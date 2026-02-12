#!/usr/bin/env python3
"""
NovaDreams Banner Scraper
=========================
Promotional banner extractor using Playwright (headless Chromium).
Bypasses CloudFlare and other bot protection by running a real browser.

Usage:
    python scrape_novadreams.py
    python scrape_novadreams.py --output my_banners
    python scrape_novadreams.py --all-images
    python scrape_novadreams.py --url https://www.novadreams.com/promotions
"""

import argparse
import hashlib
import json
import logging
import re
import struct
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Tuple, Optional

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("Missing 'playwright' package. Install with:")
    print("  pip install playwright && playwright install chromium")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TARGET_URL = "https://www.novadreams.com/"

# ---------------------------------------------------------------------------
# Banner filtering
# ---------------------------------------------------------------------------

PROMO_KEYWORDS = [
    "banner", "promo", "promotion", "offer", "welcome", "deposit",
    "free", "spin", "jackpot", "casino", "bet", "win", "reward",
    "special", "exclusive", "limited", "cashback", "match", "reload",
    "bonus", "hero", "slider", "carousel", "campaign", "featured",
    "cta", "signup", "sign-up", "register", "deal", "tournament",
]

SKIP_PATTERNS = [
    "favicon", "icon-", "logo-small", "pixel", "spacer",
    "1x1", "tracking", "analytics", "badge", ".svg",
    "emoji", "avatar", "flag-", "payment-", "visa", "mastercard",
]


def is_banner_candidate(img: Dict, include_all: bool = False) -> bool:
    """Decide if an image looks like a promotional banner."""
    url_lower = img["url"].lower()

    if any(skip in url_lower for skip in SKIP_PATTERNS):
        return False

    if include_all:
        return True

    text = f"{img['alt']} {img['title']} {img['class']} {img['url']} {img['context']}".lower()

    has_keyword = any(kw in text for kw in PROMO_KEYWORDS)
    has_promo_url = any(ind in url_lower for ind in [
        "banner", "promo", "bonus", "offer", "campaign", "hero", "slide"
    ])

    w, h = img["width"], img["height"]
    size_ok = True
    if w > 0 and h > 0:
        size_ok = w >= 200 and h >= 80
        ratio = w / h
        size_ok = size_ok and (0.8 <= ratio <= 8.0)

    return (has_keyword or has_promo_url) and size_ok


# ---------------------------------------------------------------------------
# Image utilities
# ---------------------------------------------------------------------------

IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"RIFF": "webp",
}


def detect_image_type(data: bytes) -> Optional[str]:
    for sig, fmt in IMAGE_SIGNATURES.items():
        if data[:len(sig)] == sig:
            if fmt == "webp" and data[8:12] != b"WEBP":
                continue
            return fmt
    return None


def get_image_dimensions(filepath: Path) -> Tuple[int, int]:
    try:
        with open(filepath, "rb") as f:
            header = f.read(32)

        if header[:4] == b"\x89PNG":
            w, h = struct.unpack(">II", header[16:24])
            return w, h

        with open(filepath, "rb") as f:
            data = f.read()
        if data[:2] == b"\xff\xd8":
            i = 2
            while i < len(data) - 9:
                if data[i] == 0xFF:
                    marker = data[i + 1]
                    if marker in (0xC0, 0xC2):
                        h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                        return w, h
                    length = struct.unpack(">H", data[i + 2 : i + 4])[0]
                    i += 2 + length
                else:
                    i += 1

        if header[:3] == b"GIF":
            w, h = struct.unpack("<HH", header[6:10])
            return w, h

    except Exception:
        pass
    return 0, 0


def _parse_dim(val) -> int:
    if not val:
        return 0
    try:
        return int(str(val).replace("px", "").strip())
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# Playwright-based page scraper
# ---------------------------------------------------------------------------

