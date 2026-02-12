#!/usr/bin/env bash
# Quick-run script for scraping novadreams.com banners locally.
#
# Usage:
#   ./run_scrape.sh                              # banners only
#   ./run_scrape.sh --all-images                  # all images
#   ./run_scrape.sh --url https://other-site.com  # different site

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Ensure playwright is installed
if ! python3 -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
    echo "Installing playwright..."
    pip3 install --quiet playwright
    echo "Installing Chromium browser..."
    playwright install chromium --with-deps
fi

python3 "$SCRIPT_DIR/scrape_novadreams.py" "$@"
