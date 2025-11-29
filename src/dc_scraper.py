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
from selenium.common.exceptions import TimeoutException, WebDriverException, UnexpectedAlertPresentException

# BeautifulSoup Import
from bs4 import BeautifulSoup

# -----------------------------------------------------------
# 설정 및 상수 정의
# -----------------------------------------------------------

# robots.txt에 명시된 크롤링 금지(Disallow) 갤러리 ID 목록
DISALLOWED_IDS = {
    '47', 'singo', 'stock_new', 'cat', 'dog', 'baseball_new8', 'm_entertainer1',
    'stock_new2', 'ib_new', 'd_fighter_new1', 'produce48', 'sportsseoul', 
    'metakr', 'salgoonews', 'rezero'
}

# User-Agent 목록 정의
USER_AGENT_LIST = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

def get_driver():
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
    
    # [핵심 수정 1] 페이지 로드 전략: 'eager'
    # normal: 모든 리소스(이미지, CSS, 광고 등)가 로드될 때까지 대기 (가장 느리고 무거움)
    # eager: DOMContentLoaded 이벤트까지만 대기 (이미지 로딩 안 기다림 -> 훨씬 빠르고 가벼움)
    options.page_load_strategy = 'eager'

    # [핵심 수정 2] 강력한 리소스 차단 설정 (이미지, JS 팝업 등 차단)
    prefs = {
        "profile.managed_default_content_settings.images": 2,  # 이미지 로딩 차단 (2=Block)
        "profile.default_content_setting_values.notifications": 2, # 알림 차단
        "profile.managed_default_content_settings.stylesheets": 2, # CSS 일부 차단 (브라우저에 따라 안 먹힐 수 있음)
        "profile.managed_default_content_settings.cookies": 1,
        "profile.managed_default_content_settings.javascript": 1, # JS는 켜야 함 (1=Allow)
        "profile.managed_default_content_settings.plugins": 1,
        "profile.managed_default_content_settings.popups": 2,
        "profile.managed_default_content_settings.geolocation": 2,
        "profile.managed_default_content_settings.media_stream": 2,
    }
    options.add_experimental_option("prefs", prefs)

    user_agent = random.choice(USER_AGENT_LIST)
    options.add_argument(f'user-agent={user_agent}')
    
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    try:
        # [수정 전] 자동 설치 (이 부분을 지우거나 주석 처리)
        # service = Service(ChromeDriverManager().install())
        
        # [수정 후] 고정 경로 지정
        # 도커/리눅스 환경에서 설치된 드라이버 경로 (보통 /usr/bin/chromedriver)
        service = Service(executable_path='/usr/bin/chromedriver')
        
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)
        print("[DEBUG] DC WebDriver 초기화 성공")
        return driver
    except Exception as e:
        print(f"❌ WebDriver 초기화 실패: {e}")
        return None

def extract_comments(soup):
    """
    BeautifulSoup 객체에서 댓글을 추출하여 구분자로 연결된 문자열로 반환합니다.
    구조: <ul class="cmt_list"> -> <li class="ub-content"> -> <p class="usertxt">
    * 모델 학습/필터링을 위해 번호 없이 ' ||| ' 구분자만 사용하여 연결합니다.
    """
    comments_formatted = ""
    extracted_comments = []
    
    # 댓글 리스트 컨테이너 찾기
    cmt_list = soup.select('ul.cmt_list li.ub-content')
    
    for li in cmt_list:
        # 삭제된 댓글 등은 제외하고 실제 텍스트가 있는 경우만 추출
        txt_box = li.select_one('div.cmt_txtbox p.usertxt')
        
        if txt_box:
            c_text = txt_box.get_text('\n', strip=True)
            if c_text:
                extracted_comments.append(c_text)
                
    # 결과 포맷팅 (내용 ||| 내용)
    if extracted_comments:
        comments_formatted = " ||| ".join(extracted_comments)
        
    return comments_formatted

