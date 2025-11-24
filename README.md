### DC 인사이드 크롤러 내부 API 가이드
    
## 환경 설정 및 설치

이 프로젝트는 Python 가상 환경을 사용하여 의존성을 관리합니다. 아래 절차를 따라 환경을 설정하세요.

1.  **가상 환경 생성**:
    ```bash
    python -m venv venv
    ```

2.  **가상 환경 활성화**:
    - Windows:
        ```bash
        .\venv\Scripts\activate
        ```
    - macOS/Linux:
        ```bash
        source venv/bin/activate
        ```

3.  **의존성 설치**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **환경 변수 설정**:
    `.env.example` 파일을 복사하여 `.env` 파일을 생성하고 필요한 API 키를 입력하세요.
    ```bash
    cp .env.example .env
    ```

-----


이 문서에서는 src/`scrapers.py` 파일에 정의된 두 가지 주요 데이터 수집 함수에 대한 사용법을 설명합니다.

-----

### 1. 갤러리 목록 검색 (`get_regular_post_data`)

특정 갤러리 내에서 일반 게시물 목록을 크롤링하고, 검색 키워드를 사용하여 결과를 필터링합니다.

#### 함수 정의

```python
def get_regular_post_data(
    gallery_id: str, 
    gallery_type: str = "minor", 
    search_keyword: str = "", 
    search_option: int = 0, 
    start_page: int = 1, 
    end_page: int = 3
) -> pd.DataFrame
```

#### 매개변수 설명

| 매개변수 | 타입 | 기본값 | 설명 |
| :--- | :--- | :--- | :--- |
| `gallery_id` | `str` | *필수* | 크롤링할 갤러리의 고유 ID (예: `comic_new6`, `aion2`). |
| `gallery_type` | `str` | `"minor"` | 갤러리 유형 (`major`, `minor`, `mini` 중 하나). |
| `search_keyword` | `str` | `""` | 검색할 키워드. 미입력 시 해당 갤러리의 단순 게시글 목록을 수집합니다. |
| `search_option` | `int` | `0` | 검색 옵션 지정.<br> **0:** 제목 + 내용 검색 (기본값)<br> **1:** 제목만 검색<br> **2:** 내용만 검색 |
| `start_page` | `int` | `1` | 검색을 시작할 페이지 번호. |
| `end_page` | `int` | `3` | 검색을 종료할 페이지 번호. |

#### 반환 값

| 타입 | 설명 |
| :--- | :--- |
| `pd.DataFrame` | 수집된 게시물 데이터(제목, 내용, ID 등)를 포함하는 Pandas DataFrame. |

-----

### 2. 통합 검색 (`get_integrated_search_data`)

DC 인사이드 통합 검색 페이지를 사용하여 전체 갤러리를 대상으로 게시물을 검색하고, 개별 게시물의 본문까지 크롤링합니다.

#### 함수 정의

```python
def get_integrated_search_data(
    search_keyword: str, 
    sort_type: str = "latest", 
    start_page: int = 1, 
    end_page: int = 3
) -> pd.DataFrame
```

#### 매개변수 설명

| 매개변수 | 타입 | 기본값 | 설명 |
| :--- | :--- | :--- | :--- |
| `search_keyword` | `str` | *필수* | 통합 검색에 사용할 키워드. |
| `sort_type` | `str` | `"latest"` | 검색 결과 정렬 방식.<br> **"latest":** 최신순 (기본값)<br> **"accuracy":** 정확도순 |
| `start_page` | `int` | `1` | 검색을 시작할 페이지 번호. |
| `end_page` | `int` | `3` | 검색을 종료할 페이지 번호. |

#### 반환 값

| 타입 | 설명 |
| :--- | :--- |
| `pd.DataFrame` | 수집된 게시물 데이터(제목, 내용, ID, 갤러리 이름 등)를 포함하는 Pandas DataFrame. |
