"""
renderer.py — Dispatcher: randomly picks a card template, then renders HTML → PNG.

Templates available:
  template1  — original CNICA card (date band in centre)
  template2  — ArbitrationTimes card (date top-right, headline above separator,
                case details below separator)

Canvas : 1024×1536px
Output : 2× scale = 2048×3072px
"""

import logging
from modules.renderers import template1, template2

logger = logging.getLogger(__name__)

_RENDERERS = [template1, template2]


def render_card(data: dict) -> str:
    """Select a template based on the current date (rotates daily) and render the card HTML."""
    from datetime import date
    day_index = date.today().toordinal() % len(_RENDERERS)
    renderer = _RENDERERS[day_index]
    logger.info("Selected renderer: %s", renderer.__name__)
    return renderer.render_card(data)


def html_to_png(html_content: str, output_filename: str = "legal_card.png") -> bytes:
    """Convert rendered HTML to PNG via Playwright (2048×3072px output)."""
    from pathlib import Path
    from playwright.sync_api import sync_playwright

    OUTPUT_DIR = Path(__file__).parent.parent / "output"
    OUTPUT_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--force-color-profile=srgb",
        ])
        context = browser.new_context(
            viewport={"width": 1024, "height": 1536},
            device_scale_factor=2,
        )
        page = context.new_page()
        page.set_content(html_content, wait_until="networkidle")
        # Force all fonts to load (catches Google Fonts failures gracefully)
        page.evaluate("async () => { await document.fonts.ready; await Promise.all([...document.fonts].map(f => f.load().catch(() => {}))); }")
        page.wait_for_timeout(3000)

        # Auto-fit text after fonts are confirmed loaded
        page.evaluate("""
            () => {
                function fitHeight(el, minPx) {
                    if (!el) return;
                    var size = parseFloat(window.getComputedStyle(el).fontSize);
                    while (el.scrollHeight > el.clientHeight && size > minPx) {
                        size -= 0.5;
                        el.style.fontSize = size + 'px';
                    }
                }
                function fitWidth(el, minPx) {
                    if (!el) return;
                    var size = parseFloat(window.getComputedStyle(el).fontSize);
                    while (el.scrollWidth > el.clientWidth && size > minPx) {
                        size -= 0.5;
                        el.style.fontSize = size + 'px';
                    }
                }
                fitHeight(document.querySelector('.headline'), 16);
                fitWidth(document.querySelector('.case-name'), 14);
                fitWidth(document.querySelector('.case-citation'), 14);
                fitWidth(document.querySelector('.case-date'), 14);
                fitWidth(document.querySelector('.case-block'), 12);
            }
        """)

        png_bytes = page.screenshot(type="png", clip={"x": 0, "y": 0, "width": 1024, "height": 1536})
        browser.close()

    out_path = OUTPUT_DIR / output_filename
    with open(out_path, "wb") as f:
        f.write(png_bytes)
    logger.info("PNG: %s (%d KB)", out_path, len(png_bytes) // 1024)
    return png_bytes
