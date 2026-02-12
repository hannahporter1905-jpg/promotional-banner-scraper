#!/usr/bin/env python3
"""
Simple Promotional Banner Image Extractor
=========================================
Focused tool for extracting promotional banner images from casino/gambling sites.
No analysis, no fluff - just banner extraction.

Features:
- Firecrawl + Python fallbacks for maximum success
- Smart promotional banner detection
- Clean organized downloads
- Perfect for Claude Code integration

Usage:
    export FIRECRAWL_API_KEY="your_key"
    python banner_extractor.py https://casino-site.com
"""

import os
import sys
import argparse
import requests
import time
import re
import json
import hashlib
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Optional
from pathlib import Path
import logging

# Third-party imports
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException
    
    from PIL import Image
    from bs4 import BeautifulSoup
    
    # Firecrawl
    try:
        from firecrawl import FirecrawlApp
        FIRECRAWL_AVAILABLE = True
    except ImportError:
        FIRECRAWL_AVAILABLE = False
    
except ImportError as e:
    print(f"❌ Missing package: {e}")
    print("Install with: pip install selenium pillow beautifulsoup4 firecrawl-py requests")
    sys.exit(1)

# Simple logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SimpleBannerExtractor:
    """Simple promotional banner extractor"""
    
    def __init__(self, download_dir: str = "promotional_banners"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)
        
        # Setup Firecrawl if available
        self.firecrawl_key = os.getenv('FIRECRAWL_API_KEY')
        self.use_firecrawl = FIRECRAWL_AVAILABLE and bool(self.firecrawl_key)
        
        if self.use_firecrawl:
            self.firecrawl = FirecrawlApp(api_key=self.firecrawl_key)
            logger.info("🔥 Using Firecrawl for extraction")
        else:
            logger.info("🔧 Using Selenium for extraction")
            self._setup_selenium()
        
        # Promotional keywords for banner detection
        self.promo_keywords = [
            'bonus', 'promo', 'promotion', 'offer', 'welcome', 'deposit',
            'free', 'spin', 'jackpot', 'casino', 'bet', 'win', 'reward',
            'special', 'exclusive', 'limited', 'cashback', 'match', 'reload'
        ]
        
        # Banner size filters
        self.min_width = 200
        self.min_height = 80
        self.max_file_size = 10 * 1024 * 1024  # 10MB
    
    def _setup_selenium(self):
        """Setup Chrome WebDriver as fallback"""
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1920,1080")
            
            self.driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.warning(f"⚠️ Selenium setup failed: {e}")
            self.driver = None
    
    def extract_banners(self, url: str) -> List[str]:
        """
        Extract promotional banners and return list of downloaded file paths
        """
        site_name = urlparse(url).netloc.replace('.', '_')
        logger.info(f"🎯 Extracting promotional banners from {url}")
        
        # Try Firecrawl first, then Selenium
        if self.use_firecrawl:
            images = self._extract_with_firecrawl(url)
        else:
            images = self._extract_with_selenium(url)
        
        if not images:
            logger.warning("❌ No promotional banners found")
            return []
        
        logger.info(f"📸 Found {len(images)} promotional banners")
        
        # Download banners
        downloaded_files = self._download_banners(images, site_name)
        
        logger.info(f"✅ Downloaded {len(downloaded_files)} banners to {self.download_dir / site_name}")
        return downloaded_files
    
    def _extract_with_firecrawl(self, url: str) -> List[Dict]:
        """Extract banners using Firecrawl"""
        try:
            logger.info("🔥 Extracting with Firecrawl...")
            
            result = self.firecrawl.scrape_url(url, params={
                'formats': ['html'],
                'actions': [
                    {'type': 'wait', 'milliseconds': 3000},
                    {'type': 'scroll', 'direction': 'down'}
                ]
            })
            
            if result.get('success') and result.get('html'):
                return self._parse_html_for_banners(result['html'], url)
            else:
                logger.warning("⚠️ Firecrawl failed, trying Selenium...")
                return self._extract_with_selenium(url)
                
        except Exception as e:
            logger.warning(f"⚠️ Firecrawl error: {e}, trying Selenium...")
            return self._extract_with_selenium(url)
    
    def _extract_with_selenium(self, url: str) -> List[Dict]:
        """Extract banners using Selenium"""
        if not self.driver:
            logger.error("❌ No extraction method available")
            return []
        
        try:
            logger.info("🔧 Extracting with Selenium...")
            
            self.driver.get(url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Quick scroll to load images
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            return self._parse_html_for_banners(self.driver.page_source, url)
            
        except Exception as e:
            logger.error(f"❌ Selenium extraction failed: {e}")
            return []
    
    def _parse_html_for_banners(self, html: str, base_url: str) -> List[Dict]:
        """Parse HTML and find promotional banner images"""
        soup = BeautifulSoup(html, 'html.parser')
        banners = []
        
        # Find IMG tags
        for img in soup.find_all('img'):
            src = img.get('src')
            if not src:
                continue
            
            banner_data = {
                'url': urljoin(base_url, src),
                'alt': img.get('alt', ''),
                'title': img.get('title', ''),
                'class': ' '.join(img.get('class', [])),
                'width': self._get_dimension(img.get('width')),
                'height': self._get_dimension(img.get('height'))
            }
            
            if self._is_promotional_banner(banner_data):
                banners.append(banner_data)
        
        # Find CSS background images
        for element in soup.find_all(['div', 'section', 'header'], style=True):
            style = element.get('style', '')
            bg_match = re.search(r'background-image:\s*url\(["\']?([^"\']+)["\']?\)', style)
            
            if bg_match:
                banner_data = {
                    'url': urljoin(base_url, bg_match.group(1)),
                    'alt': '',
                    'title': '',
                    'class': ' '.join(element.get('class', [])),
                    'width': 0,
                    'height': 0
                }
                
                if self._is_promotional_banner(banner_data):
                    banners.append(banner_data)
        
        return banners
    
    def _get_dimension(self, dim_str) -> int:
        """Convert dimension string to integer"""
        if not dim_str:
            return 0
        try:
            return int(str(dim_str).replace('px', ''))
        except:
            return 0
    
    def _is_promotional_banner(self, banner: Dict) -> bool:
        """Check if image is a promotional banner"""
        # Combine all text for keyword analysis
        text = f"{banner['alt']} {banner['title']} {banner['class']} {banner['url']}".lower()
        
        # Check for promotional keywords
        has_promo_keywords = any(keyword in text for keyword in self.promo_keywords)
        
        # Size check (if dimensions known)
        width, height = banner['width'], banner['height']
        if width > 0 and height > 0:
            size_ok = width >= self.min_width and height >= self.min_height
            aspect_ratio = width / height
            is_banner_shape = 1.2 <= aspect_ratio <= 6.0  # Banner-like aspect ratios
            size_ok = size_ok and is_banner_shape
        else:
            size_ok = True  # Unknown size, rely on keywords
        
        # URL pattern check
        url_indicators = ['banner', 'promo', 'bonus', 'offer', 'campaign']
        has_promo_url = any(indicator in banner['url'].lower() for indicator in url_indicators)
        
        return (has_promo_keywords or has_promo_url) and size_ok
    
    def _download_banners(self, banners: List[Dict], site_name: str) -> List[str]:
        """Download banner images"""
        site_dir = self.download_dir / site_name
        site_dir.mkdir(exist_ok=True)
        
        downloaded_files = []
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        for i, banner in enumerate(banners, 1):
            try:
                logger.info(f"📥 Downloading banner {i}/{len(banners)}")
                
                response = session.get(banner['url'], timeout=10, stream=True)
                response.raise_for_status()
                
                # Check content type
                content_type = response.headers.get('content-type', '')
                if 'image' not in content_type:
                    continue
                
                # Check file size
                content_length = int(response.headers.get('content-length', 0))
                if content_length > self.max_file_size:
                    logger.warning(f"⚠️ Skipping large file: {content_length} bytes")
                    continue
                
                # Generate filename
                url_hash = hashlib.md5(banner['url'].encode()).hexdigest()[:8]
                ext = self._get_extension(content_type)
                filename = f"banner_{i:03d}_{url_hash}{ext}"
                filepath = site_dir / filename
                
                # Download
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Validate image
                if self._validate_image(filepath):
                    downloaded_files.append(str(filepath))
                    logger.info(f"✅ {filename}")
                    
                    # Save simple metadata
                    self._save_metadata(filepath, banner)
                else:
                    filepath.unlink()  # Delete invalid file
                
                time.sleep(0.3)  # Be nice to servers
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to download {banner['url']}: {e}")
        
        return downloaded_files
    
    def _get_extension(self, content_type: str) -> str:
        """Get file extension from content type"""
        if 'jpeg' in content_type or 'jpg' in content_type:
            return '.jpg'
        elif 'png' in content_type:
            return '.png'
        elif 'gif' in content_type:
            return '.gif'
        elif 'webp' in content_type:
            return '.webp'
        else:
            return '.jpg'
    
    def _validate_image(self, filepath: Path) -> bool:
        """Quick image validation"""
        try:
            with Image.open(filepath) as img:
                img.verify()
            return filepath.stat().st_size > 1000  # At least 1KB
        except:
            return False
    
    def _save_metadata(self, filepath: Path, banner: Dict):
        """Save simple banner metadata"""
        metadata = {
            'url': banner['url'],
            'alt': banner['alt'],
            'title': banner['title'],
            'downloaded_at': time.time()
        }
        
        metadata_file = filepath.with_suffix('.json')
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    def close(self):
        """Clean up"""
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.quit()
            except:
                pass


def main():
    """Simple CLI interface"""
    parser = argparse.ArgumentParser(
        description="Extract promotional banner images from websites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python banner_extractor.py https://casino-site.com
  
  # With Firecrawl (recommended)
  export FIRECRAWL_API_KEY="your_key"
  python banner_extractor.py https://casino-site.com
  
  # Custom output directory
  python banner_extractor.py https://casino-site.com --output my_banners
        """
    )
    
    parser.add_argument('url', help='Website URL to extract banners from')
    parser.add_argument('--output', default='promotional_banners',
                       help='Output directory for banners')
    parser.add_argument('--min-size', default='200x80',
                       help='Minimum banner size (WIDTHxHEIGHT)')
    
    args = parser.parse_args()
    
    # Parse size
    try:
        width, height = map(int, args.min_size.split('x'))
    except ValueError:
        print("❌ Invalid size format. Use WIDTHxHEIGHT (e.g., 200x80)")
        sys.exit(1)
    
    # Initialize extractor
    extractor = SimpleBannerExtractor(download_dir=args.output)
    extractor.min_width = width
    extractor.min_height = height
    
    try:
        print(f"🎯 Extracting promotional banners from {args.url}")
        
        # Extract banners
        downloaded_files = extractor.extract_banners(args.url)
        
        if downloaded_files:
            print(f"🎉 Success! Downloaded {len(downloaded_files)} promotional banners")
            print(f"📁 Check: {extractor.download_dir}")
            
            # Show first few files
            for i, filepath in enumerate(downloaded_files[:3], 1):
                filename = Path(filepath).name
                print(f"  {i}. {filename}")
            
            if len(downloaded_files) > 3:
                print(f"  ... and {len(downloaded_files) - 3} more")
        else:
            print("❌ No promotional banners found")
            print("💡 Try a different site or check if banners are visible on the page")
    
    except KeyboardInterrupt:
        print("\n⏹️ Extraction cancelled")
    except Exception as e:
        logger.error(f"💥 Extraction failed: {e}")
        sys.exit(1)
    finally:
        extractor.close()


if __name__ == "__main__":
    main()
