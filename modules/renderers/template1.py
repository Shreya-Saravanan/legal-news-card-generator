"""
renderers/template1.py — Original CNICA card template.

Layout:
  - Date band: rows 274–342 (centre of card)
  - Content area: rows 885–1175 (headline + case name + citation)
"""

import base64
import logging
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

TEMPLATES_DIR  = Path(__file__).parent.parent.parent / "templates"
ASSETS_DIR     = Path(__file__).parent.parent.parent / "assets"
BG_IMAGE_PATH  = ASSETS_DIR / "cnica_template_background.png"
TEMPLATE_NAME  = "card_template.html"


def _load_bg_base64() -> str:
    if not BG_IMAGE_PATH.exists():
        raise FileNotFoundError(
            f"Background image not found: {BG_IMAGE_PATH}\n"
            f"Place cnica_template_background.png in: {ASSETS_DIR}/"
        )
    with open(BG_IMAGE_PATH, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def _clean(val) -> str:
    v = str(val).strip() if val else ""
    return "" if v.lower() in ("not specified", "n/a", "none") else v


def _trunc(text: str, max_len: int) -> str:
    text = str(text).strip()
    return text[:max_len - 1] + "…" if len(text) > max_len else text


def render_card(data: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template(TEMPLATE_NAME)

    current_date = datetime.now().strftime("%-d %B %Y").upper()

    template_vars = {
        "bg_src":        _load_bg_base64(),
        "current_date":  current_date,
        "headline":      _trunc(_clean(data.get("headline")),      400),
        "case_name":     _trunc(_clean(data.get("case_name")),     200),
        "case_citation": _trunc(_clean(data.get("case_citation")), 200),
        "case_date":     _trunc(_clean(data.get("case_date")),     20),
    }

    rendered = template.render(**template_vars)
    logger.info("[template1] Rendered (%d chars)", len(rendered))
    return rendered
