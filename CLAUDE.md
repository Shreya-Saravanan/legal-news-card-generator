# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
# Local development
pip install -r requirements.txt
playwright install chromium
streamlit run app.py
```

Local secrets go in `.streamlit/secrets.toml` (gitignored):
```toml
GEMINI_API_KEY = "your-key-here"
```

## Architecture

**Flow**: URL → scrape → Gemini extract → human verify/edit → render HTML → Playwright → PNG download

### Module responsibilities

- `app.py` — Streamlit UI, session state, Playwright install-on-startup (marker: `/tmp/.playwright_installed`)
- `modules/scraper.py` — Fetches article text; tries site-specific CSS selectors in order, then generic fallback, then Playwright JS-render, then raw body. Supported sites: `livelaw.in`, `barandbench.com`, `verdictum.in`
- `modules/extractor.py` — Calls Gemini 2.5 Flash at `temperature=0` with a strict grounding prompt. Returns JSON with fields: `headline`, `case_name`, `case_citation`, `case_date`, `court`, `summary`. Strips markdown fences and uses regex to isolate the JSON block before parsing.
- `modules/renderer.py` — Renders `card_template.html` via Jinja2, then uses Playwright to capture a PNG. Background image is embedded as a base64 data URI. Font auto-shrink runs via `page.evaluate()` after `document.fonts.ready`.
- `templates/card_template.html` — 1024×1536px card layout. Two zones: a date band (rows 274–342) and a content area (rows 885–1175) with headline, case name, and citation.

### Card rendering details

- Canvas: 1024×1536px HTML; captured at `device_scale_factor=2` → 2048×3072px PNG
- Screenshot: `page.screenshot(clip={"x":0,"y":0,"width":1024,"height":1536})` (not `element.screenshot()`)
- Fonts: Cinzel (date band), Cormorant Garamond (content area) via Google Fonts
- JS auto-fit: `fitHeight` on `.headline`, `fitWidth` on `.case-name` and `.case-citation`
- Chromium flags required: `--no-sandbox`, `--disable-dev-shm-usage`, `--disable-gpu`, `--force-color-profile=srgb`

### "Not specified" handling

`_clean()` in both `app.py` and `renderer.py` converts `"Not specified"`, `"N/A"`, and `"none"` to empty string. Both layers must stay in sync — the app-layer cleans before populating edit fields; the renderer-layer is a safety net before template rendering.

### Deployment (Streamlit Cloud)

- `packages.txt` must include `fonts-liberation`, `fonts-noto-core`, `fontconfig` — without them, Chromium renders invisible text
- Gemini API key stored as `GEMINI_API_KEY` in Streamlit Cloud secrets
- Playwright Chromium is installed at app startup, not via `packages.txt`