def extract_images_from_page(page, url: str) -> List[Dict]:
    """Use Playwright to extract all image data from the rendered page."""
    images = []

    # Extract <img> elements via JavaScript (gets the fully rendered DOM)
    img_data = page.evaluate("""() => {
        const imgs = [];
        for (const img of document.querySelectorAll('img')) {
            const src = img.currentSrc || img.src || img.dataset.src || img.dataset.lazySrc || '';
            if (!src || src.startsWith('data:')) continue;

            // Get parent context
            let context = '';
            let el = img.parentElement;
            const parts = [];
            for (let i = 0; i < 3 && el; i++) {
                const cls = el.className || '';
                const id = el.id || '';
                parts.unshift(`${el.tagName.toLowerCase()}.${cls} #${id}`);
                el = el.parentElement;
            }
            context = parts.join(' > ');

            imgs.push({
                url: src,
                alt: img.alt || '',
                title: img.title || '',
                className: img.className || '',
                width: img.naturalWidth || img.width || 0,
                height: img.naturalHeight || img.height || 0,
                context: context,
            });
        }
        return imgs;
    }""")

    for img in img_data:
        resolved = urljoin(url, img["url"])
        images.append({
            "url": resolved,
            "alt": img["alt"],
            "title": img["title"],
            "class": img["className"],
            "width": img["width"],
            "height": img["height"],
            "srcset": [],
            "context": img["context"],
            "tag": "img",
        })

    # Extract <source> srcset entries
    source_data = page.evaluate("""() => {
        const sources = [];
        for (const source of document.querySelectorAll('source[srcset]')) {
            const srcset = source.srcset || '';
            for (const part of srcset.split(',')) {
                const url = part.trim().split(/\\s+/)[0];
                if (url && !url.startsWith('data:')) {
                    sources.push(url);
                }
            }
        }
        return sources;
    }""")

    for src_url in source_data:
        resolved = urljoin(url, src_url)
        images.append({
            "url": resolved, "alt": "", "title": "",
            "class": "", "width": 0, "height": 0, "srcset": [],
            "context": "", "tag": "source",
        })

    # Extract background-image from inline styles
    bg_data = page.evaluate("""() => {
        const results = [];
        for (const el of document.querySelectorAll('[style]')) {
            const style = el.getAttribute('style') || '';
            const matches = style.matchAll(/background(?:-image)?\\s*:[^;]*url\\(["']?([^"')\\s]+)["']?\\)/g);
            for (const m of matches) {
                if (!m[1].startsWith('data:')) {
                    results.push({
                        url: m[1],
                        className: el.className || '',
                        tag: el.tagName.toLowerCase(),
                    });
                }
            }
        }
        return results;
    }""")

    for bg in bg_data:
        resolved = urljoin(url, bg["url"])
        images.append({
            "url": resolved, "alt": "", "title": "",
            "class": bg["className"], "width": 0, "height": 0, "srcset": [],
            "context": bg["tag"], "tag": f"{bg['tag']}[style]",
        })

    # Extract background-image from computed styles on common banner containers
    css_bg_data = page.evaluate("""() => {
        const results = [];
        const selectors = [
            '[class*="banner"]', '[class*="hero"]', '[class*="slider"]',
            '[class*="carousel"]', '[class*="promo"]', '[class*="slide"]',
            'header', 'section', '[class*="featured"]',
        ];
        const seen = new Set();
        for (const selector of selectors) {
            for (const el of document.querySelectorAll(selector)) {
                if (seen.has(el)) continue;
                seen.add(el);
                const bg = getComputedStyle(el).backgroundImage;
                if (bg && bg !== 'none') {
                    const matches = bg.matchAll(/url\\(["']?([^"')]+)["']?\\)/g);
                    for (const m of matches) {
                        if (!m[1].startsWith('data:')) {
                            results.push({
                                url: m[1],
                                className: el.className || '',
                                tag: el.tagName.toLowerCase(),
                            });
                        }
                    }
                }
            }
        }
        return results;
    }""")

    for bg in css_bg_data:
        resolved = urljoin(url, bg["url"])
        images.append({
            "url": resolved, "alt": "", "title": "",
            "class": bg["className"], "width": 0, "height": 0, "srcset": [],
            "context": f"css-computed({bg['tag']})", "tag": "css-bg",
        })

    return images


