"""Automatisation Leclerc Drive — bypass fiche produit + apprentissage par URL."""

from __future__ import annotations

import asyncio
import logging
import random
import subprocess
from collections.abc import Callable
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright

from app.config import LECLERC_PROFILE_PATH
from app.models.drive import DEFAULT_DRIVE_PLATFORM, DriveShoppingItem, determiner_nb_clics
from app.services.drive_base_driver import BaseDriveDriver
from app.services.drive_mapping_service import (
    ensure_plus_url,
    get_store_mapping,
    is_leclerc_product_fiche,
    normalize_product_url,
    save_mapping_entry,
)

logger = logging.getLogger(__name__)

LECLERC_STORE_URL = (
    "https://fd4-courses.leclercdrive.fr/"
    "magasin-103101-103101-Roques-sur-Garonne-Toulouse.aspx"
)

_FICHE_PRODUIT_ROOT = "#divWCRS388_FicheProduit, section.fiche-produit, .WCRS388_FicheProduit"


class LeclercDriver(BaseDriveDriver):
    """Robot courses Leclerc Drive — cycle de vie Playwright entièrement dans run()."""

    platform_id = DEFAULT_DRIVE_PLATFORM

    def __init__(
        self,
        on_status: Callable[[str], None],
        on_failures: Callable[[list[str]], None],
        on_learned: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(on_status, on_failures, on_learned)
        self._produits_a_valider: list[str] = []
        self._context: BrowserContext | None = None

    async def run(self, items: list[DriveShoppingItem]) -> None:
        self.resume_event.clear()
        async with async_playwright() as playwright:
            LECLERC_PROFILE_PATH.mkdir(parents=True, exist_ok=True)
            context = await playwright.chromium.launch_persistent_context(
                str(LECLERC_PROFILE_PATH),
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
                await self._phase_shopping(page, items)
                await self._phase_learning(page, items)
                self.on_status(
                    "[LeclercBot] Terminé — navigateur laissé ouvert pour vérifier le panier."
                )
            except asyncio.CancelledError:
                self.on_status(
                    "[LeclercBot] Interrompu — navigateur laissé ouvert."
                )
                raise
            finally:
                self._context = None

    async def _phase_login(self, page: Page) -> None:
        self.on_status(
            "Ouverture Leclerc Drive (Roques-sur-Garonne) — connectez-vous si nécessaire."
        )
        await page.goto(LECLERC_STORE_URL, wait_until="domcontentloaded")
        self.on_status("En attente : cliquez sur [▶️ Démarrer les courses] une fois prêt.")
        await self.resume_event.wait()
        self.on_status("[LeclercBot] Session reprise — début des courses.")

    async def _phase_shopping(self, page: Page, items: list[DriveShoppingItem]) -> None:
        self._produits_a_valider = []
        for item in items:
            if not item.product_url:
                self._produits_a_valider.append(item.mot_cle)
                self.on_status(f"[LeclercBot] URL absente — report : {item.mot_cle}")
                continue
            if item.nb_paquets <= 0:
                self.on_status(
                    f"[LeclercBot] Contenance non renseignée — pas d'ajout : {item.mot_cle}"
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

    async def _visible_add_zone(self, page: Page):
        """Zone d'ajout panier sur la fiche produit (pas le mini-panier header)."""
        fiche = await self._product_fiche_root(page)
        locators = (
            page.locator(".js-prix-ajout .conteneur-ajout"),
            fiche.locator(".conteneur-ajout"),
            page.locator(".fiche-produit .conteneur-ajout"),
        )
        for scoped in locators:
            count = await scoped.count()
            for idx in range(count):
                zone = scoped.nth(idx)
                if not await zone.is_visible():
                    continue
                if await zone.locator(
                    "button, a, [role='button'], .icon-plus, [class*='plus']"
                ).count():
                    return zone
        raise RuntimeError("Zone d'ajout panier (.conteneur-ajout) introuvable ou masquée")

    async def _wait_for_product_fiche(self, page: Page) -> None:
        await page.wait_for_load_state("domcontentloaded")
        blocked = page.get_by_text("Access is temporarily restricted", exact=False)
        if await blocked.count() and await blocked.first.is_visible():
            raise RuntimeError(
                "Leclerc a bloqué la session (anti-bot). Reconnectez-vous manuellement."
            )
        fiche = page.locator(_FICHE_PRODUIT_ROOT).first
        try:
            await fiche.wait_for(state="visible", timeout=20000)
        except Exception as exc:
            raise RuntimeError("Fiche produit Leclerc introuvable sur la page") from exc
        await self._visible_add_zone(page)
        await page.wait_for_timeout(int(random.uniform(800, 1500)))

    def _locate_add_controls(self, zone):
        btn_ajouter = (
            zone.get_by_role("button", name="Ajouter au panier")
            .or_(zone.get_by_role("link", name="Ajouter au panier"))
            .or_(zone.get_by_text("Ajouter au panier", exact=True))
            .or_(zone.locator("a:has-text('Ajouter au panier'), button:has-text('Ajouter au panier')"))
            .or_(zone.locator("[class*='ajout'][class*='panier'], [id*='AjoutPanier']"))
            .first
        )
        btn_plus = (
            zone.locator(
                "[class*='compteur'] button:last-child, [class*='Compteur'] button:last-child, "
                "[class*='quantite'] button:last-child, [class*='Quantite'] button:last-child"
            )
            .or_(zone.locator(".icon-plus, [class*='icon-plus'], [class*='IconPlus']"))
            .or_(zone.locator("button[aria-label*='Augmenter'], button[aria-label*='augmenter']"))
            .or_(zone.locator("a[aria-label*='Augmenter'], a[aria-label*='augmenter']"))
            .or_(zone.locator("button:has-text('+'), a:has-text('+')"))
            .first
        )
        return btn_ajouter, btn_plus

    async def _pick_add_control(self, zone, *, unit: int):
        """1er paquet → Ajouter au panier ; suivants → bouton +."""
        btn_ajouter, btn_plus = self._locate_add_controls(zone)
        if unit > 1:
            if await btn_plus.is_visible(timeout=3000):
                return btn_plus, "bouton '+'"
            if await btn_ajouter.is_visible(timeout=2000):
                return btn_ajouter, "'Ajouter au panier' (repli)"
            raise RuntimeError("Bouton '+' introuvable pour incrémenter la quantité")
        if await btn_ajouter.is_visible(timeout=3000):
            return btn_ajouter, "'Ajouter au panier'"
        if await btn_plus.is_visible(timeout=3000):
            return btn_plus, "bouton '+'"
        raise RuntimeError("Aucun bouton d'ajout au panier trouvé à l'écran")

    async def _click_add_once(self, page: Page, mot_cle: str, unit: int, total: int) -> None:
        zone = await self._visible_add_zone(page)
        control, label = await self._pick_add_control(zone, unit=unit)
        await self._click_add_control(page, control, label, mot_cle, unit, total)

    async def _click_add_control(
        self, page: Page, control, label: str, mot_cle: str, unit: int, total: int
    ) -> None:
        self.on_status(
            f"[LeclercBot] Clic sur {label} (Unité {unit}/{total}) : {mot_cle}"
        )
        await control.scroll_into_view_if_needed()
        await control.click(timeout=8000)
        await page.wait_for_timeout(int(random.uniform(1800, 3000)))

    async def _add_via_product_url(self, page: Page, item: DriveShoppingItem) -> bool:
        mot_cle = item.mot_cle
        base_url = normalize_product_url(item.product_url or "")
        if not base_url:
            return False

        self.on_status(f"[LeclercBot] Chargement de la fiche produit : {base_url}")
        try:
            await page.goto(base_url, wait_until="load", timeout=30000)
            await self._wait_for_product_fiche(page)
        except Exception as exc:
            logger.warning("[LeclercBot] goto fiche échoué %s : %s", mot_cle, exc)
            self.on_status(f"[LeclercBot] Fiche inaccessible — report : {mot_cle}")
            return False

        for i in range(item.nb_paquets):
            unit = i + 1
            added = await self._add_one_paquet(page, mot_cle, base_url, unit, item.nb_paquets)
            if not added:
                return False

        self.on_status(f"[LeclercBot] Article ajouté (× {item.nb_paquets} paquet(s)) : {mot_cle}")
        return True

    async def _add_one_paquet(
        self, page: Page, mot_cle: str, base_url: str, unit: int, total: int
    ) -> bool:
        """1er paquet : fragment #plus Leclerc ; suivants : bouton + ou #plus en repli."""
        if unit == 1:
            try:
                await page.goto(ensure_plus_url(base_url), wait_until="load", timeout=30000)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(int(random.uniform(1800, 3000)))
                self.on_status(
                    f"[LeclercBot] Ajout via #plus (Unité {unit}/{total}) : {mot_cle}"
                )
                return True
            except Exception as exc:
                logger.warning("[LeclercBot] #plus échoué %s unité 1 : %s", mot_cle, exc)

        try:
            await self._click_add_once(page, mot_cle, unit, total)
            return True
        except Exception as exc:
            logger.warning(
                "[LeclercBot] Clic DOM échoué %s unité %s/%s : %s",
                mot_cle,
                unit,
                total,
                exc,
            )

        try:
            await page.goto(ensure_plus_url(base_url), wait_until="load", timeout=30000)
            await page.wait_for_timeout(int(random.uniform(1800, 3000)))
            self.on_status(
                f"[LeclercBot] Ajout via #plus repli (Unité {unit}/{total}) : {mot_cle}"
            )
            return True
        except Exception as exc:
            logger.warning(
                "[LeclercBot] Échec d'ajout pour %s à l'unité %s/%s : %s",
                mot_cle,
                unit,
                total,
                exc,
            )
            self.on_status(
                f"[LeclercBot] Échec d'ajout pour {mot_cle} à l'unité {unit} : {exc}"
            )
            return False

    def _item_from_mapping(self, item: DriveShoppingItem) -> DriveShoppingItem | None:
        """Reconstruit l'article avec URL/contenance mémorisées pour un nouvel essai d'ajout."""
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
            self.on_status("[LeclercBot] Courses terminées — panier complet.")
            return

        await asyncio.to_thread(
            subprocess.run,
            ["osascript", "-e", "beep 2"],
            check=False,
        )
        self.on_failures(list(self._produits_a_valider))
        self.on_status(
            f"[LeclercBot] {len(self._produits_a_valider)} produit(s) à compléter — "
            "ouvrez la fiche produit ou collez l'URL dans le tableau."
        )

        items_by_mot = {i.mot_cle.strip().lower(): i for i in items}
        pending = list(self._produits_a_valider)
        for mot_cle in pending:
            memorized = await self._phase_learning_item(page, mot_cle)
            if not memorized:
                continue
            self.on_status(f"[LeclercBot] Produit mémorisé : {mot_cle}")
            source = items_by_mot.get(mot_cle.strip().lower())
            if source is None:
                continue
            retry_item = self._item_from_mapping(source)
            if retry_item is None:
                self.on_status(
                    f"[LeclercBot] Lien OK — renseignez « Cont. 1 pqt » puis relancez : {mot_cle}"
                )
                continue
            added = await self._add_via_product_url(page, retry_item)
            if added:
                self.on_status(f"[LeclercBot] Ajout réussi après mémorisation : {mot_cle}")

        self.on_status("[LeclercBot] Phase apprentissage terminée.")

    async def _phase_learning_item(self, page: Page, mot_cle: str) -> bool:
        """Attend que l'utilisateur ouvre une fiche produit manuellement (sans recherche auto)."""
        self.learning_done = asyncio.Event()
        self.skip_learning_event.clear()
        captured_url: str | None = None

        def on_frame_navigated(frame) -> None:
            nonlocal captured_url
            if frame != page.main_frame:
                return
            current = page.url
            if is_leclerc_product_fiche(current):
                captured_url = normalize_product_url(current)
                self.learning_done.set()

        page.on("framenavigated", on_frame_navigated)
        try:
            self.on_status(
                f"Ouvrez la fiche produit sur Leclerc pour « {mot_cle} », "
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
