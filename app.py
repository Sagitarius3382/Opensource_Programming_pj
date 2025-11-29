import os
import json
import time
import re
import pandas as pd
import streamlit as st
import google.generativeai as genai
import concurrent.futures
import altair as alt  # 원형 그래프 생성을 위한 시각화 라이브러리
from dotenv import load_dotenv

# --------------------------------------------------------------------------
# 1. 초기 설정 및 환경 변수 로드
# --------------------------------------------------------------------------
load_dotenv()

st.set_page_config(
    page_title="휴머니티 인사이드",
    page_icon="🕵️‍♂️",
    layout="wide"
)

# 새로운 모듈 임포트
try:
    from src.crawler_wrapper import search_community
    from src.preprocessor import filter_hate_speech
except ImportError as e:
    # 외부 모듈이 없을 경우, Streamlit 앱 실행을 위해 더미 함수로 대체
    def search_community(*args, **kwargs):
        # st.error(f"Crawler module missing. Cannot execute search for {target} - {keyword}")
        return pd.DataFrame({'Title': [f"Dummy Title - No Crawler"], 'PostUrl': ['#'], 'Content': ['Dummy content. Please install src modules.']})
    def filter_hate_speech(df):
        return df
    # st.error(f"필수 모듈을 임포트하는 중 오류가 발생했습니다: {e}")
    # st.stop()


# --------------------------------------------------------------------------
# 2. 사이드바 설정 (API 상태 표시)
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("📍 Status")
    
    api_key = os.getenv("API_KEY")
    model_name = os.getenv("MODEL")

    if api_key and model_name:
        st.success("🟢 API 연동 정상")
        st.markdown(f"**사용 모델:** `{model_name}`")
    else:
        st.error("🔴 API 연동 실패")
        if not api_key:
            st.warning("API 키가 누락되었습니다. '.env' 파일을 확인해주세요.")
        if not model_name:
            st.warning("모델 설정이 누락되었습니다. '.env' 파일을 확인해주세요.")
        
    st.markdown("---")
    st.info("AI가 사용자의 질문을 분석하여 자동으로 커뮤니티(DC/Arca)를 선정하고 데이터를 수집합니다.")
    st.info("Tip) 디시인사이드 검색의 기본값은 통합검색이지만, 갤러리 검색을 원할 경우 채널 id와 함께 지정할 수 있습니다. (예: 헤드폰 마이너 갤러리(id=newheadphone)에서 검색해줘.)")
    st.info("Tip) 디시인사이드 통합검색의 기본값은 최신순이지만, 정확도 순으로 검색해달라고 하면 정확도순으로 설정됩니다.")
    st.caption("Powered by Google Gemini")

# --------------------------------------------------------------------------
# 3. Gemini 모델 로드 
# --------------------------------------------------------------------------
@st.cache_resource
def get_gemini_model():
    """
    Gemini 모델 로드 (캐싱 적용)
    """
    YOUR_API_KEY = os.getenv("API_KEY")
    if not YOUR_API_KEY:
        st.stop()

    YOUR_MODEL = os.getenv("MODEL")
    if not YOUR_MODEL:
        st.stop()
        
    genai.configure(api_key=YOUR_API_KEY)
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    
    return genai.GenerativeModel(YOUR_MODEL, safety_settings=safety_settings)

# --------------------------------------------------------------------------
# 4. 핵심 로직 함수 
# --------------------------------------------------------------------------

