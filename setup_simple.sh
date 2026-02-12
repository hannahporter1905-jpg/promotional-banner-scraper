#!/bin/bash

# Simple Banner Extractor Setup
# Quick setup for promotional banner image extraction

set -e

echo "🎯 Setting up Simple Promotional Banner Extractor..."

# Check Python
python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" = "$required_version" ]; then
    echo "✅ Python $python_version is compatible"
else
    echo "❌ Python $required_version or higher required. Found: $python_version"
    exit 1
fi

# Check Chrome
if command -v google-chrome >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1; then
    echo "✅ Chrome browser found"
else
    echo "❌ Chrome browser required. Please install Google Chrome."
    exit 1
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install minimal requirements
echo "📚 Installing requirements..."
pip install --upgrade pip
pip install selenium pillow beautifulsoup4 requests firecrawl-py webdriver-manager

# Create directories
mkdir -p promotional_banners
mkdir -p batch_banners

# Make scripts executable
chmod +x banner_extractor.py
chmod +x batch_banner_extractor.py

# Create sites example file
echo "📝 Creating example sites file..."
cat > sites_example.txt << 'EOF'
# Example sites for batch extraction
# One URL per line, lines starting with # are comments

casino1.com
casino2.com
casino3.com
EOF

# Test setup
echo "🧪 Testing setup..."
python banner_extractor.py --help > /dev/null

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 Setup complete!"
    echo ""
    echo "🚀 QUICK START:"
    echo ""
    echo "1. Activate environment:"
    echo "   source venv/bin/activate"
    echo ""
    echo "2. Extract from single site:"
    echo "   python banner_extractor.py https://casino-site.com"
    echo ""
    echo "3. Extract from multiple sites:"
    echo "   python batch_banner_extractor.py --urls 'site1.com,site2.com,site3.com'"
    echo ""
    echo "4. Extract from file:"
    echo "   python batch_banner_extractor.py --file sites_example.txt"
    echo ""
    echo "💡 OPTIONAL - For better results:"
    echo "   Get Firecrawl API key: https://firecrawl.dev/"
    echo "   export FIRECRAWL_API_KEY='your_key_here'"
    echo ""
    echo "📁 Banners will be saved to: promotional_banners/ or batch_banners/"
else
    echo "❌ Setup failed during testing"
    exit 1
fi
