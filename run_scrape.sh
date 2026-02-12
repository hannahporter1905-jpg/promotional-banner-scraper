#!/usr/bin/env bash
# Quick-run script for scraping novadreams.com banners locally.
#
# Usage:
#   ./run_scrape.sh                              # banners only
#   ./run_scrape.sh --all-images                  # all images
#   ./run_scrape.sh --url https://other-site.com  # different site

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Ensure requests is installed
if ! python3 -c "import requests" 2>/dev/null; then
    echo "Installing requests..."
    pip3 install --quiet requests
fi

# Optional: install bs4 for better parsing
if ! python3 -c "import bs4" 2>/dev/null; then
    echo "Installing beautifulsoup4 for better parsing..."
    pip3 install --quiet beautifulsoup4 || true
fi

python3 "$SCRIPT_DIR/scrape_novadreams.py" "$@"