def get_search_plan(user_input):
    """
    사용자의 질문을 분석하여 검색 계획을 수립합니다.
    """
    model = get_gemini_model()
    
    system_instruction = """
    너는 인터넷 커뮤니티의 문화와 은어에 통달한 '커뮤니티 키워드 검색을 위한 커뮤니티 트렌드/은어 전문가'야. 
    사용자의 질문을 분석해서 어떤 커뮤니티(DCInside, ArcaLive 둘 중 하나)를 어떤 키워드로 검색할지 구체적인 계획을 세워줘.
    
    [필수 규칙]
    1. 사용자가 "여론", "반응", "평가" , "의견" , "근황" 등 키워드 검색이 가능한 것을 물으면 mode="search"로 설정해.
    2. **[검색어(keyword) 선정 핵심]** - 공식 명칭보다 **커뮤니티에서 실제로 쓰이는 '약칭', '줄임말', '은어'**를 최우선으로 선택해. (예: 갤럭시 S25 -> S25, 블루 아카이브 -> 블아/몰루, 리그오브레전드 -> 롤)
    3. **[타겟 선정]** 특정 사이트 언급이 없으면, 해당 주제가 활발한 곳을 자동으로 판단하되 **잘 모르겠거나 대중적인 게임/이슈라면 ["dc", "arca"] 두 곳에 대해 task를 총 2개 생성해야해.**
    4. **task['options']의 'gallery_id'와 'gallery_type'는 사용자가 특별히 갤러리를 지정하지 않는 이상 null 값이야(통합검색 이용).**
    5. 응답은 반드시 아래 JSON 형식에 맞춰서 반환해줘.

    [mode 판단 기준]
    1. "search": 특정 게임, 인물, 사건 등 키워드 검색이 가능한 주제에 대해 묻는 경우.
    2. "clarify": 키워드가 너무 모호해서(예: '헤르타'가 작가 헤르타 뮐러인지, 축구팀 헤르타 BSC인지, 붕괴 스타레일 게임의 등장인물 헤르타인지 불분명함) 검색 대상을 확정할 수 없는 경우.
    3. "chat": 단순 인사, 잡담, 혹은 분석과 관련 없는 대화.

    [JSON 출력 형식]
    {
        "mode": "search" | "clarify" | "chat", 
        "reply_message": "clarify" | "chat" 모드일 때 사용자에게 할 말,
        "tasks": [
            {
                "target_source": "dc" | "arca",
                "keyword": "검색효율이 가장 좋은 최적의 단어(은어/줄임말 권장). 불필요한 조사(은/는/이/가/을/를/의/도)는 제거하고 명사 위주로 구성.",
                "options": {
                    # dc, arca 공통 파라미터
                    "end_page": "종료 페이지 (커뮤니티 하나만 탐색할 때는 '2', 두 곳 모두(len(tasks) == 2)일 때는 '1')",

                    # "target_source" == "dc" 일 때 입력할 내용
                    "gallery_id": "기본값은 null. 사용자 요청이 있을 시 키워드를 검색할 갤러리의 갤러리 ID (예: 'maplestory_new', 'leagueoflegends6', 'chzzk').",
                    "gallery_type": "기본값은 null. 사용자의 요청이 있을 시 gallery_id값에 해당하는 갤러리의 종류를 기재. ('major' | 'minor').", 
                    "sort_type": 기본값은 "latest". 사용자의 '정확도 순' 요청이 있을 시 "accuracy".

                    # "target_source" == "arca" 일 때 입력할 내용
                    "channel_id": "breaking" (항상 통합검색 사용),
                }
            }
        ]
    }
    """
    
    try:
        response = model.generate_content(
            f"{system_instruction}\n\nUser Input: {user_input}",
            generation_config={"response_mime_type": "application/json"}
        )
        if response.parts:
            return json.loads(response.text)
        else:
            return {"mode": "chat", "reply_message": "죄송합니다. 계획을 수립하는 중 문제가 발생했습니다.", "tasks": []}
    except Exception as e:
        return {"mode": "chat", "reply_message": f"오류가 발생했습니다: {str(e)}", "tasks": []}

