import time 	# 랜덤 딜레이시
import random 	# 랜덤 딜레이시
import re 	# 정규 표현식
import pandas as pd # Pandas df 사용
import urllib.parse # URL 인코딩용

# Selenium 관련 Import
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# BeautifulSoup Import (HTML 파싱은 유지)
from bs4 import BeautifulSoup


# BASE URL 정의 (최상위 도메인으로 통합)
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

def get_arca_posts(channel_id: str, search_keyword: str = "", start_page: int = 1, end_page: int = 3) -> pd.DataFrame:
	"""
	아카라이브 채널 목록 및 채널 내 검색, 통합 검색(channel_id='breaking' 사용)을 Selenium을 사용하여 수행합니다.
	게시글 본문과 함께 텍스트 댓글을 수집하여 저장합니다.
	
	:param channel_id: 크롤링할 아카라이브 채널 ID (예: 'wutheringwaves' 또는 통합 검색용 'breaking', 'hotdeal')
	:param search_keyword: 검색 키워드 (선택 사항)
	:param start_page: 시작 페이지
	:param end_page: 종료 페이지
	:return: 수집된 데이터를 담은 Pandas DataFrame
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
	options.add_argument('headless') # 브라우저 창을 띄우지 않는 헤드리스 모드
	options.add_argument('disable-gpu') # GPU 사용 안 함 (헤드리스 환경에서 필요)
	options.add_argument('log-level=3') # 로그 레벨 설정 (불필요한 메시지 제거)
	
	# [중요] Headless 감지 방지를 위해 User-Agent 설정 필수
	options.add_argument(f'user-agent={random.choice(USER_AGENT_LIST)}') 
	
	driver = None
	try:
		# Selenium Manager가 자동으로 드라이버를 찾아 설치합니다.
		driver = webdriver.Chrome(options=options)
	except WebDriverException as e:
		print(f"\n❌ WebDriver 초기화 실패. Chrome 설치 및 드라이버 호환성을 확인하세요.")
		print(f"오류: {e}")
		return pd.DataFrame(data_list)
	
	is_breaking_channel = channel_id == 'breaking'

	try:
		for i in range(start_page, end_page + 1):
			
			# ----------------------
			# 1단계: 목록 페이지 요청 URL 구성 및 로딩
			# ----------------------
			
			BASE_CHANNEL_URL = f"{BASE_URL}/b/{channel_id}"
			
			# 검색어 유무에 따른 URL 파라미터 구성 분리 (사용자 요청 반영)
			if search_keyword:
				# 검색어가 있는 경우: target=all 포함
				params = {'target': 'all', 'keyword': search_keyword, 'p': i}
			else:
				# 검색어가 없는 경우 (일반 접속): 페이지만 지정 (?p=1)
				params = {'p': i}
			
			full_url = BASE_CHANNEL_URL + '?' + urllib.parse.urlencode(params)
			
			print(f"--- 채널 '{channel_id}' 목록 페이지 {i} 요청 중: {full_url} ---")
			
			# Selenium으로 페이지 로드
			driver.get(full_url)
			
			# 페이지가 완전히 로드될 때까지 명시적으로 기다림
			try:
				# 게시물 목록의 첫 번째 항목(a.vrow.column 또는 div.vrow.hybrid)이 나타날 때까지 최대 15초 대기
				WebDriverWait(driver, 15).until(
					EC.presence_of_element_located((By.CSS_SELECTOR, 'div.list-table a.vrow.column, div.list-table div.vrow.hybrid'))
				)
			except TimeoutException:
				print(f"페이지 {i} 로드 시간 초과. 유효한 게시물을 찾지 못했습니다. 크롤링 종료.")
				break
			
			# 로드된 HTML을 BeautifulSoup으로 파싱
			soup = BeautifulSoup(driver.page_source, 'lxml')
			
			# [통합 선택자 적용]
			# 1. 일반 채널 게시물 링크: a.vrow.column:not(.notice)
			# 2. 핫딜 채널 게시물 링크: div.vrow.hybrid:not(.notice) 내부의 a.hybrid-title
			# 이 두 경우 모두 href를 가진 <a> 태그를 선택하며, 공지글(.notice)은 제외합니다.
			article_list = soup.select(
				'div.list-table a.vrow.column:not(.notice), '
				'div.list-table div.vrow.hybrid:not(.notice) a.hybrid-title'
			)
			
			if not article_list:
				print(f"페이지 {i}에서 유효한 일반 게시물이 없습니다. 크롤링 종료.")
				break 

			print(f"-> 페이지 {i}에서 {len(article_list)}개의 게시물 목록 확보.")
			
			# ----------------------
			# 2단계: 개별 게시물 접근 및 내용 추출 
			# ----------------------
			for a_item in article_list:
				
				# a_item은 이제 항상 href를 가진 <a> 태그입니다.
				relative_url = a_item.get('href')
				
				# URL에서 게시물 번호(PostID) 추출
				post_id_match = re.search(r'/(\d+)(?:\?|$)', relative_url)
				
				post_id = post_id_match.group(1) if post_id_match else None

				if not post_id:
					continue
				
				# 제목 추출 (hotdeal의 경우 hybrid-title 내의 텍스트가 제목이 됩니다.)
				title_tag = a_item.select_one('span.title')
				title_raw = title_tag.get_text(strip=True) if title_tag else a_item.get_text(strip=True) # span.title이 없으면 <a> 태그 자체 텍스트 사용

				# 게시물 전체 URL
				post_full_url = BASE_URL + relative_url

				# GalleryID (채널 정보) 결정 로직
				gallery_id_for_output = channel_id 

				if is_breaking_channel:
					# 통합 검색인 경우: 배지(badge.badge-success)에서 채널 이름을 추출합니다.
					# 통합 검색 결과에서는 원본 채널 이름이 배지로 붙어 있습니다.
					badge_tag = a_item.find_parent('div').find_parent('div').select_one('span.badge.badge-success')
					if badge_tag:
						gallery_id_for_output = badge_tag.get_text(strip=True)
					else:
						gallery_id_for_output = "Unknown Channel"
				
				
				# 랜덤 딜레이
				time.sleep(random.uniform(1.5, 3.5)) 
				
				# 게시물 본문 요청
				article_contents = ""
				comments_formatted = "" # 댓글 저장 변수 초기화

				try:
					print(f" 	 -> 게시물 본문 요청: {title_raw[:20]}... (ID: {post_id}, 채널: {gallery_id_for_output})")
					driver.get(post_full_url) 
					
					# 본문 로딩 완료 대기 (div.article-content)
					WebDriverWait(driver, 10).until(
						EC.presence_of_element_located((By.CSS_SELECTOR, 'div.article-content'))
					)
					
					article_soup = BeautifulSoup(driver.page_source, 'lxml')

					# 1. 본문 추출
					article_contents_tag = article_soup.find('div', class_='article-content')
					if article_contents_tag:
						article_contents = article_contents_tag.get_text('\n', strip=True)
					
					# 2. 댓글 추출 (작성자 제외)
					comment_items = article_soup.select('div.comment-item')
					extracted_comments = []
					
					for c_item in comment_items:
						text_tag = c_item.select_one('div.message div.text pre')
						if text_tag:
							c_text = text_tag.get_text('\n', strip=True)
							if c_text:
								extracted_comments.append(c_text)
					
					# Gemini가 인식하기 좋도록 단순 번호 매기기 (예: 1. 댓글내용)
					if extracted_comments:
						comments_formatted = " ||| ".join(extracted_comments)

				except TimeoutException:
					print(f" 	 -> 게시물 본문 로드 시간 초과 ({post_full_url}). 본문/댓글 수집 건너뜁니다.")
					continue 
				except WebDriverException as e:
					print(f" 	 -> 게시물 요청 중 WebDriver 오류 ({post_full_url}): {e}")
					continue
				
				# ----------------------
				# 3단계: 데이터 클리닝 및 저장
				# ----------------------
				
				# URL 제거 (제목, 본문)
				pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$\-@\.&+:/?=]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
				repl = ''
				title_clean = re.sub(pattern=pattern, repl=repl, string=title_raw).strip()
				article_contents_clean = re.sub(pattern=pattern, repl=repl, string=article_contents).strip()
				
				# 최소한의 내용(본문)이 있어야 저장합니다.
				if article_contents_clean:
					data_list.append({
						'Site': 'ARCALIVE',
						'PostID': post_id,
						'Title': title_clean,
						'Content': article_contents_clean,
						'Comments': comments_formatted, # 포맷팅된 댓글 문자열 저장
						'GalleryID': gallery_id_for_output, 
						'PostURL': post_full_url
					})

	finally:
		if driver:
			driver.quit() # 작업 완료 후 드라이버 종료
			print("--- WebDriver 종료 ---")

	# ----------------------
	# 4단계: 리스트를 최종 DataFrame으로 변환 및 중복 제거
	# ----------------------
	df = pd.DataFrame(data_list)

	# PostID를 기준으로 중복 행 제거 
	if not df.empty:
		df = df.drop_duplicates(subset=['GalleryID', 'PostID'], keep='first')
		print(f"\n--- 크롤링 완료 및 중복 제거 ---")
		print(f"총 수집된 게시물 수 (원본): {len(data_list)}개")
		print(f"중복 제거 후 최종 게시물 수: {len(df)}개")
			
	return df