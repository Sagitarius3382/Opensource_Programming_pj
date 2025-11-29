import pandas as pd
import time
from typing import Dict, Any
from .dc_scraper import search_dc_inside
from .arca_scraper import search_arca

def search_community(
    target_source: str, 
    keyword: str, 
    start_page: int = 1, 
    end_page: int = 1, 
    **kwargs: Dict[str, Any]
) -> pd.DataFrame:
    """
    여러 커뮤니티 크롤러를 아우르는 통합 진입점(Router) 함수입니다.
    
    이 함수는 'target_source'에 따라 적절한 하위 크롤러(DC 또는 Arca)를 호출하며,
    공통 인자(keyword, page) 외의 각 사이트별 고유 인자(channel_id, gallery_id 등)는 
    **kwargs를 통해 전달받아 분배합니다.
    
    Args:
        target_source (str): 검색할 커뮤니티 식별자 ('dc', 'arca').
        keyword (str): 검색어.
        start_page (int): 검색 시작 페이지 (기본값 1).
        end_page (int): 검색 종료 페이지 (기본값 1).
        **kwargs: 커뮤니티별 추가 옵션.
            - arca: 'channel_id' (기본값 'breaking')
            - dc: 'gallery_id', 'gallery_type', 'search_option', 'sort_type' 등
        
    Returns:
        pd.DataFrame: 수집된 게시물 데이터 (컬럼: Site, PostID, Title, Content, Comments, GalleryID, PostURL)
    """
    
    # 예외 발생 시 메인 프로세스(스레드 풀 등)가 중단되지 않도록 빈 DataFrame 반환
    try:
        # 1. 아카라이브 (ArcaLive)
        if target_source.lower() == 'arca':
            # search_arca 함수는 channel_id가 첫 번째 필수 인자입니다.
            # kwargs에서 추출하되, 없으면 기본값 'breaking'을 사용합니다.
            channel = kwargs.get('channel_id', 'breaking')
            
            # ArcaLive 크롤러 호출
            return search_arca(
                channel_id=channel,
                search_keyword=keyword,
                start_page=start_page,
                end_page=end_page
            )
            
        # 2. 디시인사이드 (DCInside)
        elif target_source.lower() == 'dc':
            # search_dc_inside 함수는 search_keyword가 필수이며, 
            # 나머지 옵션(gallery_id 등)은 **kwargs로 받아서 내부에서 처리합니다.
            
            # DC 크롤러 호출
            return search_dc_inside(
                search_keyword=keyword,
                start_page=start_page,
                end_page=end_page,
                **kwargs  # gallery_id, sort_type 등의 옵션 전달
            )
            
        # 3. 지원하지 않는 소스
        else:
            print(f"[Router Warning] 알 수 없는 커뮤니티 소스입니다: {target_source}")
            return pd.DataFrame()

    except Exception as e:
        print(f"[Router Error] '{target_source}' 검색 중 예외 발생: {e}")
        return pd.DataFrame()