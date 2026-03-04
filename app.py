"""
app.py — Streamlit UI for the Legal News Card Generator.

Flow: URL → Scrape → Gemini Extract → Human Verify/Edit → Render → Download PNG
"""

import streamlit as st
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Install Playwright Chromium on Streamlit Cloud (runs once per container session)
_marker = Path("/tmp/.playwright_installed")
if not _marker.exists():
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    _marker.touch()

from modules.scraper import scrape_article
from modules.extractor import extract_structured_data
from modules.renderer import render_card, html_to_png

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

# ------------------------------------------------------------------
st.set_page_config(
    page_title="Legal Card Generator",
    page_icon="⚖️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  /* Main background — deep royal navy */
  .stApp { background: #0d1b3e; }

  /* All default text white */
  .stApp, .stApp p, .stApp li, .stApp label,
  div[data-testid="stMarkdownContainer"] p { color: #e8e8f0 !important; }

  /* Headings */
  h1, h2, h3 { font-family: Georgia, serif; color: #c9a84c !important; }

  /* Caption / small text */
  .stApp .stCaption, small { color: #a0a8c0 !important; }

  /* Input fields */
  div[data-testid="stTextInput"] input,
  div[data-testid="stTextArea"] textarea {
    background: #1a2b5e;
    color: #e8e8f0;
    border: 1px solid #3a4f8a;
    border-radius: 6px;
    font-size: 14px;
  }

  /* Buttons */
  .stButton > button {
    border-radius: 6px;
    font-weight: 600;
    background: #1a3a6e;
    color: #e8e8f0;
    border: 1px solid #3a5fa0;
  }
  .stButton > button:hover { background: #c9a84c; color: #0d1b3e; }

  /* Expander */
  div[data-testid="stExpander"] { background: #132248; border: 1px solid #2a3f70; border-radius: 8px; }

  /* Info / success / error boxes */
  div[data-testid="stAlert"] { background: #132248; border-radius: 8px; }

  /* Divider */
  hr { border-color: #2a3f70; }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# SESSION STATE
# ------------------------------------------------------------------
for k in ["scraped", "extracted", "html_rendered", "png_bytes",
          "edit_headline", "edit_case_name", "edit_case_citation", "edit_case_date"]:
    if k not in st.session_state:
        st.session_state[k] = None

# ------------------------------------------------------------------
# HEADER
# ------------------------------------------------------------------
st.markdown("# ⚖️ Legal News Card Generator")
st.caption("Paste a LiveLaw, Bar & Bench, or Verdictum URL → fetch & extract → verify → download a publication-ready card.")
st.markdown("---")

# ------------------------------------------------------------------
# STEP 1 — SCRAPE + EXTRACT
# ------------------------------------------------------------------
st.markdown("### 1 · Paste Article URL")
url = st.text_input("", placeholder="https://www.livelaw.in/...", label_visibility="collapsed")

if st.button("🔍 Fetch & Extract", use_container_width=False):
    if not url.strip():
        st.error("Please enter a URL.")
    else:
        with st.spinner("Fetching article..."):
            scraped = scrape_article(url.strip())
        if scraped["error"]:
            st.error(f"Scraping failed: {scraped['error']}")
        else:
            st.session_state.scraped            = scraped
            st.session_state.extracted          = None
            st.session_state.html_rendered      = None
            st.session_state.png_bytes          = None
            st.session_state.edit_headline      = None
            st.session_state.edit_case_name     = None
            st.session_state.edit_case_citation = None
            st.session_state.edit_case_date     = None
            with st.spinner("Extracting with Gemini 2.5 Flash..."):
                extracted = extract_structured_data(scraped["text"], GEMINI_API_KEY)
            if extracted["error"]:
                st.error(f"Extraction failed: {extracted['error']}")
                if extracted.get("raw_response"):
                    with st.expander("Raw Gemini output (debug)"):
                        st.code(extracted["raw_response"])
            else:
                st.session_state.extracted          = extracted
                st.session_state.edit_headline      = extracted.get("headline", "")
                st.session_state.edit_case_name     = extracted.get("case_name", "")
                st.session_state.edit_case_citation = extracted.get("case_citation", "")
                st.session_state.edit_case_date     = extracted.get("case_date", "")
                st.success(f"✅ Fetched & extracted: **{scraped['title'][:80]}**")

# Show summary persistently whenever extracted data is available
if st.session_state.extracted:
    summary = st.session_state.extracted.get("summary", "")
    if summary and summary != "Not specified":
        st.markdown("---")
        st.markdown("**Article Summary**")
        st.info(summary)

# ------------------------------------------------------------------
# STEP 2 — VERIFY & EDIT
# ------------------------------------------------------------------
if st.session_state.extracted and not st.session_state.extracted.get("error"):
    st.markdown("---")
    st.markdown("### 2 · Verify & Edit")
    st.info("All AI-extracted fields are editable. Correct anything before generating.")

    ex = st.session_state.extracted

    st.text_area("📰 Headline", key="edit_headline", height=100,
                 help="Bold title as it will appear on the card")
    st.text_input("⚖️ Case Name (Petitioner Vs. Respondent)", key="edit_case_name")
    st.text_input("📁 Case Citation / Number", key="edit_case_citation")
    st.text_input("📅 Date of Judgment (DD.MM.YYYY)", key="edit_case_date")

    st.caption(f"Court identified: **{ex.get('court', 'N/A')}** (used internally)")
    st.markdown("")

    if st.button("✅ Approve & Generate Card", use_container_width=True, type="primary"):
        st.session_state.extracted.update({
            "headline":      st.session_state.edit_headline or "",
            "case_name":     st.session_state.edit_case_name or "",
            "case_citation": st.session_state.edit_case_citation or "",
            "case_date":     st.session_state.edit_case_date or "",
        })

        with st.spinner("Rendering HTML template..."):
            html = render_card(st.session_state.extracted)
            st.session_state.html_rendered = html

        with st.spinner("Launching headless Chromium → PNG..."):
            try:
                png = html_to_png(html)
                st.session_state.png_bytes = png
                st.success("🎉 Card generated!")
            except Exception as e:
                st.error(f"PNG conversion failed: {e}")
                st.caption("Ensure Playwright is installed: `playwright install chromium`")
                st.download_button("⬇️ Download HTML fallback",
                    data=html, file_name="legal_card.html", mime="text/html")

# ------------------------------------------------------------------
# STEP 3 — PREVIEW & DOWNLOAD
# ------------------------------------------------------------------
if st.session_state.png_bytes:
    st.markdown("---")
    st.markdown("### 3 · Preview & Download")
    st.image(st.session_state.png_bytes, caption="900×1200 card (rendered at 2×)", use_container_width=True)

    st.download_button(
        label="⬇️ Download PNG",
        data=st.session_state.png_bytes,
        file_name="legal_card_900x1200.png",
        mime="image/png",
        use_container_width=True,
        type="primary",
    )

# Footer
st.markdown("---")
st.caption("Legal Card Generator · Gemini 2.5 Flash + Playwright + Streamlit · Human-verified before publish.")