def download_image_playwright(page, url: str, dest_dir: Path, index: int) -> Optional[Dict]:
    """Download an image using the browser context (inherits cookies/session)."""
    try:
        response = page.request.get(url, timeout=15000)
        if response.status != 200:
            return None

        content_type = response.headers.get("content-type", "")
        if "image" not in content_type and "octet-stream" not in content_type:
            return None

        data = response.body()
        if len(data) < 500 or len(data) > 10 * 1024 * 1024:
            return None

        img_type = detect_image_type(data)
        if not img_type:
            for ct, ext in [("jpeg", "jpg"), ("jpg", "jpg"), ("png", "png"),
                            ("gif", "gif"), ("webp", "webp")]:
                if ct in content_type:
                    img_type = ext
                    break
        if not img_type:
            img_type = "jpg"

        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        filename = f"banner_{index:03d}_{url_hash}.{img_type}"
        filepath = dest_dir / filename
        filepath.write_bytes(data)

        w, h = get_image_dimensions(filepath)

        return {
            "file": str(filepath),
            "filename": filename,
            "url": url,
            "width": w,
            "height": h,
            "size_bytes": len(data),
            "format": img_type,
        }

    except Exception as e:
        logger.warning(f"Failed to download {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# Main scraper
# ---------------------------------------------------------------------------

def scrape_banners(url: str, output_dir: str = "novadreams_banners",
                   all_images: bool = False) -> List[Dict]:
    site_name = urlparse(url).netloc.replace(".", "_").replace(":", "_")
    dest_dir = Path(output_dir) / site_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        # Navigate and wait for page to fully load
        logger.info(f"Launching browser and navigating to {url} ...")
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
        except PlaywrightTimeout:
            logger.warning("Page load timed out, proceeding with partial content")

        # Extra wait for lazy-loaded content / JS carousels
        page.wait_for_timeout(3000)

        # Scroll down to trigger lazy loading
        logger.info("Scrolling page to trigger lazy-loaded images...")
        page.evaluate("""async () => {
            const delay = ms => new Promise(r => setTimeout(r, ms));
            for (let i = 0; i < 5; i++) {
                window.scrollBy(0, window.innerHeight);
                await delay(500);
            }
            window.scrollTo(0, 0);
        }""")
        page.wait_for_timeout(2000)

        logger.info("Extracting images from rendered page...")
        all_found = extract_images_from_page(page, url)

        # Deduplicate
        seen_urls = set()
        unique: List[Dict] = []
        for img in all_found:
            if img["url"] not in seen_urls:
                seen_urls.add(img["url"])
                unique.append(img)

        logger.info(f"Found {len(unique)} unique images")

        # Filter
        candidates = [img for img in unique if is_banner_candidate(img, include_all=all_images)]
        label = "images" if all_images else "banner candidates"
        logger.info(f"Identified {len(candidates)} {label}")

        if not candidates:
            logger.warning("No banners found. Try --all-images to download every image.")
            browser.close()
            return []

        # Download using browser context (inherits cookies, passes bot checks)
        downloaded: List[Dict] = []
        for i, img in enumerate(candidates, 1):
            logger.info(f"Downloading {i}/{len(candidates)}: {img['url'][:80]}...")
            meta = download_image_playwright(page, img["url"], dest_dir, i)
            if meta:
                meta["alt"] = img.get("alt", "")
                meta["title"] = img.get("title", "")
                meta["source_tag"] = img.get("tag", "")
                meta["context"] = img.get("context", "")
                downloaded.append(meta)
                logger.info(f"  Saved {meta['filename']} ({meta['width']}x{meta['height']}, {meta['size_bytes']} bytes)")
            time.sleep(0.3)

        browser.close()

    # Save manifest
    manifest_path = dest_dir / "manifest.json"
    manifest = {
        "source_url": url,
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_images_found": len(unique),
        "banners_downloaded": len(downloaded),
        "all_images_mode": all_images,
        "images": downloaded,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    logger.info(f"Manifest saved to {manifest_path}")

    return downloaded


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape promotional banner images using Playwright (headless Chromium)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scrape_novadreams.py
  python scrape_novadreams.py --output my_banners
  python scrape_novadreams.py --all-images
  python scrape_novadreams.py --url https://www.novadreams.com/promotions
        """,
    )
    parser.add_argument(
        "--url", default=TARGET_URL,
        help=f"Page URL to scrape (default: {TARGET_URL})",
    )
    parser.add_argument(
        "--output", default="novadreams_banners",
        help="Output directory (default: novadreams_banners)",
    )
    parser.add_argument(
        "--all-images", action="store_true",
        help="Download ALL images, not just detected banners",
    )

    args = parser.parse_args()

    print(f"Scraping banners from {args.url}")

    try:
        results = scrape_banners(args.url, output_dir=args.output, all_images=args.all_images)

        if results:
            print(f"\nSuccess! Downloaded {len(results)} banner images")
            print(f"Output: {Path(args.output).resolve()}")
            for r in results[:5]:
                print(f"  - {r['filename']}  {r['width']}x{r['height']}  {r['size_bytes']} bytes")
            if len(results) > 5:
                print(f"  ... and {len(results) - 5} more")
            print(f"\nManifest: {Path(args.output) / urlparse(args.url).netloc.replace('.', '_') / 'manifest.json'}")
        else:
            print("\nNo banner images found.")
            print("Tip: try --all-images to grab everything, or check a subpage like /promotions")

    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
