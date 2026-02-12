#!/usr/bin/env python3
"""
Batch Banner Extractor
======================
Extract promotional banners from multiple sites quickly.
Perfect for Claude Code batch operations.

Usage:
    python batch_banner_extractor.py --urls "site1.com,site2.com,site3.com"
    python batch_banner_extractor.py --file sites.txt
"""

import os
import sys
import argparse
import time
from pathlib import Path
from typing import List
import logging
from urllib.parse import urlparse

try:
    from banner_extractor import SimpleBannerExtractor
except ImportError:
    print("❌ banner_extractor.py not found in current directory")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BatchBannerExtractor:
    """Extract banners from multiple sites"""
    
    def __init__(self, output_dir: str = "batch_banners"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.stats = {
            'total_sites': 0,
            'successful_sites': 0,
            'failed_sites': 0,
            'total_banners': 0
        }
    
    def extract_from_urls(self, urls: List[str]) -> dict:
        """Extract banners from list of URLs"""
        self.stats['total_sites'] = len(urls)
        results = []
        
        logger.info(f"🚀 Starting batch extraction from {len(urls)} sites")
        
        extractor = SimpleBannerExtractor(download_dir=str(self.output_dir))
        
        try:
            for i, url in enumerate(urls, 1):
                logger.info(f"📍 Processing {i}/{len(urls)}: {url}")
                
                try:
                    # Ensure URL has protocol
                    if not url.startswith(('http://', 'https://')):
                        url = f"https://{url}"
                    
                    # Extract banners
                    downloaded_files = extractor.extract_banners(url)
                    
                    site_name = urlparse(url).netloc
                    result = {
                        'url': url,
                        'site_name': site_name,
                        'success': True,
                        'banners_downloaded': len(downloaded_files),
                        'files': downloaded_files
                    }
                    
                    if downloaded_files:
                        self.stats['successful_sites'] += 1
                        self.stats['total_banners'] += len(downloaded_files)
                        logger.info(f"✅ {site_name}: {len(downloaded_files)} banners")
                    else:
                        logger.warning(f"⚠️ {site_name}: No banners found")
                    
                    results.append(result)
                    
                    # Brief pause between sites
                    time.sleep(1)
                    
                except Exception as e:
                    logger.error(f"❌ {url}: {e}")
                    self.stats['failed_sites'] += 1
                    results.append({
                        'url': url,
                        'success': False,
                        'error': str(e),
                        'banners_downloaded': 0
                    })
        
        finally:
            extractor.close()
        
        # Save summary
        self._save_summary(results)
        
        return {
            'results': results,
            'stats': self.stats
        }
    
    def _save_summary(self, results: List[dict]):
        """Save batch summary"""
        summary_file = self.output_dir / "batch_summary.txt"
        
        with open(summary_file, 'w') as f:
            f.write("🎰 BATCH BANNER EXTRACTION SUMMARY\n")
            f.write("=" * 40 + "\n\n")
            
            f.write(f"📊 STATISTICS\n")
            f.write(f"Total Sites: {self.stats['total_sites']}\n")
            f.write(f"Successful: {self.stats['successful_sites']}\n")
            f.write(f"Failed: {self.stats['failed_sites']}\n")
            f.write(f"Total Banners: {self.stats['total_banners']}\n")
            f.write(f"Success Rate: {(self.stats['successful_sites']/self.stats['total_sites']*100):.1f}%\n\n")
            
            f.write("✅ SUCCESSFUL EXTRACTIONS\n")
            f.write("-" * 25 + "\n")
            for result in results:
                if result['success'] and result['banners_downloaded'] > 0:
                    f.write(f"{result['site_name']}: {result['banners_downloaded']} banners\n")
            
            f.write("\n❌ FAILED EXTRACTIONS\n")
            f.write("-" * 20 + "\n")
            for result in results:
                if not result['success']:
                    error = result.get('error', 'Unknown error')
                    f.write(f"{result['url']}: {error}\n")
        
        logger.info(f"📄 Summary saved to {summary_file}")


def load_urls_from_file(filepath: str) -> List[str]:
    """Load URLs from text file (one per line)"""
    try:
        with open(filepath, 'r') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        return urls
    except Exception as e:
        logger.error(f"❌ Failed to load file {filepath}: {e}")
        return []


def main():
    """CLI for batch banner extraction"""
    parser = argparse.ArgumentParser(
        description="Extract promotional banners from multiple sites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # From URL list
  python batch_banner_extractor.py --urls "casino1.com,casino2.com,casino3.com"
  
  # From file
  python batch_banner_extractor.py --file sites.txt
  
  # With Firecrawl
  export FIRECRAWL_API_KEY="your_key"
  python batch_banner_extractor.py --urls "site1.com,site2.com"
  
File format (sites.txt):
  casino1.com
  casino2.com  
  # This is a comment
  casino3.com
        """
    )
    
    # Input source
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--urls', help='Comma-separated list of URLs')
    input_group.add_argument('--file', help='Text file with URLs (one per line)')
    
    parser.add_argument('--output', default='batch_banners',
                       help='Output directory for all banners')
    
    args = parser.parse_args()
    
    # Load URLs
    if args.urls:
        urls = [url.strip() for url in args.urls.split(',') if url.strip()]
    else:
        urls = load_urls_from_file(args.file)
    
    if not urls:
        print("❌ No URLs provided or file is empty")
        sys.exit(1)
    
    # Check for API key
    if not os.getenv('FIRECRAWL_API_KEY'):
        logger.warning("⚠️ No FIRECRAWL_API_KEY set - using Selenium only")
        logger.info("💡 Set FIRECRAWL_API_KEY for better results")
    
    try:
        print(f"🎯 Starting batch extraction from {len(urls)} sites")
        
        # Run batch extraction
        batch_extractor = BatchBannerExtractor(output_dir=args.output)
        results = batch_extractor.extract_from_urls(urls)
        
        # Final summary
        stats = results['stats']
        print(f"\n🎉 BATCH EXTRACTION COMPLETE!")
        print(f"📊 Results: {stats['successful_sites']}/{stats['total_sites']} sites successful")
        print(f"🖼️ Total Banners: {stats['total_banners']}")
        print(f"📁 Output Directory: {batch_extractor.output_dir}")
        
        # Show top performers
        successful = [r for r in results['results'] if r['success'] and r['banners_downloaded'] > 0]
        if successful:
            successful.sort(key=lambda x: x['banners_downloaded'], reverse=True)
            print(f"\n🏆 TOP SITES:")
            for result in successful[:3]:
                print(f"  {result['site_name']}: {result['banners_downloaded']} banners")
        
    except KeyboardInterrupt:
        print("\n⏹️ Batch extraction cancelled")
    except Exception as e:
        logger.error(f"💥 Batch extraction failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