def execute_crawling(tasks):
    """
    수립된 계획(tasks)을 병렬로 실행하여 데이터를 수집합니다.
    """
    all_results = []
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_task = {}
        for task in tasks:
            target = task.get("target_source")
            keyword = task.get("keyword")
            options = task.get("options", {})
            
            # 디버깅: 전달되는 파라미터 출력
            print(f"[DEBUG] Crawling Task: {target} - {keyword}")
            future = executor.submit(search_community, target, keyword, **options)
            future_to_task[future] = task

        # [수정] 모든 태스크가 '완전히' 끝날 때까지 명시적으로 대기 (wait)
        # return_when=ALL_COMPLETED를 사용하여 하나라도 실행 중이면 넘어가지 않음
        if future_to_task:
            concurrent.futures.wait(future_to_task.keys(), return_when=concurrent.futures.ALL_COMPLETED)
            
        # 모든 작업이 완료된 후 결과 수집
        for future in future_to_task:
            try:
                df = future.result()
                current_task = future_to_task[future]
                print(f"[DEBUG] Crawling result for {current_task.get('target_source')}: {len(df)} rows")
                if not df.empty:
                    df["Source"] = current_task.get("target_source")
                    df["Keyword"] = current_task.get("keyword")
                    all_results.append(df)
                else:
                    print(f"[DEBUG] Empty DataFrame returned for {current_task.get('target_source')}")

            except Exception as e:
                print(f"[DEBUG] Error: {e}", flush=True)

    if all_results:
        # [수정] 여러 소스의 데이터를 고르게 섞기 (Interleaving)
        # 각 데이터프레임에 순위(Rank)를 매겨서, 1등끼리, 2등끼리 모이도록 정렬
        for df in all_results:
            df['__rank'] = range(len(df))
        
        final_df = pd.concat(all_results, ignore_index=True)
        # Rank 기준으로 정렬하여 소스 간 균형 맞춤 (예: DC 1위 -> Arca 1위 -> DC 2위 ...)
        final_df = final_df.sort_values('__rank').drop(columns=['__rank']).reset_index(drop=True)
        
        return final_df
    else:
        return pd.DataFrame()

def generate_report(user_input, df):
    model = get_gemini_model()
    
    if df.empty: return None
        
    summary_text = ""
    cols = {c.lower(): c for c in df.columns}
    title_col = cols.get('title', 'Title')
    content_col = cols.get('content', 'Content')

    # 인덱스 1부터 시작 (30개 제한)
    for i, (idx, row) in enumerate(df.head(30).iterrows()):
        title = row.get(title_col, "No Title")
        # 본문 150자 제한 (이미 잘려있겠지만 안전장치 및 프롬프트 최적화)
        content = str(row.get(content_col, ""))[:150]
        # ID를 1부터 시작하는 순번으로 매핑하여 프롬프트에 전달
        summary_text += f"[ID: {i + 1}] {title}: {content}\n"
        
    prompt = f"""
    당신은 커뮤니티 여론 분석 전문가입니다.
    
    [사용자 질문]
    {user_input}
    
    [수집된 데이터 요약 (ID 포함)]
    {summary_text}
    
    위 데이터를 바탕으로 상세한 보고서를 작성해주세요.

    **🔥 [중요 지침] 🔥**
    보고서의 문장이나 핵심적인 여론(긍정/부정 요소)을 언급할 때는, 해당 내용의 근거가 된 [수집된 데이터 요약]의 **게시물 ID를 반드시 괄호 안에 [ID] 형태로 명시**해 주세요.
    * **예시:** "대부분의 유저가 인터페이스의 편의성을 높이 평가했습니다 [1, 5, 10]."
    * **예시:** "가격 정책에 대한 불만이 다수 제기되었습니다 [2, 4, 11]."
    
    [보고서 포함 항목]
    1. **3줄 요약**: 전체적인 여론의 핵심 요약
    2. **긍정 여론**: 유저들이 긍정적으로 평가하는 요소
    3. **부정 여론**: 유저들이 불만이나 비판을 제기하는 요소
    4. **주요 논쟁**: 현재 가장 뜨거운 감자나 논쟁거리
    5. **종합 평가**: 결론 및 제언
    
    [특별 지시사항 - 데이터 구조]
    **중요:** 보고서 본문 작성이 모두 끝나면, 반드시 `__REF_DATA__` 라는 구분자를 출력하고, 그 뒤에 **JSON 형식**으로 아래 정보들을 출력해주세요.
    
    1. **reference_ids**: 분석에 가장 영양가가 높았던 글의 ID (최대 3개, 숫자 리스트)
    2. **sentiment_counts**: 전체(최대 30개) 글에 대한 감성 분석 통계. 각각의 글에 대해 ("Positive"|"Negative"|"Neutral")을 판단함. (긍정 부정 판단이 불가능할 경우에는 "Neutral"로 판단)
    3. **topic_counts**: 전체(최대 30개) 글에서 주로 다뤄진 상위 키워드(한국어로 작성) 3~5개와 그 빈도수
    
    __REF_DATA__
    {{
        "reference_ids": [1, 5, 10],
        "sentiment_counts": {{ "Positive": 12, "Negative": 8, "Neutral": 10 }},
        "topic_counts": {{ "게임플레이": 15, "스토리": 8, "운영": 7 }}
    }}
    """
    
    return model.generate_content(prompt, stream=True)