# -----------------------------------------------------------
# 1. 일반 갤러리 크롤링 함수 (Selenium 적용)
# -----------------------------------------------------------
def get_regular_post_data(gallery_id: str, gallery_type: str = "minor", search_keyword: str = "", search_option: int = 0, start_page: int = 1, end_page: int = 1) -> pd.DataFrame:
    
    data_list = []
    BASE_URL = "https://gall.dcinside.com"

    # 로봇 배제 확인
    if gallery_id in DISALLOWED_IDS:
        print(f"\n🚨 경고: 갤러리 ID '{gallery_id}'는 크롤링 금지 대상입니다.")
        
        data_list.append({
            'Site': 'DCINSIDE',
            'PostID': 'robots.txt disallow',
            'Title': 'robots.txt disallow',
            'Content': f"\n🚨 경고: 갤러리 ID '{gallery_id}'는 크롤링 금지 대상입니다.",
            'Comments': 'robots.txt disallow',
            'GalleryID': 'robots.txt disallow',
            'PostURL': 'robots.txt disallow'
        })
        return pd.DataFrame(data_list)

    # 갤러리 타입에 따른 URL 설정
    if gallery_type == "minor":
        board_path = "/mgallery/board/lists/"
    elif gallery_type == "major":
        board_path = "/board/lists/"
    elif gallery_type == "mini":
        board_path = "/mini/board/lists/"
    else:
        print("잘못된 갤러리 타입입니다.")
        return pd.DataFrame(data_list)

    driver = get_driver()
    if not driver:
        return pd.DataFrame(data_list)

    try:
        for i in range(int(start_page), int(end_page) + 1):
            
            # --- 1단계: 목록 페이지 URL 구성 ---
            params = {'id': gallery_id, 'page': i}
            
            if search_keyword:
                params['search_pos'] = ''
                if search_option == 0: params['s_type'] = 'search_subject_memo'
                elif search_option == 1: params['s_type'] = 'search_subject'
                elif search_option == 2: params['s_type'] = 'search_memo'
                
                params['s_keyword'] = search_keyword
            
            full_list_url = f"{BASE_URL}{board_path}?{urllib.parse.urlencode(params)}"
            print(f"--- [DC 일반] 목록 페이지 {i} 진입. 갤러리: {gallery_id}, 검색어: {search_keyword}, URL: {full_list_url} ---")
            
            try:
                driver.get(full_list_url)
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'tbody tr.ub-content'))
                )
            except (TimeoutException, UnexpectedAlertPresentException):
                print(f"[DC 일반] 목록 페이지 {i} 로딩 실패 또는 알림창 발생. 다음 페이지로 이동.")
                continue

            # BS4로 목록 파싱
            soup = BeautifulSoup(driver.page_source, 'lxml')
            article_rows = soup.select('tbody tr.ub-content')
            
            valid_rows = []
            for row in article_rows:
                # 1. data-type 기반 공지 필터링
                data_type = row.get('data-type')
                if data_type and 'icon_notice' in data_type: continue

                # 2. 작성자(운영자) 필터링
                writer_td = row.select_one('td.gall_writer')
                if writer_td:
                    if writer_td.get('user_name') == '운영자': continue
                    if writer_td.get_text(strip=True) == '운영자': continue

                # 3. 말머리(이슈, 공지 등) 필터링
                subject_td = row.select_one('td.gall_subject')
                if subject_td:
                    subject_txt = subject_td.get_text(strip=True)
                    if subject_txt == '공지': continue

                valid_rows.append(row)

            if not valid_rows:
                print(f"[DC 일반] 페이지 {i}에 수집 가능한 게시물이 없습니다.")
                continue

            print(f"-> [DC 일반] 페이지 {i}에서 {len(valid_rows)}개의 게시물 발견.")

            # --- 2단계: 개별 게시물 순회 ---
            for row in valid_rows:
                title_tag = row.select_one('a[href*="&no="]')
                if not title_tag: continue
                
                title_raw = title_tag.get_text(strip=True)
                relative_url = title_tag['href']
                
                post_id_match = re.search(r'&no=(\d+)', relative_url)
                post_id = post_id_match.group(1) if post_id_match else None
                
                if not post_id: continue
                
                if relative_url.startswith('http'):
                    post_full_url = relative_url
                else:
                    post_full_url = BASE_URL + relative_url

                # 랜덤 딜레이
                time.sleep(random.uniform(1.5, 3.5))

                # --- 3단계: 본문 및 댓글 수집 ---
                try:
                    print(f"   -> [DC 일반] 게시물 접속: {title_raw[:20]}... (ID: {post_id}, 갤러리: {gallery_id})")
                    driver.get(post_full_url)
                    
                    # 1. 가장 중요한 본문이 뜰 때까지 확실히 기다림 (필수)
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'div.write_div'))
                    )

                    # 2. 댓글 영역 로딩 대기 (선택 사항 - 타임아웃 예외 처리 필수)
                    try:
                        WebDriverWait(driver, 1).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.comment_wrap'))
                        )
                    except TimeoutException:
                        # 댓글 영역을 못 찾아도(네트워크 느림 or 구조 변경 등) 본문은 수집해야 하므로 그냥 넘어감
                        print("[DC 일반] 댓글 로딩 시간이 초과되었습니다.")
                    
                    post_soup = BeautifulSoup(driver.page_source, 'lxml')
                    
                    # A. 본문 추출
                    content_div = post_soup.find('div', class_='write_div')
                    content_text = content_div.get_text('\n', strip=True) if content_div else ""
                    
                    # B. 댓글 추출
                    comments_text = extract_comments(post_soup)
                    
                    # C. 데이터 클리닝
                    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$\-@\.&+:/?=]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
                    title_clean = re.sub(url_pattern, '', title_raw).strip()
                    content_clean = re.sub(url_pattern, '', content_text).strip()
                    content_clean = content_clean.replace('- dc official App', '').replace('- dc App', '').strip()
                    
                    if content_clean:
                        data_list.append({
                            'Site': 'DCINSIDE',
                            'PostID': post_id,
                            'Title': title_clean,
                            'Content': content_clean,
                            'Comments': comments_text,
                            'GalleryID': gallery_id,
                            'PostURL': post_full_url
                        })

                except Exception as e:
                    print(f"   -> [DC 일반] 상세 수집 실패: {e}")
                    continue

    finally:
        driver.quit()
        print("--- WebDriver 종료 ---")
    
    # 결과 DF 생성 및 중복 제거
    df = pd.DataFrame(data_list)
    if not df.empty:
        df = df.drop_duplicates(subset=['GalleryID', 'PostID'], keep='first')
        print(f"\n--- [DC 일반] 크롤링 완료 및 중복 제거 ---")
        print(f"총 수집된 게시물 수 (원본): {len(data_list)}개")
        print(f"중복 제거 후 최종 게시물 수: {len(df)}개")
        
    return df


