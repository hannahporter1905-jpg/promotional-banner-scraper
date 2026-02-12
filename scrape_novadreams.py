#!/usr/bin/env python3
"""
NovaDreams Banner Scraper
=========================
Lightweight promotional banner extractor for novadreams.com.
Uses only `requests` + Python stdlib (html.parser) so it runs anywhere
without Selenium or Chrome.

Optional: install beautifulsoup4 for improved parsing.

Usage:
    python scrape_novadreams.py
    python scrape_novadreams.py --output my_banners
    python scrape_novadreams.py --all-images
"""

import os
import sys
import argparse
import hashlib
import json
import re
import time
import struct
import logging
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Tuple, Optional

try:
    import requests
except ImportError:
    print("Missing 'requests' package. Install with: pip install requests")
    sys.exit(1)

# Optional: use BeautifulSoup when available for better parsing
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TARGET_URL = "https://www.novadreams.com/"

# ---------------------------------------------------------------------------
# Stdlib HTML image extractor (no external parser needed)
# ---------------------------------------------------------------------------

class ImageHTMLParser(HTMLParser):
    """Extract image data from HTML using only the stdlib."""

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.images: List[Dict] = []
        self._current_context: List[str] = []

    def _resolve(self, url: str) -> str:
        if not url or url.startswith("data:"):
            return ""
        return urljoin(self.base_url, url)

    def handle_starttag(self, tag: str, attrs):
        attr = dict(attrs)

        # Track context (e.g. inside a <section class="banner">)
        if tag in ("div", "section", "header", "a", "figure"):
            self._current_context.append(
                f"{tag}.{attr.get('class', '')} #{attr.get('id', '')}"
            )

        # <img> tags
        if tag == "img":
            src = self._resolve(attr.get("src", ""))
            srcset = attr.get("srcset", "")
            data_src = self._resolve(attr.get("data-src", "") or attr.get("data-lazy-src", ""))
            if src or data_src:
                self.images.append({
                    "url": src or data_src,
                    "alt": attr.get("alt", ""),
                    "title": attr.get("title", ""),
                    "class": attr.get("class", ""),
                    "width": self._parse_dim(attr.get("width")),
                    "height": self._parse_dim(attr.get("height")),
                    "srcset": self._parse_srcset(srcset),
                    "context": " > ".join(self._current_context[-3:]),
                    "tag": "img",
                })

        # <source> inside <picture>
        if tag == "source":
            srcset = attr.get("srcset", "")
            for url in self._parse_srcset(srcset):
                resolved = self._resolve(url)
                if resolved:
                    self.images.append({
                        "url": resolved,
                        "alt": "",
                        "title": "",
                        "class": attr.get("class", ""),
                        "width": 0,
                        "height": 0,
                        "srcset": [],
                        "context": " > ".join(self._current_context[-3:]),
                        "tag": "source",
                    })

        # Inline background-image styles
        style = attr.get("style", "")
        if style:
            for bg_url in re.findall(r'background(?:-image)?\s*:[^;]*url\(["\']?([^"\')\s]+)["\']?\)', style):
                resolved = self._resolve(bg_url)
                if resolved:
                    self.images.append({
                        "url": resolved,
                        "alt": "",
                        "title": "",
                        "class": attr.get("class", ""),
                        "width": 0,
                        "height": 0,
                        "srcset": [],
                        "context": " > ".join(self._current_context[-3:]),
                        "tag": f"{tag}[style]",
                    })

    def handle_endtag(self, tag: str):
        if tag in ("div", "section", "header", "a", "figure") and self._current_context:
            self._current_context.pop()

    # -- helpers --
    @staticmethod
    def _parse_dim(val) -> int:
        if not val:
            return 0
        try:
            return int(str(val).replace("px", "").strip())
        except ValueError:
            return 0

    def _parse_srcset(self, srcset: str) -> List[str]:
        if not srcset:
            return []
        urls = []
        for part in srcset.split(","):
            part = part.strip()
            if part:
                url = part.split()[0]
                resolved = self._resolve(url)
                if resolved:
                    urls.append(resolved)
        return urls