# ==========================================================================
# 5. 메인 로직 
# ==========================================================================

# [CSS] 스타일 병합 (기존 레이아웃 CSS + 협업자 CSS)
st.markdown("""
<style>
    /* 협업자 추가 스타일 */
    .main-header {
        font-size: 2.5rem !important;
        font-weight: 700 !important;
        color: #333399 !important;
        margin-bottom: 0px !important;
    }
    .sub-header {
        font-size: 1.1rem !important;
        color: #666 !important;
        margin-top: -10px !important;
        margin-bottom: 20px !important;
    }
    div.stButton > button {
        width: 100% !important;
        border-radius: 20px !important;
        border: 1px solid #ddd !important;
    }
    /* 다크모드/라이트모드 대응 텍스트 컬러 조정 (옵션) */
    @media (prefers-color-scheme: dark) {
        .main-header { color: #8080ff !important; }
        .sub-header { color: #cccccc !important; }
    }
    </style>
""", unsafe_allow_html=True)

# [Header] 협업자 디자인 적용
st.markdown("""
    <div style="text-align: left;">
        <h1 class="main-header">🌏 휴머니티 인사이드 🔍</h1>
        <p class="sub-header">커뮤니티의 인간미 넘치는(Humanity) 이용자(Inside)의 솔직한 글을 바탕으로, 진정성 있는 정보를 제공합니다</p>
    </div>
    <hr style="margin-top: 0; margin-bottom: 30px;">
""", unsafe_allow_html=True)

# [Session State] 초기화
if "search_history" not in st.session_state:
    st.session_state.search_history = []  # 검색 기록을 저장할 리스트
if "current_view_index" not in st.session_state:
    st.session_state.current_view_index = -1 # 현재 보고 있는 검색 기록의 인덱스

if "messages" not in st.session_state:
    st.session_state.messages = []
    # 협업자 환영 메시지 적용
    welcome_msg = "안녕하세요! 궁금한 게임, 인물, 이슈 등을 물어봐주세요. 제가 커뮤니티의 관련 내용을 종합해드릴게요!"
    st.session_state.messages.append({"role": "assistant", "content": welcome_msg})

# --- 화면 레이아웃 분할 (좌: 채팅 / 우: 통계) ---
chat_col, stat_col = st.columns([0.6, 0.4], gap="large")

# 대시보드 Placeholder
dashboard_placeholder = stat_col.empty()

