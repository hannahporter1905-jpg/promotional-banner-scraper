# 🎯 Promotional Banner Scraper

Extract promotional banner images from casino/gambling websites for reverse engineering analysis.

## 🚀 Quick Start for Claude Code
```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/promotional-banner-scraper.git
cd promotional-banner-scraper

# Setup (one-time)
chmod +x setup_simple.sh
./setup_simple.sh

# Activate environment
source venv/bin/activate

# Extract banners from single site
python banner_extractor.py https://casino-site.com

# Extract from multiple sites
python batch_banner_extractor.py --urls "site1.com,site2.com,site3.com"
```

## 🤖 Claude Code Usage Examples
```bash
# Basic extraction
claude-code "Clone promotional-banner-scraper, set it up, and extract banners from https://mega-casino.com"

# Batch extraction
claude-code "Use promotional-banner-scraper to extract banners from casino1.com, casino2.com, casino3.com"

# Custom workflow
claude-code "Clone the banner scraper, extract from bonus-palace.com, and show me the results"
```

## 📦 What's Included

- **`banner_extractor.py`** - Extract banners from single site
- **`batch_banner_extractor.py`** - Extract from multiple sites  
- **`setup_simple.sh`** - Automated setup script
- **`requirements_simple.txt`** - Python dependencies

## 🎯 Features

✅ Smart promotional banner detection  
✅ Firecrawl + Selenium fallback support  
✅ Batch processing capabilities  
✅ Clean organized output  
✅ Claude Code ready  

## 🔧 Manual Setup

If you prefer manual setup:
```bash
# Install dependencies
pip install -r requirements_simple.txt

# Extract banners
python banner_extractor.py https://your-target-site.com
```

## 🎰 Output Structure
promotional_banners/
├── casino_site_com/
│   ├── banner_001_a1b2c3d4.jpg
│   ├── banner_002_e5f6g7h8.png
│   └── banner_003_i9j0k1l2.jpg
└── batch_banners/
    ├── site1_com/
    ├── site2_com/
    └── batch_summary.txt

## 💡 Optional: Firecrawl API

For better success against bot protection:
```bash
export FIRECRAWL_API_KEY="your_key_from_firecrawl.dev"
python banner_extractor.py https://protected-casino.com
```

Perfect for reverse engineering and competitive analysis! 🚀
