import time 	# 랜덤 딜레이시
import random 	# 랜덤 딜레이시
import pandas as pd # pandas는 사용하지 않지만, 기존 파일 구조를 유지하기 위해 import
import urllib.parse

# Selenium 관련 Import
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
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

def test_arca_comments(driver: webdriver.Chrome, url: str):
	"""
	지정된 게시물 URL에서 댓글을 로드하고, 텍스트가 있는 댓글만 필터링하여 출력합니다.
	"""
	print(f"--- 댓글 수집 테스트 시작: {url} ---")
	
	try:
		# 1. 페이지 로드
		driver.get(url)
		
		# 2. 댓글 영역이 로드될 때까지 대기 (div.comment-item이 나타날 때까지)
		try:
			WebDriverWait(driver, 10).until(
				EC.presence_of_element_located((By.CSS_SELECTOR, 'div.comment-item'))
			)
		except TimeoutException:
			print("댓글을 찾을 수 없거나 로딩 시간이 초과되었습니다.")
			return

		# 3. BeautifulSoup으로 파싱
		soup = BeautifulSoup(driver.page_source, 'lxml')
		
		# 4. 모든 댓글 요소 찾기
		comment_items = soup.select('div.comment-item')
		print(f"-> 총 {len(comment_items)}개의 댓글 요소 감지됨.\n")
		
		print("--- [텍스트가 포함된 댓글 목록] ---")
		
		for index, item in enumerate(comment_items, 1):
			# 작성자 정보 추출
			user_tag = item.select_one('span.user-info a')
			user_name = user_tag.get_text(strip=True) if user_tag else "익명"
			
			# 텍스트 내용 추출 (div.message > div.text > pre)
			# 제공해주신 HTML 구조상 텍스트 댓글은 <div class="text"><pre>...</pre></div> 구조를 가집니다.
			text_tag = item.select_one('div.message div.text pre')
			
			if text_tag:
				content = text_tag.get_text(strip=True)
				# 내용이 있는 경우만 출력
				if content:
					print(f"[{index}] 작성자: {user_name}")
					print(f"내용: {content}")
					print("-" * 30)
			else:
				# 텍스트 태그가 없는 경우 (이모티콘, 이미지, 비디오 등만 있는 댓글)
				# 디버깅용으로 주석 처리하거나 필요시 출력 가능
				# print(f"[{index}] (텍스트 없음 - 이모티콘/이미지 등)") 
				pass

	except WebDriverException as e:
		print(f"\n🚨 WebDriver 오류 발생: {e}")
	
	# 딜레이
	time.sleep(random.uniform(1, 2))


if __name__ == '__main__':
    
	# WebDriver 초기화
	chrome_options = Options()
	chrome_options.add_argument('--headless') 
	chrome_options.add_argument('--disable-gpu')
	chrome_options.add_argument('--log-level=3')
	chrome_options.add_argument(f'user-agent={random.choice(USER_AGENT_LIST)}')
	
	driver = None
	try:
		driver = webdriver.Chrome(options=chrome_options)

		# 테스트할 특정 게시물 URL
		TARGET_URL = "https://arca.live/b/breaking/154797102?&p=1"
		
		# 댓글 수집 함수 실행
		test_arca_comments(driver, TARGET_URL)

	except WebDriverException as e:
		print(f"\n❌ WebDriver 초기화 실패: {e}")
	finally:
		if driver:
			driver.quit()
			print("\n--- WebDriver 종료 ---")