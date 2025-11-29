import time
import random
import re
import pandas as pd
import urllib.parse

# Selenium 관련 Import
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# BeautifulSoup Import
from bs4 import BeautifulSoup


# BASE URL 정의
BASE_URL = "https://arca.live" 

# User-Agent 목록 정의(랜덤선택)
USER_AGENT_LIST = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

# robots.txt에 명시된 크롤링 금지(Disallow) 채널 ID 목록 정의
DISALLOWED_CHANNEL_IDS = {'my'} 

def extract_arca_comments(soup):
    """
    ArcaLive 게시물에서 댓글을 추출합니다.
    """
    comments_formatted = ""
    extracted_comments = []
    
    # 댓글 아이템들 찾기
    comment_items = soup.select('div.comment-item')
    
    for item in comment_items:
        # 대댓글 등을 포함하여 텍스트 영역 찾기
        text_div = item.select_one('div.message div.text')
        if text_div:
            c_text = text_div.get_text('\n', strip=True)
            
            # "삭제된 댓글입니다" 필터링
            if c_text and "삭제된 댓글입니다" not in c_text:
                extracted_comments.append(c_text)
                
    if extracted_comments:
        comments_formatted = " ||| ".join(extracted_comments)
        
    return comments_formatted

def search_arca(channel_id: str = 'breaking', search_keyword: str = "", start_page: int = 1, end_page: int = 1) -> pd.DataFrame:
    """
    아카라이브 채널 목록 및 채널 내 검색, 통합 검색(channel_id='breaking' 사용)을 Selenium을 사용하여 수행합니다.
    게시글 본문과 함께 텍스트 댓글을 수집하여 저장합니다.
    """
    
    data_list = []
    
    # robots.txt disallow 채널 필터링
    if channel_id in DISALLOWED_CHANNEL_IDS:
        print(f"\n🚨 경고: 채널 ID '{channel_id}'는 robots.txt에 의해 크롤링이 금지된 ID입니다. 작업을 중단합니다.")

        data_list.append({
            'Site': 'ARCALIVE',
            'PostID': 'robots.txt disallow',
            'Title': 'robots.txt disallow',
            'Content': f"\n🚨 경고: 채널 ID '{channel_id}'는 robots.txt에 의해 크롤링이 금지된 ID입니다. 작업을 중단합니다.",
            'Comments': 'robots.txt disallow',
            'GalleryID': 'robots.txt disallow', 
            'PostURL': 'robots.txt disallow'
        })

        return pd.DataFrame(data_list)
    
    # WebDriver 설정
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument('disable-gpu')
    options.add_argument('log-level=3')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument(f'user-agent={random.choice(USER_AGENT_LIST)}')
    
    # [최적화 1] 페이지 로드 전략: 'eager' (DOM 로드 시점까지만 대기)
    options.page_load_strategy = 'eager'

    # [최적화 2] 이미지 및 불필요한 리소스 차단
    prefs = {
        "profile.managed_default_content_settings.images": 2,  # 이미지 차단
        "profile.default_content_setting_values.notifications": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
        "profile.managed_default_content_settings.cookies": 1,
        "profile.managed_default_content_settings.javascript": 1,
        "profile.managed_default_content_settings.plugins": 1,
        "profile.managed_default_content_settings.popups": 2,
        "profile.managed_default_content_settings.geolocation": 2,
        "profile.managed_default_content_settings.media_stream": 2,
    }

    options.add_experimental_option("prefs", prefs)

    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        # eager 모드이므로 타임아웃을 20초로 단축
        driver.set_page_load_timeout(20)
        print("[DEBUG] Arca WebDriver 초기화 성공")
    except Exception as e:
        print(f"\n❌ WebDriver 초기화 실패: {e}")
        return pd.DataFrame(data_list)
    
    is_breaking_channel = channel_id == 'breaking'

    try:
        for i in range(int(start_page), int(end_page) + 1):
            
            # ----------------------
            # 1단계: 목록 페이지 요청 URL 구성 및 로딩
            # ----------------------
            
            BASE_CHANNEL_URL = f"{BASE_URL}/b/{channel_id}"
            
            # 검색어 유무에 따른 URL 파라미터 구성
            if search_keyword:
                params = {'target': 'all', 'keyword': search_keyword, 'p': i}
            else:
                params = {'p': i}
            
            full_url = BASE_CHANNEL_URL + '?' + urllib.parse.urlencode(params)
            
            print(f"--- [ARCA] 목록 페이지 {i} 진입. 채널 '{channel_id}', 검색어: {search_keyword}, URL: {full_url} ---")
            
            # Selenium으로 페이지 로드
            driver.get(full_url)
            
            # 페이지가 완전히 로드될 때까지 명시적으로 기다림
            try:
                # 게시물 목록의 첫 번째 항목(a.vrow.column 또는 div.vrow.hybrid)이 나타날 때까지 최대 15초 대기
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div.list-table a.vrow.column, div.list-table div.vrow.hybrid'))
                )
            except TimeoutException:
                print(f"[ARCA] 페이지 {i} 로드 시간 초과. 유효한 게시물을 찾지 못했습니다. 크롤링 종료.")
                break
            
            # 로드된 HTML을 BeautifulSoup으로 파싱
            soup = BeautifulSoup(driver.page_source, 'lxml')
            
            # [통합 선택자 적용]
            article_list = soup.select(
                'div.list-table a.vrow.column:not(.notice), '
                'div.list-table div.vrow.hybrid:not(.notice) a.hybrid-title'
            )
            
            if not article_list:
                print(f"[ARCA] 페이지 {i}에서 유효한 일반 게시물이 없습니다. 크롤링 종료.")
                break 

            print(f"-> [ARCA] 페이지 {i}에서 {len(article_list)}개의 게시물 목록 확보.")
            
            # ----------------------
            # 2단계: 개별 게시물 접근 및 내용 추출 
            # ----------------------
            for a_item in article_list:
                
                relative_url = a_item.get('href')
                
                # URL에서 게시물 번호(PostID) 추출
                post_id_match = re.search(r'/(\d+)(?:\?|$)', relative_url)
                post_id = post_id_match.group(1) if post_id_match else None

                if not post_id: continue
                
                # 제목 추출
                title_tag = a_item.select_one('span.title')
                title_raw = title_tag.get_text(strip=True) if title_tag else a_item.get_text(strip=True)

                # 게시물 전체 URL
                post_full_url = BASE_URL + relative_url

                # GalleryID (채널 정보) 결정 로직
                gallery_id_for_output = channel_id 
                
                if is_breaking_channel:
                    # 현재 행(a_item) 내부에서 배지 찾기
                    badge_tag = a_item.select_one('span.badge')
                    if badge_tag:
                        gallery_id_for_output = badge_tag.get_text(strip=True)
                    else:
                        gallery_id_for_output = "Unknown Channel"
                
                time.sleep(random.uniform(1.5, 3.5)) 
                
                # 게시물 본문 요청
                article_contents = ""
                comments_formatted = ""

                try:
                    print(f"    -> [ARCA] 게시물 본문 요청: {title_raw[:20]}... (ID: {post_id}, 채널: {gallery_id_for_output})")
                    driver.get(post_full_url) 
                    
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'div.article-content'))
                    )

                    # 댓글 영역이 로드될 때까지 대기 (div.comment-item이 나타날 때까지)
                    try:
                        WebDriverWait(driver, 1).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'div#comment'))
                        )
                    except TimeoutException:
                        print("[ARCA] 댓글 로딩 시간이 초과되었습니다.")
                    
                    article_soup = BeautifulSoup(driver.page_source, 'lxml')

                    # 1. 본문 추출
                    article_contents_tag = article_soup.find('div', class_='article-content')
                    if article_contents_tag:
                        article_contents = article_contents_tag.get_text('\n', strip=True)
                    
                    # 2. 댓글 추출
                    comments_formatted = extract_arca_comments(article_soup)

                except TimeoutException:
                    print(f"    -> [ARCA] 게시물 본문 로드 시간 초과 ({post_full_url}). 본문/댓글 수집 건너뜁니다.")
                    continue 
                except Exception as e:
                    print(f"    -> [ARCA] 게시물 요청 중 오류 ({post_full_url}): {e}")
                    continue
                
                # ----------------------
                # 3단계: 데이터 클리닝 및 저장
                # ----------------------
                
                pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$\-@\.&+:/?=]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
                repl = ''
                title_clean = re.sub(pattern=pattern, repl=repl, string=title_raw).strip()
                article_contents_clean = re.sub(pattern=pattern, repl=repl, string=article_contents).strip()
                
                if article_contents_clean:
                    data_list.append({
                        'Site': 'ARCALIVE',
                        'PostID': post_id,
                        'Title': title_clean,
                        'Content': article_contents_clean,
                        'Comments': comments_formatted,
                        'GalleryID': gallery_id_for_output, 
                        'PostURL': post_full_url
                    })

    finally:
        if driver:
            driver.quit()
            print("--- WebDriver 종료 ---")

    # ----------------------
    # 4단계: 리스트를 최종 DataFrame으로 변환 및 중복 제거
    # ----------------------
    df = pd.DataFrame(data_list)

    # PostID를 기준으로 중복 행 제거 
    if not df.empty:
        df = df.drop_duplicates(subset=['GalleryID', 'PostID'], keep='first')
        print(f"\n--- [ARCA] 크롤링 완료 및 중복 제거 ---")
        print(f"총 수집된 게시물 수 (원본): {len(data_list)}개")
        print(f"중복 제거 후 최종 게시물 수: {len(df)}개")
            
    return df