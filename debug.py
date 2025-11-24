# 1. 필요한 함수를 모듈에서 임포트합니다.
try:
    # 두 크롤러 함수를 모두 임포트합니다.
    from src.dc_scraper import get_regular_post_data, get_integrated_search_data
    from src.arca_scraper import get_arca_posts
    import pandas as pd
except ImportError as e:
    print(f"🚨 오류: 모듈 임포트 실패! 파일명을 확인하세요. ({e})")
    print("스크레이퍼 함수가 정의된 파일(dc_scraper_functions.py)이 현재 디렉토리에 있는지 확인하세요.")
    exit()


def test_gallery_search(gallery_id: str, gallery_type: str, keyword: str, search_option: int = 0, end_page: int = 2):
    """
    특정 갤러리와 키워드로 get_regular_post_data 함수를 호출하고 결과를 출력합니다.
    """
    print(f"\n--- [테스트 시작] 갤러리 검색 ---")
    print(f"갤러리 ID: {gallery_id}, 타입: {gallery_type}, 키워드: '{keyword}', 옵션: {search_option}, 페이지: 1~{end_page}")
    
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
        
        # CSV 파일로 저장
        file_name = f"test_GALLERY_{gallery_id}_{keyword[:10]}.csv"
        results_df.to_csv(file_name, index=False, encoding="utf-8-sig")
        print(f"\n💾 데이터가 {file_name} 파일로 저장되었습니다.")


def test_integrated_search(keyword: str, sort_type: str = "latest", end_page: int = 2):
    """
    통합 검색 키워드로 get_integrated_search_data 함수를 호출하고 결과를 출력합니다.
    """
    print(f"\n--- [테스트 시작] 통합 검색 ---")
    print(f"키워드: '{keyword}', 정렬: {sort_type}, 페이지: 1~{end_page}")
    
    # 2. 원하는 함수와 인수를 설정하여 호출합니다.
    results_df = get_integrated_search_data(
        search_keyword=keyword,
        sort_type=sort_type,
        start_page=1, 
        end_page=end_page
    )
    
    # 3. 결과 확인
    if results_df.empty:
        print("➡️ 수집된 검색 결과가 없거나 요청에 실패했습니다.")
    else:
        print(f"✅ 최종 수집된 게시물 수: {len(results_df)}개")
        print("\n--- 결과 DataFrame (상위 5개) ---")
        # DataFrame이 콘솔에 출력됩니다.
        print(results_df.head())
        
        # CSV 파일로 저장
        file_name = f"test_INTEGRATED_{keyword[:10]}_{sort_type}.csv"
        results_df.to_csv(file_name, index=False, encoding="utf-8-sig")
        print(f"\n💾 데이터가 {file_name} 파일로 저장되었습니다.")



def test_arca_search(channel_id: str, keyword: str, end_page: int = 2):
    """
    아카라이브 채널/통합 검색으로 get_arca_posts 함수를 호출하고 결과를 출력합니다.
    """
    print(f"\n--- [테스트 시작] 아카라이브 검색 ---")
    print(f"채널 ID: {channel_id}, 키워드: '{keyword}', 페이지: 1~{end_page}")
    
    # 2. 원하는 함수와 인수를 설정하여 호출합니다.
    results_df = get_arca_posts(
        channel_id=channel_id, 
        search_keyword=keyword,
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
        
        # CSV 파일로 저장
        file_name = f"test_ARCA_{channel_id}_{keyword[:10]}.csv"
        results_df.to_csv(file_name, index=False, encoding="utf-8-sig")
        print(f"\n💾 데이터가 {file_name} 파일로 저장되었습니다.")


def run_all_tests():
    """스크레이퍼 기능을 선택하여 실행합니다."""
    print("====================================")
    print("      스크레이퍼 디버그 모드 실행     ")
    print("====================================")
    
    while True:
        try:
            choice = input("테스트할 기능 선택 (1: 갤러리 검색, 2: 통합 검색, 3: 아카라이브 검색, 0: 종료): ")
            choice = int(choice.strip())
            break
        except ValueError:
            print("❗ 잘못된 입력입니다. 1, 2, 3 또는 0을 입력해주세요.")
            continue
    
    if choice == 1:
        # 갤러리 검색 테스트 시나리오
        print("\n[--- 갤러리 검색 설정 ---]")
        gall = input("갤러리 ID 입력(ex| warship): ")
        gall_type = input("갤러리 type 입력(major, minor, mini): ")
        keyword = input("검색할 키워드 입력: ")
        # 정수 입력 예외 처리 추가
        while True:
            try:
                search_option = int(input("검색 옵션 선택(0: 제목,내용 / 1: 제목 / 2: 내용): "))
                if search_option not in [0, 1, 2]:
                    raise ValueError
                break
            except ValueError:
                print("❗ 옵션은 0, 1, 2 중 하나를 숫자로 입력해주세요.")
        
        while True:
            try:
                until = int(input("1페이지부터 몇 페이지까지 검색할지: "))
                if until < 1:
                     raise ValueError
                break
            except ValueError:
                print("❗ 페이지는 1 이상의 정수를 입력해주세요.")

        test_gallery_search(gallery_id=gall, gallery_type=gall_type, keyword=keyword, search_option=search_option, end_page=until)
    
    elif choice == 2:
        # 통합 검색 테스트 시나리오
        print("\n[--- 통합 검색 설정 ---]")
        keyword = input("검색할 키워드 입력: ")
        
        while True:
            sort_choice = input("정렬 방식 선택 (1: 최신순[latest], 2: 정확도순[accuracy]): ")
            if sort_choice == '1':
                sort_type = 'latest'
                break
            elif sort_choice == '2':
                sort_type = 'accuracy'
                break
            else:
                print("❗ 1 또는 2를 입력해주세요.")
                
        while True:
            try:
                until = int(input("1페이지부터 몇 페이지까지 검색할지: "))
                if until < 1:
                     raise ValueError
                break
            except ValueError:
                print("❗ 페이지는 1 이상의 정수를 입력해주세요.")
                
        test_integrated_search(keyword=keyword, sort_type=sort_type, end_page=until)
        
    elif choice == 3:
        # 아카라이브 검색 테스트 시나리오
        print("\n[--- 아카라이브 검색 설정 ---]")
        print("팁: 통합 검색을 원하시면 채널 ID에 'breaking'을 입력하세요.")
        channel = input("채널 ID 입력(ex| wutheringwaves, breaking): ")
        keyword = input("검색할 키워드 입력(없으면 엔터): ")
        
        while True:
            try:
                until = int(input("1페이지부터 몇 페이지까지 검색할지: "))
                if until < 1:
                     raise ValueError
                break
            except ValueError:
                print("❗ 페이지는 1 이상의 정수를 입력해주세요.")
                
        test_arca_search(channel_id=channel, keyword=keyword, end_page=until)
        
    elif choice == 0:
        print("\n테스트 프로그램을 종료합니다.")
        return
    
    else:
        print("\n선택된 기능이 없습니다.")


if __name__ == '__main__':
    run_all_tests()