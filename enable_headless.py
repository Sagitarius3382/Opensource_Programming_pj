# Enable Headless Mode Script
# 이 스크립트는 브라우저 창이 팝업되지 않도록 헤드리스 모드를 활성화합니다.

import re

# DC Scraper 수정
print("DC Scraper 수정 중...")
with open("src/dc_scraper.py", 'r', encoding='utf-8') as f:
    content = f.read()

# 헤드리스 주석 해제
content = re.sub(
    r'#\s*options\.add_argument\([\'"]--headless[\'"]\)',
    "options.add_argument('--headless')",
    content
)

with open("src/dc_scraper.py", 'w', encoding='utf-8') as f:
    f.write(content)
print("✅ DC Scraper 헤드리스 모드 활성화 완료")

# Arca Scraper 수정
print("Arca Scraper 수정 중...")
with open("src/arca_scraper.py", 'r', encoding='utf-8') as f:
    content = f.read()

# 헤드리스 주석 해제
content = re.sub(
    r'#\s*options\.add_argument\([\'"]--?headless[\'"]\)',
    "options.add_argument('--headless')",
    content
)

with open("src/arca_scraper.py", 'w', encoding='utf-8') as f:
    f.write(content)
print("✅ Arca Scraper 헤드리스 모드 활성화 완료")

print("\n완료! 이제 브라우저 창이 팝업되지 않습니다.")
print("Streamlit 앱을 재시작하세요.")
