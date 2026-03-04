"""
renderer.py — Jinja2 rendering + Playwright HTML→PNG export.

Canvas : 1024×1536px (matches background image exactly).
Output : 2× scale = 2048×3072px.

Template variables:
  bg_src         : base64 data URI of background PNG
  current_date   : e.g. "19 FEBRUARY 2026"  (shown in date band)
  headline       : Bold ruling headline (up to 3 lines)
  case_name      : "Petitioner Vs. Respondent"
  case_citation  : "Arbitration O.P.(Com.Div.) No.603 of 2022"
  case_date      : "20.01.2026"
"""

import logging
import base64
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
ASSETS_DIR    = Path(__file__).parent.parent / "assets"
OUTPUT_DIR    = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

BG_IMAGE_PATH = ASSETS_DIR / "cnica_template_background.png"


def _load_bg_base64() -> str:
    if not BG_IMAGE_PATH.exists():
        raise FileNotFoundError(
            f"Background image not found: {BG_IMAGE_PATH}\n"
            f"Place cnica_template_background.png in: {ASSETS_DIR}/"
        )
    with open(BG_IMAGE_PATH, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def _trunc(text: str, max_len: int) -> str:
    text = str(text).strip()
    return text[:max_len - 1] + "…" if len(text) > max_len else text


def render_card(data: dict, config: dict = None) -> str:
    """
    Render the card HTML template.

    Args:
        data: dict with keys — headline, case_name, case_citation, case_date
        config: unused (branding is in the background image)

    Returns:
        Rendered HTML string.
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("card_template.html")

    # Date band: always show today's date
    current_date = datetime.now().strftime("%-d %B %Y").upper()

    template_vars = {
        "bg_src":        _load_bg_base64(),
        "current_date":  current_date,
        "headline":      _trunc(data.get("headline",      "Not specified"), 400),
        "case_name":     _trunc(data.get("case_name",     "Not specified"), 200),
        "case_citation": _trunc(data.get("case_citation", "Not specified"), 200),
        "case_date":     _trunc(data.get("case_date",     ""),              20),
    }

    rendered = template.render(**template_vars)
    logger.info("Template rendered (%d chars)", len(rendered))
    return rendered


def html_to_png(html_content: str, output_filename: str = "legal_card.png") -> bytes:
    """Convert rendered HTML to PNG via Playwright (2048×3072px output)."""
    from playwright.sync_api import sync_playwright

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
                fitHeight(document.querySelector('.headline'), 20);
                fitWidth(document.querySelector('.case-name'), 16);
                fitWidth(document.querySelector('.case-citation'), 16);
            }
        """)

        # Use page screenshot clipped to card bounds (more reliable than element screenshot)
        png_bytes = page.screenshot(type="png", clip={"x": 0, "y": 0, "width": 1024, "height": 1536})
        browser.close()

    out_path = OUTPUT_DIR / output_filename
    with open(out_path, "wb") as f:
        f.write(png_bytes)
    logger.info("PNG: %s (%d KB)", out_path, len(png_bytes) // 1024)
    return png_bytes
