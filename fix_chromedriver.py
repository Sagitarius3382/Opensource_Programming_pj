# ChromeDriver Fix Patch
# 이 스크립트는 dc_scraper.py와 arca_scraper.py의 get_driver() 함수를 수정합니다.

import re

# DC Scraper 수정
dc_file = "src/dc_scraper.py"

with open(dc_file, 'r', encoding='utf-8') as f:
    content = f.read()

# get_driver 함수 찾기 및 교체
old_get_driver = '''def get_driver():
    """Selenium WebDriver 설정을 초기화하고 드라이버 객체를 반환합니다."""
    options = webdriver.ChromeOptions()
    options.add_argument('headless')  # 헤드리스 모드 (창 숨김)
    options.add_argument('window-size=1920x1080')
    options.add_argument('disable-gpu')
    options.add_argument('log-level=3')
    options.add_argument('disable-infobars')
    options.add_argument('--disable-extensions')
    
    # 봇 탐지 방지 설정
    user_agent = random.choice(USER_AGENT_LIST)
    options.add_argument(f'user-agent={user_agent}')
    
    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except WebDriverException as e:
        print(f"❌ WebDriver 초기화 실패: {e}")
        return None'''

new_get_driver = '''def get_driver():
    """Selenium WebDriver 설정을 초기화하고 드라이버 객체를 반환합니다."""
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument('window-size=1920x1080')
    options.add_argument('disable-gpu')
    options.add_argument('log-level=3')
    options.add_argument('disable-infobars')
    options.add_argument('--disable-extensions')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    user_agent = random.choice(USER_AGENT_LIST)
    options.add_argument(f'user-agent={user_agent}')
    
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)
        print("[DEBUG] DC WebDriver 초기화 성공")
        return driver
    except Exception as e:
        print(f"❌ WebDriver 초기화 실패: {e}")
        return None'''

if old_get_driver in content:
    content = content.replace(old_get_driver, new_get_driver)
    with open(dc_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ {dc_file} 수정 완료")
else:
    print(f"⚠️ {dc_file}에서 get_driver 함수를 찾을 수 없습니다")

# Arca Scraper 수정
arca_file = "src/arca_scraper.py"

with open(arca_file, 'r', encoding='utf-8') as f:
    content = f.read()

# WebDriver 초기화 부분 찾기 및 교체
old_arca_driver = '''\t# WebDriver 설정
\toptions = webdriver.ChromeOptions()
\toptions.add_argument('headless') # 브라우저 창을 띄우지 않는 헤드리스 모드
\toptions.add_argument('disable-gpu') # GPU 사용 안 함 (헤드리스 환경에서 필요)
\toptions.add_argument('log-level=3') # 로그 레벨 설정 (불필요한 메시지 제거)
\t
\t# [중요] Headless 감지 방지를 위해 User-Agent 설정 필수
\toptions.add_argument(f'user-agent={random.choice(USER_AGENT_LIST)}') 
\t
\tdriver = None
\ttry:
\t\t# Selenium Manager가 자동으로 드라이버를 찾아 설치합니다.
\t\tdriver = webdriver.Chrome(options=options)
\texcept WebDriverException as e:
\t\tprint(f"\\n❌ WebDriver 초기화 실패. Chrome 설치 및 드라이버 호환성을 확인하세요.")
\t\tprint(f"오류: {e}")
\t\treturn pd.DataFrame(data_list)'''

new_arca_driver = '''\t# WebDriver 설정
\tfrom selenium.webdriver.chrome.service import Service
\tfrom webdriver_manager.chrome import ChromeDriverManager
\t
\toptions = webdriver.ChromeOptions()
\toptions.add_argument('headless')
\toptions.add_argument('disable-gpu')
\toptions.add_argument('log-level=3')
\toptions.add_argument('--no-sandbox')
\toptions.add_argument('--disable-dev-shm-usage')
\toptions.add_argument(f'user-agent={random.choice(USER_AGENT_LIST)}')
\toptions.add_experimental_option("excludeSwitches", ["enable-automation"])
\toptions.add_experimental_option('useAutomationExtension', False)
\t
\tdriver = None
\ttry:
\t\tservice = Service(ChromeDriverManager().install())
\t\tdriver = webdriver.Chrome(service=service, options=options)
\t\tdriver.set_page_load_timeout(30)
\t\tprint("[DEBUG] Arca WebDriver 초기화 성공")
\texcept Exception as e:
\t\tprint(f"\\n❌ WebDriver 초기화 실패: {e}")
\t\treturn pd.DataFrame(data_list)'''

if old_arca_driver in content:
    content = content.replace(old_arca_driver, new_arca_driver)
    with open(arca_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ {arca_file} 수정 완료")
else:
    print(f"⚠️ {arca_file}에서 WebDriver 초기화 코드를 찾을 수 없습니다")

print("\n수정 완료! Streamlit 앱을 다시 시작하고 테스트해보세요.")
