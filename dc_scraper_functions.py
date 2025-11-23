import requests
from bs4 import BeautifulSoup
import time    # 랜덤 딜레이시
import random  # 랜덤 딜레이시
import re  # 정규 표현식
import pandas as pd # Pandas df 사용

# ----------------------
# 1. 상수 정의 (PC 버전)
# ----------------------
BASE_URL = "https://gall.dcinside.com"

# User-Agent 목록 정의(랜덤선택)
USER_AGENT_LIST = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]


def get_regular_post_data(gallery_id: str, gallery_type: str = "minor", search_keyword: str = "", search_option: int = 0, start_page: int = 1, end_page: int = 3) -> pd.DataFrame:
    """
    PC 갤러리 페이지에서 게시물의 제목과 내용을 추출하여 DataFrame으로 반환합니다.
    """
    
    data_list = []

    # 갤러리 종류별 주소 설정
    if gallery_type == "minor":
        gallery_type_url = "/mgallery/board/lists"
    elif gallery_type == "major":
        gallery_type_url = "/board/lists"
    elif gallery_type == "mini":
        gallery_type_url = "/mini/board/lists"
    else:
        print("gallery_type 인자가 잘못 되었습니다. 빈 df를 반환합니다.")
        return pd.DataFrame(data_list)
    
    for i in range(start_page, end_page + 1):
        
        # ----------------------
        # 1단계: 목록 페이지 요청 및 파싱
        # ----------------------
        
        params = {'id': gallery_id, 'page': i}

        # 검색 주소 조립 시 필요한 파라미터 정의
        # ex) https://gall.dcinside.com/mgallery/board/lists/?id={GalleryID}&s_type={search_option}&s_keyword={search_keyword}
        if search_keyword:
            # PC 검색 파라미터 사용
            params['search_pos'] = ''

            # 검색 옵션 별 주소 설정
            if search_option == 0:
                params['s_type'] = 'search_subject_memo'
            elif search_option == 1:
                params['s_type'] = 'search_subject'
            elif search_option == 2:
                params['s_type'] = 'search_memo'
            else:
                print("search_option 인수가 잘못 되었습니다. 기본값인 0(제목, 내용 검색)으로 설정됩니다.")
                params['s_type'] = 'search_subject_memo'
                
            params['s_keyword'] = search_keyword

        # User-Agent 설정
        user_agent = random.choice(USER_AGENT_LIST)
        headers = {'User-Agent': user_agent}

        # try-except
        try:
            print(f"--- 갤러리 목록 페이지 {i} 요청 중 ---")
            full_url = BASE_URL + gallery_type_url
            response = requests.get(full_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"목록 페이지 {i} 요청 실패: {e}. 다음 페이지로 이동합니다.")
            time.sleep(random.uniform(2, 4))
            continue

        # lxml 파서 사용(HTML 대신)
        soup = BeautifulSoup(response.content, 'lxml')
        
        # 글 목록 구조: <tbody> 내의 <tr>
        article_list = soup.find('tbody').find_all('tr', {'data-type': ['icon_pic', 'icon_txt']})
        
        # 기본 공지, 광고글 필터링
        # 일반적으로 없어도 무관하지만 공백 검색시 포함됨
        filtered_articles = []
        for tr_item in article_list:
            writer_tag = tr_item.find('td', class_='gall_writer')
            is_operator_post = writer_tag and writer_tag.get('user_name') == '운영자'
            is_notice = tr_item.get('data-type') == 'icon_notice'
            
            if not is_operator_post and not is_notice:
                filtered_articles.append(tr_item)
                
        if not filtered_articles:
             print(f"페이지 {i}에서 유효한 일반 게시물이 없습니다. 크롤링 종료.")
             break 


        # ----------------------
        # 2단계: 개별 게시물 접근 및 내용 추출 
        # ----------------------
        for tr_item in filtered_articles:
            
            title_tag = tr_item.find('a', href=True)
            if not title_tag: continue

            title_raw = title_tag.text.strip()
            relative_url = title_tag['href']

            # 게시글 ID 저장
            post_id_match = re.search(r'&no=(\d+)', relative_url)
            post_id = post_id_match.group(1) if post_id_match else None

            # 게시글 ID 오류 시 건너뛰기
            if not post_id:
                print(f"    -> 오류: 게시물 번호 추출 실패 ({BASE_URL + relative_url}). 건너뜁니다.")
                continue
            
            # href 절대 경로/상대 경로 모두 대응 (없어도 솔직히 문제 없을듯?)
            if relative_url.startswith('http'):
                full_url = relative_url
            else:
                full_url = BASE_URL + relative_url

            # 랜덤 딜레이
            time.sleep(random.uniform(3, 5))
            
            # 게시물 본문 요청
            try:
                print(f"   -> 게시물 요청: {title_raw[:20]}...")
                article_user_agent = random.choice(USER_AGENT_LIST)
                article_headers = {'User-Agent': article_user_agent}
                article_response = requests.get(full_url, headers=article_headers, timeout=10)
                article_response.raise_for_status()
            except requests.exceptions.RequestException as e:
                print(f"   -> 게시물 요청 실패 ({full_url}): {e}")
                continue
            
            article_soup = BeautifulSoup(article_response.content, 'lxml') # lxml 사용

            # 본문 추출 클래스: 'write_div'
            article_contents_tag = article_soup.find('div', class_='write_div')
            article_contents = ""
            if article_contents_tag:
                # 텍스트만 추출
                article_contents = article_contents_tag.get_text(strip=True)
            
            # ----------------------
            # 3단계: 데이터 클리닝 및 저장
            # ----------------------
            
            # 제목과 게시글에서 url 제거
            pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$\-@\.&+:/?=]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
            repl = ''
            title_clean = re.sub(pattern=pattern, repl=repl, string=title_raw).strip()
            article_contents_clean = re.sub(pattern=pattern, repl=repl, string=article_contents).strip()
            
            # '- dc official App' 제거
            article_contents_clean = article_contents_clean.replace('- dc official App', '').strip()
            
            
            if article_contents_clean:
                data_list.append({
                    'PostID': post_id,
                    'Title': title_clean,
                    'Content': article_contents_clean,
                    'GalleryID': gallery_id,
                    'URL': full_url
                })

    # ----------------------
    # 4단계: 리스트를 최종 DataFrame으로 변환 및 중복 제거
    # ----------------------
    df = pd.DataFrame(data_list)

    # PostID를 기준으로 중복 행 제거 (페이지가 겹쳐서 재수집된 게시물 제거)
    if not df.empty:
        df = df.drop_duplicates(subset=['GalleryID', 'PostID'], keep='first')
        print(f"\n--- 크롤링 완료 및 중복 제거 ---")
        print(f"총 수집된 게시물 수: {len(data_list)}개")
        print(f"중복 제거 후 최종 게시물 수: {len(df)}개")
             
    return df