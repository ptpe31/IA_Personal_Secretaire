#!/usr/bin/env python3
"""Inspecte une fiche produit Leclerc Drive avec le profil persistant Trankil-v2.

Usage:
    .venv/bin/python scripts/inspect_leclerc_fiche.py [URL]

Nécessite une session déjà connectée dans ~/.leclerc_profile (ou ~/Trankil-v2/.leclerc_profile).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from app.config import LECLERC_PROFILE_PATH
from app.services.leclerc_driver import (
    _LECLERC_ADD_BTN,
    _LECLERC_ADD_ZONE,
    _LECLERC_COUNTER,
    _LECLERC_MORE_BTN,
    _LECLERC_QTY,
)

DEFAULT_URL = (
    "https://fd4-courses.leclercdrive.fr/magasin-103101-103101-Roques-sur-Garonne-Toulouse/"
    "fiche-produits-36039-Creme-legere-fluide-UHT-Delisse.aspx"
)


async def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    profile = Path(LECLERC_PROFILE_PATH)
    print(f"Profil : {profile}")
    print(f"URL    : {url}\n")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(profile),
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print("HTTP:", resp.status if resp else "?")
        await page.wait_for_timeout(5000)

        title = await page.title()
        print("Title:", title)
        if "restricted" in title.lower() or "temporarily" in (await page.inner_text("body")).lower():
            print("\n⚠️  Page de blocage anti-bot détectée — connectez-vous manuellement d'abord.")
            await context.close()
            return

        probes = [
            ("conteneur-ajout", page.locator(_LECLERC_ADD_ZONE)),
            ("WCRS310 Add (lien <a>)", page.locator(_LECLERC_ADD_BTN)),
            ("WCRS310 counter", page.locator(_LECLERC_COUNTER)),
            ("WCRS310 More (+)", page.locator(_LECLERC_MORE_BTN)),
            ("WCRS310 qty", page.locator(_LECLERC_QTY)),
            ("role=button name=Ajouter au panier", page.get_by_role("button", name="Ajouter au panier")),
            ("role=link name=Ajouter au panier", page.get_by_role("link", name="Ajouter au panier")),
            ("text=Ajouter au panier", page.get_by_text("Ajouter au panier", exact=True)),
            ("a:has-text", page.locator("a:has-text('Ajouter au panier')")),
            ("button:has-text", page.locator("button:has-text('Ajouter au panier')")),
            ("[class*='Ajout']", page.locator("[class*='Ajout'], [class*='ajout']")),
            ("[id*='Ajout']", page.locator("[id*='Ajout'], [id*='ajout']")),
            (".icon-plus", page.locator(".icon-plus")),
            ("compteur button", page.locator("[class*='compteur'] button, [class*='Compteur'] button")),
        ]
        print("\n=== PROBES ===")
        for label, loc in probes:
            count = await loc.count()
            if not count:
                continue
            first = loc.first
            visible = await first.is_visible()
            outer = await first.evaluate("el => el.outerHTML.slice(0, 500)")
            box = await first.bounding_box()
            print(f"\n[{label}] count={count} visible={visible} box={box}")
            print(outer)

        candidates = await page.evaluate(
            """() => {
            const out = [];
            for (const el of document.querySelectorAll('a, button, [role=\"button\"]')) {
                const t = (el.innerText || '').trim().replace(/\\s+/g, ' ');
                if (!t.includes('Ajouter') && !t.includes('+')) continue;
                const r = el.getBoundingClientRect();
                if (r.width < 5 || r.height < 5) continue;
                out.push({
                    tag: el.tagName,
                    text: t.slice(0, 80),
                    id: el.id,
                    cls: (typeof el.className === 'string' ? el.className : '').slice(0, 120),
                    role: el.getAttribute('role'),
                    href: el.getAttribute('href'),
                });
            }
            return out;
        }"""
        )
        print("\n=== CANDIDATES JSON ===")
        print(json.dumps(candidates, ensure_ascii=False, indent=2))
        input("\nFenêtre ouverte — inspectez DevTools puis Entrée pour fermer…")
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
