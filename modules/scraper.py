"""
scraper.py — Article text extraction from legal news sites.

Supports: LiveLaw, Bar & Bench, Verdictum
Strategy: Site-specific CSS selectors (multiple tried in order)
          → generic fallback → Playwright JS-render fallback → raw body text
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Site-specific extraction rules.
# Each domain maps to a list of selectors tried in order.
# The first one that returns >200 chars of text wins.
# ------------------------------------------------------------------
SITE_SELECTORS = {
    "livelaw.in": [
        "div.details-story-wrapper",
        ".details-story-wrapper",
        "div.single-post-content",
        "div.entry-content",
        "div.post-content",
    ],
    "barandbench.com": [
        "div.article-content",
        "div.story-content",
        "div.entry-content",
        "div.post-content",
        ".article-body",
    ],
    "verdictum.in": [
        "div.post-content",
        "div.entry-content",
        "div.article-content",
        "div.single-post-content",
    ],
}

# Request headers to mimic a real browser (avoids 403 blocks)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MIN_ARTICLE_CHARS = 300   # below this → try next selector or fallback


def get_domain(url: str) -> str:
    """Extract bare domain from a full URL."""
    return urlparse(url).netloc.replace("www.", "")


def _clean(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _scrape_with_playwright(url: str) -> str:
    """Render the page with headless Chromium and extract visible text."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(extra_http_headers={"Accept-Language": "en-US,en;q=0.9"})
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        # Try the same site selectors on the rendered DOM
        domain = get_domain(url)
        for key, selectors in SITE_SELECTORS.items():
            if key in domain:
                for sel in selectors:
                    el = page.query_selector(sel)
                    if el:
                        text = el.inner_text()
                        if len(text) > MIN_ARTICLE_CHARS:
                            browser.close()
                            logger.info(f"Playwright extracted via: {sel}")
                            return _clean(text)

        # Generic fallback on rendered page
        for sel in ["article", "main"]:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text()
                if len(text) > MIN_ARTICLE_CHARS:
                    browser.close()
                    logger.info(f"Playwright fallback via: {sel}")
                    return _clean(text)

        # Last resort: full body
        text = page.inner_text("body")
        browser.close()
        return _clean(text)


def scrape_article(url: str) -> dict:
    """
    Fetch and parse article text from a legal news URL.

    Returns:
        {
            "url": str,
            "title": str,
            "text": str,       # full article body
            "source": str,     # domain name
            "error": str|None
        }
    """
    result = {"url": url, "title": "", "text": "", "source": "", "error": None}

    # --- Step 1: Validate URL format ---
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        result["error"] = "Invalid URL format. Please include https://"
        return result

    domain = get_domain(url)
    result["source"] = domain

    # --- Step 2: Fetch the page ---
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        result["error"] = "Could not connect. Check the URL or your internet connection."
        return result
    except requests.exceptions.Timeout:
        result["error"] = "Request timed out. The site may be slow."
        return result
    except requests.exceptions.HTTPError as e:
        result["error"] = f"HTTP error {response.status_code}: {str(e)}"
        return result

    # --- Step 3: Parse HTML ---
    soup = BeautifulSoup(response.content, "html.parser")

    title_tag = soup.find("h1")
    result["title"] = title_tag.get_text(strip=True) if title_tag else "Unknown Title"

    # --- Step 4: Try site-specific selectors in order ---
    article_text = ""

    for key, selectors in SITE_SELECTORS.items():
        if key in domain:
            for sel in selectors:
                container = soup.select_one(sel)
                if container:
                    text = container.get_text(separator="\n", strip=True)
                    if len(text) > MIN_ARTICLE_CHARS:
                        article_text = text
                        logger.info(f"Extracted via site selector: {sel}")
                        break
            break

    # --- Step 5: Generic fallback ---
    if not article_text:
        for tag in ["article", "main", '[class*="content"]', '[class*="article"]']:
            container = soup.select_one(tag)
            if container:
                text = container.get_text(separator="\n", strip=True)
                if len(text) > MIN_ARTICLE_CHARS:
                    article_text = text
                    logger.info(f"Extracted via generic selector: {tag}")
                    break

    # --- Step 6: Playwright JS-render fallback ---
    if not article_text or len(article_text) < MIN_ARTICLE_CHARS:
        logger.warning("Static scrape insufficient — trying Playwright JS render...")
        try:
            article_text = _scrape_with_playwright(url)
        except Exception as e:
            logger.warning(f"Playwright fallback failed: {e}")

    # --- Step 7: Raw body last resort ---
    if not article_text:
        body = soup.find("body")
        if body:
            article_text = body.get_text(separator="\n", strip=True)
            logger.warning("Used raw body text extraction (low quality fallback)")

    article_text = _clean(article_text)

    if len(article_text) < 100:
        result["error"] = "Could not extract sufficient article content. The page may require JavaScript."
        return result

    result["text"] = article_text
    logger.info(f"Scraped {len(article_text)} characters from {domain}")
    return result