# ---------------------------------------------------------------------------
# CSS background-image extractor (from <style> blocks)
# ---------------------------------------------------------------------------

def extract_css_bg_images(html: str, base_url: str) -> List[Dict]:
    """Pull background-image URLs out of <style> blocks."""
    images: List[Dict] = []
    for style_block in re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL | re.IGNORECASE):
        for match in re.finditer(
            r'([.#][\w-]+)[^{]*\{[^}]*background(?:-image)?\s*:[^;]*url\(["\']?([^"\')\s]+)["\']?\)',
            style_block,
        ):
            selector, bg_url = match.group(1), match.group(2)
            resolved = urljoin(base_url, bg_url) if not bg_url.startswith("data:") else ""
            if resolved:
                images.append({
                    "url": resolved,
                    "alt": "",
                    "title": "",
                    "class": selector,
                    "width": 0,
                    "height": 0,
                    "srcset": [],
                    "context": f"css({selector})",
                    "tag": "css-bg",
                })
    return images


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

    # Always skip known non-banner patterns
    if any(skip in url_lower for skip in SKIP_PATTERNS):
        return False

    if include_all:
        return True

    text = f"{img['alt']} {img['title']} {img['class']} {img['url']} {img['context']}".lower()

    has_keyword = any(kw in text for kw in PROMO_KEYWORDS)
    has_promo_url = any(ind in url_lower for ind in ["banner", "promo", "bonus", "offer", "campaign", "hero", "slide"])

    # Size heuristic (when known)
    w, h = img["width"], img["height"]
    size_ok = True
    if w > 0 and h > 0:
        size_ok = w >= 200 and h >= 80
        if w > 0 and h > 0:
            ratio = w / h
            size_ok = size_ok and (0.8 <= ratio <= 8.0)

    return (has_keyword or has_promo_url) and size_ok


# ---------------------------------------------------------------------------
# Image downloading & validation
# ---------------------------------------------------------------------------

# Magic bytes for common image formats
IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"RIFF": "webp",  # RIFF....WEBP
}


def detect_image_type(data: bytes) -> Optional[str]:
    """Detect image type from file header bytes."""
    for sig, fmt in IMAGE_SIGNATURES.items():
        if data[:len(sig)] == sig:
            if fmt == "webp" and data[8:12] != b"WEBP":
                continue
            return fmt
    return None


