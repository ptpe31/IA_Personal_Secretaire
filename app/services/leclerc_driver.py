"""Automatisation Leclerc Drive — Playwright async avec session persistante."""

from __future__ import annotations

import asyncio
import logging
import random
import re
import subprocess
from collections.abc import Callable
from typing import Any

from playwright.async_api import Page, async_playwright

from app.config import LECLERC_PROFILE_PATH
from app.models.drive import CourseItem
from app.services.drive_mapping_service import get_mapping, remove_entry, save_mapping_entry

logger = logging.getLogger(__name__)

LECLERC_HOME_URL = "https://www.leclercdrive.fr/"
CART_URL_PATTERNS = ("/ajout/", "/panier/", "addToCart", "ajouter")

_PRODUCT_ID_URL_RE = re.compile(r"/(?:ajout|produit|product)/(\d+)", re.I)
_PRODUCT_ID_QUERY_RE = re.compile(r"[?&](?:productId|id|codeArticle)=(\d+)", re.I)
_BODY_ID_KEYS = ("id", "productId", "codeArticle", "product_id", "codeProduit")


def _parse_cart_payload(request: Any, page_url: str) -> dict[str, str]:
    """Extrait product_id et product_url depuis l'interception réseau Leclerc."""
    captured: dict[str, str] = {"product_url": page_url}
    url_str = request.url or ""

    for pattern in (_PRODUCT_ID_URL_RE, _PRODUCT_ID_QUERY_RE):
        match = pattern.search(url_str)
        if match:
            captured["product_id"] = match.group(1)
            break

    try:
        body = request.post_data_json
        if isinstance(body, dict):
            for key in _BODY_ID_KEYS:
                if key in body and body[key]:
                    captured["product_id"] = str(body[key])
                    break
    except Exception:
        pass

    if "product_id" not in captured:
        raise ValueError(f"Impossible d'extraire product_id depuis {url_str}")
    return captured


def is_product_page_valid(page_url: str, product_id: str | None) -> bool:
    """Vérifie que l'URL finale contient encore l'identifiant produit."""
    if not product_id:
        return False
    return product_id in page_url


