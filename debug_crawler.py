import sys
import os
import pandas as pd

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from src.crawler_wrapper import search_community
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

def test_dc_crawling():
    print("Testing DC Crawling...")
    # Test with a known active gallery and keyword
    # Example: MapleStory (maplestory), keyword: "메이플"
    try:
        df = search_community("dc", "메이플", 1, 1, gallery_id="maplestory")
        print(f"DC Result Count: {len(df)}")
        if not df.empty:
            print(df.head())
        else:
            print("DC Result is empty.")
    except Exception as e:
        print(f"DC Crawling Error: {e}")

def test_arca_crawling():
    print("\nTesting Arca Crawling...")
    # Test with a known active channel
    # Example: Blue Archive (bluearchive), keyword: "블아"
    try:
        df = search_community("arca", "블아", 1, 1, channel_id="bluearchive")
        print(f"Arca Result Count: {len(df)}")
        if not df.empty:
            print(df.head())
        else:
            print("Arca Result is empty.")
    except Exception as e:
        print(f"Arca Crawling Error: {e}")

if __name__ == "__main__":
    test_dc_crawling()
    test_arca_crawling()
