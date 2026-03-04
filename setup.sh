#!/bin/bash
# setup.sh — Run once on Streamlit Cloud to install Playwright browser
# This file is NOT needed locally; run `playwright install chromium` locally instead.
pip install playwright
playwright install chromium
