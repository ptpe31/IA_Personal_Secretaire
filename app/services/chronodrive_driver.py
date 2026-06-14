"""Automatisation Chronodrive (Portet) — fiche produit -P{id} + apprentissage par URL."""

from __future__ import annotations

import asyncio
import logging
import random
import subprocess
import time
from collections.abc import Callable
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright

from app.config import CHRONODRIVE_PROFILE_PATH
from app.models.drive import DriveShoppingItem, determiner_nb_clics
from app.services.drive_base_driver import BaseDriveDriver
from app.services.drive_mapping_service import (
    get_store_mapping,
    is_chronodrive_product_fiche,
    normalize_product_url,
    save_mapping_entry,
)

logger = logging.getLogger(__name__)

_OPEN_CHRONODRIVE_SESSIONS: list[tuple[Any, BrowserContext]] = []

CHRONODRIVE_STORE_URL = "https://www.chronodrive.com/"

_FICHE_PRODUIT_ROOT = ".page-layout.product-page, .product-details"
_CART_ZONE = ".product-details .product-actions-info .cart-stepper"
_ADD_BTN = "button.cart-stepper-add"
_QTY = ".cart-stepper-output"
_SEARCH = "#search-input"
_ROBOT_DONE_MARKER = "terminé"


class ChronodriveDriver(BaseDriveDriver):
    """Robot courses Chronodrive Portet — cycle de vie Playwright entièrement dans run()."""

    platform_id = "chronodrive"

    def __init__(
        self,
        on_status: Callable[[str], None],
        on_failures: Callable[[list[str]], None],
        on_learned: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(on_status, on_failures, on_learned)
        self._produits_a_valider: list[str] = []
        self._context: BrowserContext | None = None
        self._playwright: Any = None
        self._playwright_mgr: Any = None
        self.items: list[DriveShoppingItem] = []

    async def signal_resume(self, updated_items: list[DriveShoppingItem] | None = None) -> None:
        if updated_items is not None:
            self.items = updated_items
        self.resume_event.set()

    async def run(self, items: list[DriveShoppingItem]) -> None:
        self.resume_event.clear()
        self.items = list(items)
        self._playwright_mgr = async_playwright()
        playwright = await self._playwright_mgr.start()
        self._playwright = playwright
        CHRONODRIVE_PROFILE_PATH.mkdir(parents=True, exist_ok=True)
        context = await playwright.chromium.launch_persistent_context(
            str(CHRONODRIVE_PROFILE_PATH),
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        self._context = context
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            await self._phase_login(page)
            await self._phase_shopping(page, self.items)
            await self._phase_learning(page, self.items)
            await self._signal_robot_done(page)
            self.on_status(
                "[ChronodriveBot] Terminé — « terminé » saisi dans la recherche, "
                "navigateur laissé ouvert pour vérifier le panier."
            )
        except asyncio.CancelledError:
            self.on_status(
                "[ChronodriveBot] Interrompu — navigateur laissé ouvert."
            )
            raise
        finally:
            _OPEN_CHRONODRIVE_SESSIONS.append((self._playwright_mgr, context))
            self._context = None

    async def _phase_login(self, page: Page) -> None:
        self.on_status(
            "Ouverture Chronodrive (Portet) — connectez-vous, "
            "fermez les cookies et choisissez le mode de service si besoin."
        )
        await page.goto(CHRONODRIVE_STORE_URL, wait_until="domcontentloaded")
        self.on_status("En attente : cliquez sur [▶️ Démarrer les courses] une fois prêt.")
        await self.resume_event.wait()
        self.on_status(
            f"[ChronodriveBot] Session reprise — début des courses ({len(self.items)} article(s))."
        )

    async def _phase_shopping(self, page: Page, items: list[DriveShoppingItem]) -> None:
        self._produits_a_valider = []
        for item in items:
            if not item.product_url:
                self._produits_a_valider.append(item.mot_cle)
                self.on_status(f"[ChronodriveBot] URL absente — report : {item.mot_cle}")
                continue
            if item.nb_paquets <= 0:
                self.on_status(
                    f"[ChronodriveBot] Contenance non renseignée — pas d'ajout : {item.mot_cle}"
                )
                continue
            success = await self._add_via_product_url(page, item)
            if not success:
                self._produits_a_valider.append(item.mot_cle)

    async def _product_fiche_root(self, page: Page):
        fiche = page.locator(_FICHE_PRODUIT_ROOT).first
        if await fiche.count() and await fiche.is_visible():
            return fiche
        return page.locator("body")

    async def _cart_stepper(self, page: Page):
        fiche = await self._product_fiche_root(page)
        for scoped in (
            fiche.locator(_CART_ZONE),
            page.locator(_CART_ZONE),
        ):
            count = await scoped.count()
            for idx in range(count):
                zone = scoped.nth(idx)
                if not await zone.is_visible():
                    continue
                if await zone.locator(_ADD_BTN).count():
                    return zone
        raise RuntimeError(
            "Stepper panier introuvable sur la fiche produit (.product-actions-info .cart-stepper)"
        )

    async def _read_fiche_qty(self, page: Page) -> int:
        zone = await self._cart_stepper(page)
        qty_el = zone.locator(_QTY).first
        if not await qty_el.count():
            return 0
        try:
            if not await qty_el.is_visible():
                return 0
            return int((await qty_el.inner_text()).strip())
        except ValueError:
            return 0

    async def _wait_for_fiche_qty_at_least(
        self, page: Page, minimum: int, *, timeout_ms: int = 12000
    ) -> None:
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            if await self._read_fiche_qty(page) >= minimum:
                return
            await page.wait_for_timeout(250)
        current = await self._read_fiche_qty(page)
        raise RuntimeError(
            f"Quantité fiche produit inchangée ({current}, attendu ≥ {minimum})"
        )

    async def _wait_for_product_fiche(self, page: Page) -> None:
        await page.wait_for_load_state("domcontentloaded")
        fiche = page.locator(_FICHE_PRODUIT_ROOT).first
        try:
            await fiche.wait_for(state="visible", timeout=20000)
        except Exception as exc:
            raise RuntimeError("Fiche produit Chronodrive introuvable sur la page") from exc
        await self._cart_stepper(page)
        await page.wait_for_timeout(int(random.uniform(800, 1500)))

    async def _click_add_once(self, page: Page, mot_cle: str, unit: int, total: int) -> None:
        zone = await self._cart_stepper(page)
        btn_add = zone.locator(_ADD_BTN).first
        if not await btn_add.is_visible(timeout=5000):
            raise RuntimeError("Bouton cart-stepper-add introuvable sur la fiche produit")
        label = (
            "bouton '+' (cart-stepper-add)"
            if unit > 1
            else "'Ajouter au panier' (cart-stepper-add)"
        )
        await self._click_add_control(page, btn_add, label, mot_cle, unit, total)
        await self._wait_for_fiche_qty_at_least(page, unit)

    async def _click_add_control(
        self, page: Page, control, label: str, mot_cle: str, unit: int, total: int
    ) -> None:
        self.on_status(
            f"[ChronodriveBot] Clic sur {label} (Unité {unit}/{total}) : {mot_cle}"
        )
        await control.scroll_into_view_if_needed()
        await control.click(timeout=8000)
        await page.wait_for_timeout(int(random.uniform(1800, 3000)))

    async def _add_via_product_url(self, page: Page, item: DriveShoppingItem) -> bool:
        mot_cle = item.mot_cle
        base_url = normalize_product_url(item.product_url or "")
        if not base_url:
            return False

        self.on_status(f"[ChronodriveBot] Chargement de la fiche produit : {base_url}")
        try:
            await page.goto(base_url, wait_until="load", timeout=30000)
            await self._wait_for_product_fiche(page)
        except Exception as exc:
            logger.warning("[ChronodriveBot] goto fiche échoué %s : %s", mot_cle, exc)
            self.on_status(f"[ChronodriveBot] Fiche inaccessible — report : {mot_cle}")
            return False

        for i in range(item.nb_paquets):
            unit = i + 1
            if await self._read_fiche_qty(page) >= unit:
                continue
            try:
                await self._click_add_once(page, mot_cle, unit, item.nb_paquets)
            except Exception as exc:
                logger.warning(
                    "[ChronodriveBot] Échec d'ajout pour %s à l'unité %s/%s : %s",
                    mot_cle,
                    unit,
                    item.nb_paquets,
                    exc,
                )
                self.on_status(
                    f"[ChronodriveBot] Échec d'ajout pour {mot_cle} à l'unité {unit} "
                    f"(quantité fiche : {await self._read_fiche_qty(page)})"
                )
                return False

        self.on_status(
            f"[ChronodriveBot] Article ajouté (× {item.nb_paquets} paquet(s)) : {mot_cle}"
        )
        return True

    async def _signal_robot_done(self, page: Page) -> None:
        """Marqueur visuel de fin : « terminé » dans la barre de recherche, sans Entrée."""
        field = page.locator(_SEARCH).first
        try:
            if not await field.count():
                raise RuntimeError("Champ #search-input introuvable")
            await field.wait_for(state="visible", timeout=3000)
            await field.click(timeout=3000)
            await field.fill(_ROBOT_DONE_MARKER)
            self.on_status(
                f"[ChronodriveBot] Signal de fin : « {_ROBOT_DONE_MARKER} » "
                "saisi dans la barre de recherche (sans validation)."
            )
        except Exception as exc:
            logger.warning("[ChronodriveBot] Barre de recherche introuvable : %s", exc)

    def _item_from_mapping(self, item: DriveShoppingItem) -> DriveShoppingItem | None:
        mapping = get_store_mapping(item.mot_cle, self.platform_id) or {}
        url = normalize_product_url(mapping.get("product_url") or "") or None
        if not url:
            return None
        contenance = mapping.get("contenance_paquet") or mapping.get("quantite_paquet")
        if not contenance or float(contenance) <= 0:
            return None
        unite = mapping.get("unite_paquet") or item.unite_recette
        preview: dict[str, Any] = {
            **mapping,
            "contenance_paquet": float(contenance),
            "unite_paquet": unite,
        }
        nb_paquets = determiner_nb_clics(item, preview)
        if nb_paquets <= 0:
            return None
        return item.model_copy(update={"product_url": url, "nb_paquets": nb_paquets})

    async def _phase_learning(self, page: Page, items: list[DriveShoppingItem]) -> None:
        if not self._produits_a_valider:
            self.on_status("[ChronodriveBot] Courses terminées — panier complet.")
            return

        await asyncio.to_thread(
            subprocess.run,
            ["osascript", "-e", "beep 2"],
            check=False,
        )
        self.on_failures(list(self._produits_a_valider))
        self.on_status(
            f"[ChronodriveBot] {len(self._produits_a_valider)} produit(s) à compléter — "
            "ouvrez la fiche produit ou collez l'URL dans le tableau."
        )

        items_by_mot = {i.mot_cle.strip().lower(): i for i in items}
        pending = list(self._produits_a_valider)
        for mot_cle in pending:
            memorized = await self._phase_learning_item(page, mot_cle)
            if not memorized:
                continue
            self.on_status(f"[ChronodriveBot] Produit mémorisé : {mot_cle}")
            source = items_by_mot.get(mot_cle.strip().lower())
            if source is None:
                continue
            retry_item = self._item_from_mapping(source)
            if retry_item is None:
                self.on_status(
                    f"[ChronodriveBot] Lien OK — renseignez « Cont. 1 pqt » puis relancez : {mot_cle}"
                )
                continue
            added = await self._add_via_product_url(page, retry_item)
            if added:
                self.on_status(f"[ChronodriveBot] Ajout réussi après mémorisation : {mot_cle}")

        self.on_status("[ChronodriveBot] Phase apprentissage terminée.")

    async def _phase_learning_item(self, page: Page, mot_cle: str) -> bool:
        """Attend que l'utilisateur ouvre une fiche produit manuellement."""
        self.learning_done = asyncio.Event()
        self.skip_learning_event.clear()
        captured_url: str | None = None

        def on_frame_navigated(frame) -> None:
            nonlocal captured_url
            if frame != page.main_frame:
                return
            current = page.url
            if is_chronodrive_product_fiche(current):
                captured_url = normalize_product_url(current)
                self.learning_done.set()

        page.on("framenavigated", on_frame_navigated)
        try:
            self.on_status(
                f"Ouvrez la fiche produit sur Chronodrive pour « {mot_cle} », "
                "ou collez l'URL dans le tableau, ou [Passer ce produit]"
            )

            skip_task = asyncio.create_task(self.skip_learning_event.wait())
            learn_task = asyncio.create_task(self.learning_done.wait())
            _done, pending = await asyncio.wait(
                {skip_task, learn_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
        finally:
            page.remove_listener("framenavigated", on_frame_navigated)

        if captured_url:
            save_mapping_entry(
                mot_cle,
                platform=self.platform_id,
                product_name=mot_cle,
                product_url=captured_url,
            )
            self.on_learned(mot_cle, captured_url)
            return True
        return False