# [우측] 통계 대시보드 렌더링 함수
def render_stats_dashboard():
    with dashboard_placeholder.container():
        st.markdown("### 📈 실시간 여론 대시보드")
        
        # 검색 기록이 없으면 안내 메시지 출력
        if not st.session_state.search_history:
            st.info("데이터가 수집되면 통계가 표시됩니다.")
            return

        # 현재 인덱스 유효성 검사 및 보정
        if st.session_state.current_view_index < 0 or st.session_state.current_view_index >= len(st.session_state.search_history):
             st.session_state.current_view_index = len(st.session_state.search_history) - 1
        
        idx = st.session_state.current_view_index
        history_item = st.session_state.search_history[idx]
        
        # [네비게이션 UI] 이전/다음 버튼 및 현재 상태 표시
        nav_col1, nav_col2, nav_col3 = st.columns([0.2, 0.6, 0.2])
        
        with nav_col1:
            if idx > 0:
                # 이전 버튼: 인덱스 감소 callback
                st.button("◀", key=f"prev_{idx}", on_click=lambda: setattr(st.session_state, 'current_view_index', idx - 1))
        
        with nav_col3:
            if idx < len(st.session_state.search_history) - 1:
                # 다음 버튼: 인덱스 증가 callback
                st.button("▶", key=f"next_{idx}", on_click=lambda: setattr(st.session_state, 'current_view_index', idx + 1))
        
        with nav_col2:
            # 폰트 크기 수정: 1.5em으로 키움
            st.markdown(f"<div style='text-align: center; font-weight: bold; font-size: 1.5em; margin-top: 5px;'>{history_item['label']}<br><span style='color:gray; font-size:0.8em;'>({idx + 1}/{len(st.session_state.search_history)})</span></div>", unsafe_allow_html=True)

        st.markdown("---")

        # 1. 누적 감성 분석 (원형 그래프)
        # 선택된 히스토리 아이템의 감성 데이터 사용
        sentiment_counts = history_item.get("sentiment", {})
        total_sentiment = sum(sentiment_counts.values()) if sentiment_counts else 0
        
        if total_sentiment > 0:
            st.markdown("#### 😊 감성 비율")
            sentiment_df = pd.DataFrame([
                {"Category": "😊 긍정", "Count": sentiment_counts.get("Positive", 0)},
                {"Category": "😐 중립", "Count": sentiment_counts.get("Neutral", 0)},
                {"Category": "😡 부정", "Count": sentiment_counts.get("Negative", 0)}
            ])
            
            base = alt.Chart(sentiment_df).encode(theta=alt.Theta("Count", stack=True))
            pie = base.mark_arc(outerRadius=120, innerRadius=60).encode(
                color=alt.Color("Category", scale=alt.Scale(domain=["😊 긍정", "😐 중립", "😡 부정"], range=["#66BB6A", "#FFCA28", "#EF5350"])),
                order=alt.Order("Count", sort="descending"),
                tooltip=["Category", "Count"]
            )
            text = base.mark_text(radius=140).encode(
                text="Count", order=alt.Order("Count", sort="descending"), color=alt.value("black"), size=alt.value(16)
            )
            st.altair_chart(pie + text, width='stretch')
            
            c1, c2, c3 = st.columns(3)
            c1.metric("긍정", sentiment_counts.get("Positive", 0))
            c2.metric("중립", sentiment_counts.get("Neutral", 0))
            c3.metric("부정", sentiment_counts.get("Negative", 0))
        else:
            st.info("감성 분석 데이터가 없습니다.")

        st.markdown("---")

        # 2. 키워드 빈도 (막대 그래프)
        # 선택된 히스토리 아이템의 토픽 데이터 사용
        topic_counts = history_item.get("topics", {})
        
        if topic_counts:
            st.markdown("#### 🔑 키워드 빈도")
            topic_df = pd.DataFrame(list(topic_counts.items()), columns=['Keyword', 'Count']).sort_values(by='Count', ascending=False)
            
            bar = alt.Chart(topic_df).mark_bar().encode(
                x=alt.X('Count', title='빈도수'),
                y=alt.Y('Keyword', sort='-x', title='키워드'),
                color=alt.value("#7E57C2"),
                tooltip=['Keyword', 'Count']
            ).properties(height=300)
            
            st.altair_chart(bar, width='stretch')
        else:
            st.caption("키워드 통계가 없습니다.")

# 초기 렌더링
render_stats_dashboard()