# -----------------------------------------------------------
# 2. 통합 검색 크롤링 함수 (Selenium 적용)
# -----------------------------------------------------------
def get_integrated_search_data(search_keyword: str, sort_type: str = "latest", start_page: int = 1, end_page: int = 1) -> pd.DataFrame:
    
    data_list = []
    SEARCH_BASE_URL = "https://search.dcinside.com/post/"
    
    # 검색어 인코딩
    encoded_keyword = urllib.parse.quote(search_keyword).replace('%', '.')
    sort_path = "sort/accuracy/" if sort_type == "accuracy" else ""
    
    driver = get_driver()
    if not driver:
        return pd.DataFrame(data_list)

    try:
        for i in range(int(start_page), int(end_page) + 1):
            
            # 검색 URL 구성
            full_search_url = f"{SEARCH_BASE_URL}p/{i}/{sort_path}q/{encoded_keyword}"
            print(f"--- [DC 통합] 검색 페이지 {i} 진입. 검색어: {search_keyword} , URL: {full_search_url} ---")
            
            try:
                driver.get(full_search_url)
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'ul.sch_result_list'))
                )
            except TimeoutException:
                print(f"[DC 통합] 검색 페이지 {i} 로딩 실패. 종료.")
                break
                
            soup = BeautifulSoup(driver.page_source, 'lxml')
            result_items = soup.select('ul.sch_result_list li')
            
            if not result_items:
                print("[DC 통합] 검색 결과가 없습니다.")
                break
                
            # 결과 아이템 순회
            for item in result_items:
                link_tag = item.select_one('a.tit_txt')
                if not link_tag: continue
                
                post_url = link_tag.get('href')
                title_raw = link_tag.get_text(strip=True)
                
                # 갤러리 정보 추출
                meta_tag = item.select_one('p.link_dsc_txt.dsc_sub a.sub_txt')
                gallery_name = meta_tag.get_text(strip=True) if meta_tag else "Unknown"
                
                # 갤러리 ID 추출 (URL 파싱)
                gallery_id = "N/A"
                if meta_tag and 'id=' in meta_tag.get('href', ''):
                    gallery_id = meta_tag['href'].split('id=')[1].split('&')[0]
                
                if gallery_id in DISALLOWED_IDS:
                    continue
                    
                if 'no=' in post_url:
                    post_id = re.search(r'no=(\d+)', post_url).group(1)
                else:
                    continue

                # 상세 페이지 진입
                time.sleep(random.uniform(1.5, 3.5))
                
                try:
                    print(f"   -> [DC 통합] 검색 게시물 접속: {title_raw[:20]}... (ID: {post_id}, 갤러리: {gallery_name})")
                    driver.get(post_url)
                    
                    # 1. 가장 중요한 본문이 뜰 때까지 확실히 기다림 (필수)
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'div.write_div'))
                    )

                    # 2. 댓글 영역 로딩 대기 (선택 사항 - 타임아웃 예외 처리 필수)
                    try:
                        WebDriverWait(driver, 1).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.comment_wrap'))
                        )
                    except TimeoutException:
                        # 댓글 영역을 못 찾아도(네트워크 느림 or 구조 변경 등) 본문은 수집해야 하므로 그냥 넘어감
                        print("[DC 통합] 댓글 로딩 시간이 초과되었습니다.")
                    
                    post_soup = BeautifulSoup(driver.page_source, 'lxml')
                    
                    content_div = post_soup.find('div', class_='write_div')
                    content_text = content_div.get_text('\n', strip=True) if content_div else ""
                    
                    comments_text = extract_comments(post_soup)
                    
                    # 클리닝
                    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$\-@\.&+:/?=]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
                    title_clean = re.sub(url_pattern, '', title_raw).strip()
                    content_clean = re.sub(url_pattern, '', content_text).strip()
                    content_clean = content_clean.replace('- dc official App', '').replace('- dc App', '').strip()
                    
                    data_list.append({
                        'Site': 'DCINSIDE',
                        'PostID': post_id,
                        'Title': title_clean,
                        'Content': content_clean,
                        'Comments': comments_text,
                        'GalleryID': gallery_name,
                        'PostURL': post_url
                    })
                    
                except Exception as e:
                    print(f"   -> [DC 통합] 상세 수집 실패: {e}")
                    continue

    finally:
        driver.quit()
        print("--- 검색 WebDriver 종료 ---")
        
    df = pd.DataFrame(data_list)
    if not df.empty:
        df = df.drop_duplicates(subset=['GalleryID', 'PostID'], keep='first')
        print(f"\n--- [DC 통합] 크롤링 완료 및 중복 제거 ---")
        print(f"총 수집된 게시물 수 (원본): {len(data_list)}개")
        print(f"중복 제거 후 최종 게시물 수: {len(df)}개")
        
    return df

