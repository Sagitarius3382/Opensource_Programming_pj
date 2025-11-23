<dc_scraper_functions.py>
  get_regular_post_data()
    gallery_id: str                // 갤러리 ID    ex) comic_new6, aion2
    gallery_type: str = "minor"    // 갤러리 타입  (major, minor, mini)
    search_keyword: str = ""       // 검색 키워드  미입력시 단순 게시글 수집
    search_option: int = 0         // 검색 옵션    0:제목+댓글 / 1:제목만 / 2:내용만
    start_page: int = 1            // 검색 시작 페이지
    end_page: int = 3              // 마지막 검색 페이지