class LeclercDriver:
    """Robot courses Leclerc Drive — cycle de vie Playwright entièrement dans run()."""

    def __init__(
        self,
        on_status: Callable[[str], None],
        on_failures: Callable[[list[str]], None],
    ) -> None:
        self.on_status = on_status
        self.on_failures = on_failures
        self.resume_event = asyncio.Event()
        self.skip_learning_event = asyncio.Event()
        self.learning_done = asyncio.Event()
        self._produits_a_valider: list[str] = []
        self._current_mot_cle: str | None = None

    async def run(self, items: list[CourseItem]) -> None:
        async with async_playwright() as playwright:
            LECLERC_PROFILE_PATH.mkdir(parents=True, exist_ok=True)
            context = await playwright.chromium.launch_persistent_context(
                str(LECLERC_PROFILE_PATH),
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                await self._phase_login(page)
                await self._phase_shopping(page, items)
                await self._phase_learning(page)
            finally:
                await context.close()

    async def signal_resume(self) -> None:
        self.resume_event.set()

    async def signal_skip_learning(self) -> None:
        self.skip_learning_event.set()
        self.learning_done.set()

    async def _human_delay(self) -> None:
        await asyncio.sleep(random.uniform(1.5, 3.5))

    async def _phase_login(self, page: Page) -> None:
        self.on_status("Ouverture Leclerc Drive — connectez-vous et choisissez votre magasin.")
        await page.goto(LECLERC_HOME_URL, wait_until="domcontentloaded")
        self.resume_event.clear()
        self.on_status("En attente : cliquez sur [▶️ Démarrer les courses] une fois connecté.")
        await self.resume_event.wait()
        self.on_status("[LeclercBot] Session reprise — début des courses.")

    async def _phase_shopping(self, page: Page, items: list[CourseItem]) -> None:
        self._produits_a_valider = []
        for item in items:
            success = await self._shop_item(page, item)
            if not success:
                self._produits_a_valider.append(item.mot_cle)

    async def _shop_item(self, page: Page, item: CourseItem) -> bool:
        mot_cle = item.mot_cle
        mapping = get_mapping(mot_cle)
        if mapping and mapping.get("product_url"):
            if await self._try_bypass(page, item, mapping):
                return True
        return await self._search_and_add(page, item)

    async def _try_bypass(self, page: Page, item: CourseItem, mapping: dict) -> bool:
        mot_cle = item.mot_cle
        product_url = mapping.get("product_url", "")
        product_id = mapping.get("product_id")
        self.on_status(f"[LeclercBot] Bypass URL : {mot_cle}")
        await self._human_delay()
        try:
            await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            logger.warning("[LeclercBot] goto bypass échoué %s : %s", mot_cle, exc)
            remove_entry(mot_cle)
            return False

        if not is_product_page_valid(page.url, str(product_id) if product_id else None):
            logger.warning("[LeclercBot] URL mapping expirée pour « %s » — fallback recherche", mot_cle)
            remove_entry(mot_cle)
            return False

        add_btn = page.locator("button[aria-label*='Ajouter'], button:has-text('+')").first
        try:
            if not await add_btn.is_visible(timeout=5000):
                remove_entry(mot_cle)
                return False
        except Exception:
            remove_entry(mot_cle)
            return False

        for _ in range(item.quantite):
            await self._human_delay()
            await add_btn.click()
        self.on_status(f"[LeclercBot] Article ajouté (bypass) : {mot_cle}")
        return True

    async def _search_and_add(self, page: Page, item: CourseItem) -> bool:
        mot_cle = item.mot_cle
        self.on_status(f"[LeclercBot] Recherche : {mot_cle}…")
        await self._human_delay()

        search = page.locator(
            "input[type='search'], input[placeholder*='Recherch'], input[name='Rechercher']"
        ).first
        try:
            await search.wait_for(state="visible", timeout=10000)
            await search.click()
            await search.fill("")
            await search.press_sequentially(mot_cle, delay=80)
            await search.press("Enter")
        except Exception as exc:
            logger.warning("[LeclercBot] Recherche impossible pour %s : %s", mot_cle, exc)
            return False

        await self._human_delay()
        await self._apply_marque_repere(page)
        await asyncio.sleep(2)

        cards = page.locator("[data-test='product-card'], .product-card, article.product")
        count = await cards.count()
        if count == 0:
            cards = page.locator(".col-product, li.product")
            count = await cards.count()

        for idx in range(count):
            card = cards.nth(idx)
            text = (await card.inner_text()).lower()
            if "bientôt disponible" in text or "produits similaires" in text:
                continue
            add_btn = card.locator("button[aria-label*='Ajouter'], button:has-text('+')").first
            try:
                if await add_btn.is_visible(timeout=2000):
                    for _ in range(item.quantite):
                        await self._human_delay()
                        await add_btn.click()
                    self.on_status(f"[LeclercBot] Article ajouté au panier : {mot_cle}")
                    return True
            except Exception:
                continue

        self.on_status(f"[LeclercBot] Aucun produit disponible pour : {mot_cle}")
        return False

    async def _apply_marque_repere(self, page: Page) -> None:
        try:
            checkbox = page.get_by_role("checkbox", name="Marque Repère")
            if await checkbox.is_visible(timeout=3000):
                await checkbox.check()
                self.on_status("[LeclercBot] Filtre Marque Repère appliqué.")
        except Exception:
            logger.debug("[LeclercBot] Filtre Marque Repère non trouvé.")

    async def _phase_learning(self, page: Page) -> None:
        if not self._produits_a_valider:
            self.on_status("[LeclercBot] Courses terminées — panier complet.")
            return

        await asyncio.to_thread(
            subprocess.run,
            ["osascript", "-e", "beep 2"],
            check=False,
        )
        self.on_failures(list(self._produits_a_valider))
        self.on_status(f"[LeclercBot] {len(self._produits_a_valider)} produit(s) à valider manuellement.")

        for mot_cle in self._produits_a_valider:
            memorized = await self._phase_learning_item(page, mot_cle)
            if memorized:
                self.on_status(f"[LeclercBot] Produit mémorisé : {mot_cle}")

        self.on_status("[LeclercBot] Phase apprentissage terminée.")

    async def _phase_learning_item(self, page: Page, mot_cle: str) -> bool:
        self.learning_done = asyncio.Event()
        self.skip_learning_event.clear()
        self._current_mot_cle = mot_cle
        captured: dict[str, str] = {}

        def on_request(request: Any) -> None:
            try:
                if request.method not in ("POST", "PUT"):
                    return
                if not any(p in request.url for p in CART_URL_PATTERNS):
                    return
                captured.update(_parse_cart_payload(request, page.url))
                self.learning_done.set()
            except Exception as exc:
                logger.warning(
                    "[LeclercBot] Requête panier ignorée (%s): %s",
                    getattr(request, "url", "?"),
                    exc,
                )

        page.on("request", on_request)
        try:
            await self._search_keyword_only(page, mot_cle)
            self.on_status(
                f"Cliquez sur + dans Leclerc pour « {mot_cle} », ou [Passer ce produit]"
            )

            skip_task = asyncio.create_task(self.skip_learning_event.wait())
            learn_task = asyncio.create_task(self.learning_done.wait())
            done, pending = await asyncio.wait(
                {skip_task, learn_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
        finally:
            page.remove_listener("request", on_request)

        if captured:
            save_mapping_entry(
                mot_cle,
                product_name=mot_cle,
                product_url=captured.get("product_url"),
                product_id=captured.get("product_id"),
            )
            return True
        return False

    async def _search_keyword_only(self, page: Page, mot_cle: str) -> None:
        search = page.locator(
            "input[type='search'], input[placeholder*='Recherch'], input[name='Rechercher']"
        ).first
        try:
            await search.wait_for(state="visible", timeout=10000)
            await search.click()
            await search.fill("")
            await search.press_sequentially(mot_cle, delay=80)
            await search.press("Enter")
        except Exception as exc:
            logger.warning("[LeclercBot] Recherche apprentissage %s : %s", mot_cle, exc)