# -----------------------------------------------------------
# 3. [NEW] DC 통합 인터페이스 (Wrapper)
# -----------------------------------------------------------
def search_dc_inside(search_keyword: str, start_page: int = 1, end_page: int = 1, **kwargs) -> pd.DataFrame:
    """
    DC 인사이드 내의 모든 검색 요청(통합 검색 및 갤러리 검색)을 처리하는 단일 진입점입니다.
    **kwargs에 'gallery_id'가 포함되어 있으면 일반 갤러리 검색으로,
    그렇지 않으면 통합 검색으로 분기합니다.
    
    Args:
        search_keyword (str): 검색어
        start_page (int): 시작 페이지
        end_page (int): 종료 페이지
        **kwargs:
            - gallery_id (str): 갤러리 ID (존재 시 갤러리 검색)
            - gallery_type (str): 갤러리 타입 (기본 'minor')
            - search_option (int): 검색 옵션 (기본 0)
            - sort_type (str): 통합 검색 정렬 방식 (기본 'latest')
    """
    
    # 1. gallery_id가 인자에 있으면 -> 특정 갤러리 검색
    if 'gallery_id' in kwargs and kwargs['gallery_id']:
        gallery_id = kwargs['gallery_id']
        gallery_type = kwargs.get('gallery_type', 'minor')
        search_option = kwargs.get('search_option', 0)
        
        print(f"🚀 [DC Wrapper] '{gallery_id}' 갤러리 검색 모드로 진입")
        return get_regular_post_data(
            gallery_id=gallery_id,
            gallery_type=gallery_type,
            search_keyword=search_keyword,
            search_option=search_option,
            start_page=start_page,
            end_page=end_page
        )
        
    # 2. gallery_id가 없으면 -> DC 전체 통합 검색
    else:
        sort_type = kwargs.get('sort_type', 'latest')
        print(f"🚀 [DC Wrapper] 통합 검색 모드로 진입")
        return get_integrated_search_data(
            search_keyword=search_keyword,
            sort_type=sort_type,
            start_page=start_page,
            end_page=end_page
        )