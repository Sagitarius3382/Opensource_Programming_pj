# debug.py

# 1. 필요한 함수를 모듈에서 임포트합니다.
try:
    from dc_scraper_functions import get_regular_post_data
    import pandas as pd
except ImportError as e:
    print(f"🚨 오류: 모듈 임포트 실패! 파일명을 확인하세요. ({e})")
    print("스크레이퍼 함수가 정의된 파일이 현재 디렉토리에 있는지 확인하세요.")
    exit()


def test_gallery_search(gallery_id: str, gallery_type: str, keyword: str, search_option: int = 0, end_page: int = 2):
    """
    특정 갤러리와 키워드로 스크레이퍼 함수를 호출하고 결과를 출력합니다.
    """
    print(f"\n--- [테스트 시작] 갤러리: {gallery_id}, 갤러리 타입: {gallery_type}, 키워드: '{keyword}', 검색 옵션: {search_option}, {end_page}페이지 까지 ---")
    
    # 2. 원하는 함수와 인수를 설정하여 호출합니다.
    results_df = get_regular_post_data(
        gallery_id=gallery_id, 
        gallery_type=gallery_type,
        search_keyword=keyword,
        search_option=search_option,
        start_page=1, 
        end_page=end_page
    )
    
    # 3. 결과 확인
    if results_df.empty:
        print("➡️ 수집된 게시물이 없거나 요청에 실패했습니다.")
    else:
        print(f"✅ 최종 수집된 게시물 수: {len(results_df)}개")
        print("\n--- 결과 DataFrame (상위 5개) ---")
        # DataFrame이 콘솔에 출력됩니다.
        print(results_df.head())
        
        # CSV 파일로 저장 (테스트 결과를 보존하고 싶을 때)
        file_name = f"test_{gallery_id}_{keyword}.csv"
        results_df.to_csv(file_name, index=False, encoding="utf-8-sig")
        print(f"\n💾 데이터가 {file_name} 파일로 저장되었습니다.")


def run_all_tests():
    """모든 테스트 시나리오를 순차적으로 실행합니다."""
    print("====================================")
    print("     스크레이퍼 디버그 모드 실행")
    print("====================================")
    
    # 시나리오 1: 특정 갤러리 + 키워드 검색
    gall = input("갤러리 ID 입력(ex| warship): ")
    gall_type = input("갤러리 type 입력(major, minor, mini): ")
    keyword = input("검색할 키워드 입력: ")
    search_option = int(input("검색 옵션 선택(0: 제목,내용 / 1: 제목 / 2: 내용): "))
    until = int(input("1페이지부터 몇 페이지까지 검색할지: "))

    test_gallery_search(gallery_id=gall, gallery_type=gall_type, keyword=keyword, search_option=search_option, end_page=until)

    # 시나리오 2: 통합 검색 (키워드 없음)
    #test_gallery_search(gallery_id='warship', keyword='')

if __name__ == '__main__':
    run_all_tests()