# [좌측] 채팅 인터페이스
with chat_col:
    # 높이 고정 컨테이너
    chat_container = st.container(height=950)
    
    with chat_container:
        # 메시지 출력 (협업자 아바타 적용)
        for message in st.session_state.messages:
            avatar_img = "🕵️" if message["role"] == "assistant" else "💁‍♂️"
            with st.chat_message(message["role"], avatar=avatar_img):
                st.markdown(message["content"])
                
                # [수정 2] 메시지 히스토리 루프에서 Expander 렌더링
                # 이전 검색 결과의 목록도 여기서 보존되어 출력됩니다.
                if "references" in message and isinstance(message["references"], pd.DataFrame) and not message["references"].empty:
                    with st.expander(f"📚 사용된 전체 게시글 보기 ({len(message['references'])}건)"):
                        df_ref = message["references"]
                        cols = {c.lower(): c for c in df_ref.columns}
                        url_col = cols.get('posturl') or cols.get('url') or cols.get('link')
                        title_col = cols.get('title', 'Title')
                        for i, (idx, row) in enumerate(df_ref.iterrows()):
                            st.markdown(f"**{i+1}.** [{row[title_col]}]({row[url_col]}) ({row.get('Source', '')})")

    # 입력 처리 로직 (버튼 및 Chat Input)
    # Chat Input은 항상 하단에 위치
    user_input = st.chat_input("무엇을 분석해 드릴까요?")
    
    # 추천 키워드 버튼 (메시지가 적을 때만 표시)
    # 버튼 클릭 시 prompt 변수에 값을 할당하여 user_input이 있는 것처럼 처리
    prompt = None
    
    if len(st.session_state.messages) < 2:
        with chat_container:
            st.caption("🔥 요즘 핫한 키워드 / 추천 질문")
            col1, col2, col3, col4 = st.columns(4)
            if col1.button("🎮 롤드컵 반응"):
                prompt = "이번 롤드컵 커뮤니티 반응 알려줘"
            if col2.button("📱 아이폰 16 후기"):
                prompt = "아이폰 16 실사용 후기 요약해줘"
            if col3.button("⚽ 손흥민 현지 반응"):
                prompt = "손흥민 최근 경기 현지 및 국내 반응"
            if col4.button("👩‍🍳‍ 흑백요리사 여론"):
                prompt = "넷플릭스 흑백요리사 프로그램 여론 알려줘"
    
    # 입력 우선순위: Chat Input > Button Input
    if user_input:
        prompt = user_input

    # [Main Logic] 사용자 입력 처리
    if prompt:
        # 사용자 메시지 추가 및 표시
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # chat_container 내에 출력
        with chat_container:
            with st.chat_message("user", avatar="💁‍♂️"):
                st.markdown(prompt)

            # AI 응답 생성
            with st.chat_message("assistant", avatar="🕵️"):
                message_placeholder = st.empty()
                full_response = ""
                
                # 협업자 상태 표시 로직 적용
                with st.status("🕵️ 사용자의 질문을 분석하고 있습니다...", expanded=True) as status:
                    
                    # [Step 1] 검색 계획 수립
                    plan = get_search_plan(prompt)
                    mode = plan.get("mode", "chat")
                    
                    if mode == "search":
                        tasks = plan.get("tasks", [])
                        
                        task_summary = [f"{t.get('target_source').upper()}: '{t.get('keyword')}'" for t in tasks]
                        status.write(f"📋 **검색 계획 수립 완료**: {', '.join(task_summary)}")
                        status.update(label="데이터를 수집하고 있습니다...", state="running")
                        
                        # [Step 2] 크롤링 실행
                        raw_df = execute_crawling(tasks)
                        
                        if not raw_df.empty:
                            if 'Content' in raw_df.columns:
                                raw_df['Content'] = raw_df['Content'].astype(str).str.slice(0, 150)

                            initial_count = len(raw_df)
                            status.write(f"✅ 총 {initial_count}건의 데이터를 수집했습니다.")
                            status.update(label="혐오 표현을 필터링하고 있습니다...", state="running")
                            
                            # [Step 3] 혐오 표현 필터링
                            try:
                                clean_df = filter_hate_speech(raw_df)
                                target_df = clean_df.head(30) # 최신 30건 사용
                                
                                # target_df를 로컬 변수로 사용 (메시지에 저장됨)
                                
                                filtered_cnt = initial_count - len(clean_df)
                                used_cnt = len(target_df)
                                
                                msg = f"🧹 **필터링 완료**: {filtered_cnt}건의 부적절한 게시물을 제외했습니다. (분석 대상: 최근 {used_cnt}건)"
                                status.write(msg)
                                    
                            except Exception as e:
                                st.warning(f"필터링 중 오류 발생: {e}")
                                clean_df = raw_df
                                target_df = clean_df.head(30)
                            
                            status.update(label="최종 보고서를 작성하고 있습니다...", state="running")
                            
                            # [Step 4] 보고서 작성 (스트리밍)
                            try:
                                response_stream = generate_report(prompt, target_df)
                                
                                full_buffer = ""
                                
                                for chunk in response_stream:
                                    if chunk.text:
                                        full_buffer += chunk.text
                                        
                                        if "__REF_DATA__" in full_buffer:
                                            visible_text = full_buffer.split("__REF_DATA__")[0]
                                            message_placeholder.markdown(visible_text + "▌")
                                        else:
                                            message_placeholder.markdown(full_buffer + "▌")
                            
                                parts = full_buffer.split("__REF_DATA__")
                                report_content = parts[0].strip()
                                full_response = report_content
                                
                                # 통계 데이터 처리
                                ref_ids = []
                                if len(parts) > 1:
                                    try:
                                        json_str = parts[1].strip().replace("```json", "").replace("```", "").strip()
                                        json_data = json.loads(json_str)
                                        
                                        ref_ids = json_data.get("reference_ids", [])
                                        sentiment_counts = json_data.get("sentiment_counts", {})
                                        topic_counts = json_data.get("topic_counts", {})
                                        
                                        # [수정] 통계를 search_history에 추가 (History Logic)
                                        sources = set([t.get('target_source').upper() for t in tasks])
                                        keywords = set([t.get('keyword') for t in tasks])
                                        label = f"{', '.join(sources)} - {', '.join(keywords)}"
                                        
                                        new_history_item = {
                                            "label": label,
                                            "timestamp": time.time(),
                                            "sentiment": sentiment_counts,
                                            "topics": topic_counts
                                        }
                                        
                                        st.session_state.search_history.append(new_history_item)
                                        # 인덱스를 가장 최신(마지막)으로 이동
                                        st.session_state.current_view_index = len(st.session_state.search_history) - 1
                                            
                                        # 우측 대시보드 리렌더링
                                        render_stats_dashboard()

                                    except json.JSONDecodeError:
                                        print(f"[DEBUG] JSON Parsing failed")

                                # [UI 구성 1] 추천 링크 추가
                                if ref_ids:
                                    full_response += "\n\n---\n### 🔗 Gemini가 참고한 핵심 게시글\n"
                                    cols = {c.lower(): c for c in target_df.columns}
                                    url_col = cols.get('posturl') or cols.get('url') or cols.get('link')
                                    title_col = cols.get('title', 'Title')

                                    if url_col:
                                        for ref_id in ref_ids:
                                            target_idx = ref_id - 1
                                            if 0 <= target_idx < len(target_df):
                                                row = target_df.iloc[target_idx]
                                                full_response += f"- [{row[title_col]}]({row[url_col]})\n"
                            
                                message_placeholder.markdown(full_response)
                                
                                # [수정] Expander 즉시 렌더링 (Rerun 기다리지 않음)
                                if not target_df.empty:
                                    with st.expander(f"📚 사용된 전체 게시글 보기 ({len(target_df)}건)"):
                                        cols = {c.lower(): c for c in target_df.columns}
                                        url_col = cols.get('posturl') or cols.get('url') or cols.get('link')
                                        title_col = cols.get('title', 'Title')
                                        for i, (idx, row) in enumerate(target_df.iterrows()):
                                            st.markdown(f"**{i+1}.** [{row[title_col]}]({row[url_col]}) ({row.get('Source', '')})")

                            except Exception as e:
                                full_response += f"\n\n(오류 발생: {str(e)})"
                                message_placeholder.markdown(full_response)

                            status.update(label="분석 완료! (아래에서 전체 목록을 확인하세요)", state="complete", expanded=False)
                                
                        else:
                            full_response = "😥 검색 결과가 없습니다."
                            message_placeholder.markdown(full_response)
                            status.update(label="검색 실패", state="error", expanded=False)
                    
                    else:
                        # Chat 모드
                        full_response = plan.get("reply_message", "죄송합니다. 다시 말씀해 주시겠어요?")
                        message_placeholder.markdown(full_response)
                        status.update(label="대화 모드", state="complete", expanded=False)
            
            # [수정 2 관련] target_df를 메시지 히스토리에 함께 저장 (references 키 사용)
            msg_data = {"role": "assistant", "content": full_response}
            if mode == "search" and not raw_df.empty:
                 msg_data["references"] = target_df
            
            st.session_state.messages.append(msg_data)
            
            # 버튼 클릭 등으로 인해 갱신된 경우 rerun하여 UI 업데이트
            if prompt and not user_input:
                st.rerun()