def get_image_dimensions(filepath: Path) -> Tuple[int, int]:
    """Read image dimensions from file header without PIL."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(32)

        # PNG
        if header[:4] == b"\x89PNG":
            w, h = struct.unpack(">II", header[16:24])
            return w, h

        # JPEG – scan for SOF0/SOF2 marker
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

        # GIF
        if header[:3] == b"GIF":
            w, h = struct.unpack("<HH", header[6:10])
            return w, h

    except Exception:
        pass
    return 0, 0


def download_image(session: requests.Session, url: str, dest_dir: Path, index: int) -> Optional[Dict]:
    """Download a single image and return metadata or None."""
    try:
        resp = session.get(url, timeout=15, stream=True)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type and "octet-stream" not in content_type:
            return None

        data = resp.content
        if len(data) < 500:
            return None
        if len(data) > 10 * 1024 * 1024:
            return None

        img_type = detect_image_type(data)
        if not img_type:
            # Fall back to content-type
            for ct, ext in [("jpeg", "jpg"), ("jpg", "jpg"), ("png", "png"), ("gif", "gif"), ("webp", "webp")]:
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

def fetch_page(session: requests.Session, url: str) -> str:
    """Fetch the full HTML of a page."""
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    return resp.text


def scrape_banners(url: str, output_dir: str = "novadreams_banners", all_images: bool = False) -> List[Dict]:
    """
    Scrape banner images from the given URL.

    Args:
        url: Target page URL.
        output_dir: Directory to save downloaded banners.
        all_images: If True, download all images (not just detected banners).

    Returns:
        List of metadata dicts for each downloaded image.
    """
    site_name = urlparse(url).netloc.replace(".", "_").replace(":", "_")
    dest_dir = Path(output_dir) / site_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })

    logger.info(f"Fetching {url} ...")
    html = fetch_page(session, url)
    logger.info(f"Received {len(html)} bytes of HTML")

    # --- Parse images ---
    all_found: List[Dict] = []

    if HAS_BS4:
        logger.info("Parsing with BeautifulSoup")
        soup = BeautifulSoup(html, "html.parser")

        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
            if not src or src.startswith("data:"):
                continue
            resolved = urljoin(url, src)
            parent_classes = " ".join(
                c for p in img.parents for c in (p.get("class") or [])
            )
            all_found.append({
                "url": resolved,
                "alt": img.get("alt", ""),
                "title": img.get("title", ""),
                "class": " ".join(img.get("class", [])),
                "width": ImageHTMLParser._parse_dim(img.get("width")),
                "height": ImageHTMLParser._parse_dim(img.get("height")),
                "srcset": [],
                "context": parent_classes,
                "tag": "img",
            })
            # Also grab srcset entries
            for srcset_url in ImageHTMLParser(url)._parse_srcset(img.get("srcset", "")):
                all_found.append({
                    "url": srcset_url, "alt": img.get("alt", ""), "title": "",
                    "class": "", "width": 0, "height": 0, "srcset": [],
                    "context": parent_classes, "tag": "img[srcset]",
                })

        for source in soup.find_all("source"):
            for srcset_url in ImageHTMLParser(url)._parse_srcset(source.get("srcset", "")):
                all_found.append({
                    "url": srcset_url, "alt": "", "title": "",
                    "class": "", "width": 0, "height": 0, "srcset": [],
                    "context": "", "tag": "source",
                })

        for el in soup.find_all(style=True):
            style = el.get("style", "")
            for bg_url in re.findall(r'background(?:-image)?\s*:[^;]*url\(["\']?([^"\')\s]+)["\']?\)', style):
                if not bg_url.startswith("data:"):
                    all_found.append({
                        "url": urljoin(url, bg_url), "alt": "", "title": "",
                        "class": " ".join(el.get("class", [])),
                        "width": 0, "height": 0, "srcset": [],
                        "context": el.name, "tag": f"{el.name}[style]",
                    })
    else:
        logger.info("Parsing with stdlib HTMLParser (install bs4 for better results)")
        parser = ImageHTMLParser(url)
        parser.feed(html)
        all_found.extend(parser.images)

    # CSS <style> block images
    all_found.extend(extract_css_bg_images(html, url))

    # --- Deduplicate ---
    seen_urls = set()
    unique: List[Dict] = []
    for img in all_found:
        if img["url"] not in seen_urls:
            seen_urls.add(img["url"])
            unique.append(img)

    logger.info(f"Found {len(unique)} unique images")

    # --- Filter ---
    candidates = [img for img in unique if is_banner_candidate(img, include_all=all_images)]
    label = "images" if all_images else "banner candidates"
    logger.info(f"Identified {len(candidates)} {label}")

    if not candidates:
        logger.warning("No banners found. Try --all-images to download every image.")
        return []

    # --- Download ---
    downloaded: List[Dict] = []
    for i, img in enumerate(candidates, 1):
        logger.info(f"Downloading {i}/{len(candidates)}: {img['url'][:80]}...")
        meta = download_image(session, img["url"], dest_dir, i)
        if meta:
            meta["alt"] = img.get("alt", "")
            meta["title"] = img.get("title", "")
            meta["source_tag"] = img.get("tag", "")
            meta["context"] = img.get("context", "")
            downloaded.append(meta)
            logger.info(f"  Saved {meta['filename']} ({meta['width']}x{meta['height']}, {meta['size_bytes']} bytes)")
        time.sleep(0.3)

    # --- Save manifest ---
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
        description="Scrape promotional banner images from novadreams.com",
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

    except requests.ConnectionError:
        print(f"\nCould not connect to {args.url}")
        print("Check your internet connection and that the URL is correct.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
