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
    page_title="Community Insight Bot",
    page_icon="🕵️‍♂️",
    layout="wide"
)

# 새로운 모듈 임포트
try:
    from src.crawler_wrapper import search_community
    from src.preprocessor import filter_hate_speech
except ImportError as e:
    st.error(f"필수 모듈을 임포트하는 중 오류가 발생했습니다: {e}")
    st.stop()

# --------------------------------------------------------------------------
# 2. 사이드바 설정 (API 상태 표시)
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 설정")
    
    api_key = os.getenv("API_KEY")
    model_name = os.getenv("MODEL")

    if api_key and model_name:
        st.success("🟢 API 연동 정상")
        st.markdown(f"**사용 모델:** `{model_name}`")
    else:
        st.error("🔴 API 연동 실패")
        if not api_key:
            st.warning("API 키가 누락되었습니다.")
        if not model_name:
            st.warning("모델 설정이 누락되었습니다.")
        
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
    너는 '커뮤니티 키워드 검색을 위한 검색 설계자'야. 
    사용자의 질문을 분석해서 어떤 커뮤니티(DCInside, ArcaLive 둘 중 하나)를 어떤 키워드로 검색할지 구체적인 계획을 세워줘.
    
    [필수 규칙]
    1. 사용자가 "여론", "반응", "평가" , "의견" , "근황" 등 키워드 검색이 가능한 것을 물으면 mode="search"로 설정해.
    2. **검색어(keyword)는 공식 명칭보다 실제로 커뮤니티에서 많이 쓰이는 '단어의 일부분', '은어'나 '줄임말'을 우선적으로 선택해.** (예: 갤럭시 S25 -> S25, 블루 아카이브 -> 블아, 리그오브레전드 -> 롤, 맨체스터 유나이티드 -> 맨유)
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
                "keyword": "검색어: 단어의 일부분, 줄임말, 은어를 적극적으로 사용. 특정 주제의 갤러리 검색 시 주제 관련 단어는 제거. (예: 원신 갤러리 검색 시, '원신 필수캐' -> '필수캐')",
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
    all_results = []
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_task = {}
        for task in tasks:
            target = task.get("target_source")
            keyword = task.get("keyword")
            options = task.get("options", {})
            
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
                if not df.empty:
                    df["Source"] = future_to_task[future].get("target_source")
                    df["Keyword"] = future_to_task[future].get("keyword")
                    all_results.append(df)

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
        content = str(row.get(content_col, ""))[:150]
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
    3. **topic_counts**: 전체(최대 30개) 글에서 주로 다뤄진 상위 키워드 3~5개와 그 빈도수
    
    __REF_DATA__
    {{
        "reference_ids": [1, 5, 10],
        "sentiment_counts": {{ "Positive": 12, "Negative": 8, "Neutral": 10 }},
        "topic_counts": {{ "게임플레이": 15, "스토리": 8, "운영": 7 }}
    }}
    """
    
    return model.generate_content(prompt, stream=True)

# --------------------------------------------------------------------------
# 5. 메인 로직 
# --------------------------------------------------------------------------
st.title("🕵️‍♂️ Community Insight Bot")
st.caption("AI가 자동으로 커뮤니티를 선정하고 커뮤니티 기반 정보와 여론을 분석합니다.")

# [누적 데이터 관리] 세션 상태 초기화
if "sentiment_history" not in st.session_state:
    st.session_state.sentiment_history = {"Positive": 0, "Neutral": 0, "Negative": 0}
if "latest_topic_counts" not in st.session_state:
    st.session_state.latest_topic_counts = {}
if "messages" not in st.session_state:
    st.session_state.messages = []
    welcome_msg = "안녕하세요! 궁금한 키워드를 물어봐주세요. 제가 커뮤니티 여론을 분석해 드릴게요."
    st.session_state.messages.append({"role": "assistant", "content": welcome_msg})

# [CSS] 채팅창 스타일 조정 (채팅 입력창을 좌측 컬럼 너비에 맞게 고정)
st.markdown(
    """
    <style>
    /* 화면 너비가 넓을 때 (PC 등) 채팅 입력창을 좌측 60% 영역에 맞춤 */
    @media (min-width: 768px) {
        div[data-testid="stChatInput"] {
            width: 58% !important; /* 좌측 컬럼 비율에 맞게 조정 (gap 고려) */
            left: 21rem !important; /* 사이드바 너비(기본값)만큼 띄움 */
            margin-right: auto;
        }
        .stMain div[data-testid="stChatInput"] {
            width: 58% !important;
            left: auto !important;
            right: auto !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- 화면 레이아웃 분할 (좌: 채팅 / 우: 통계) ---
chat_col, stat_col = st.columns([0.6, 0.4], gap="large")

# 대시보드를 덮어쓰기 위해 st.empty()로 placeholder 생성
dashboard_placeholder = stat_col.empty()

# [우측] 통계 대시보드 렌더링 함수
def render_stats_dashboard():
    # placeholder.container()를 사용하여 매번 내용을 덮어씀 (중복 출력 방지)
    with dashboard_placeholder.container():
        st.markdown("### 📈 실시간 여론 대시보드")
        
        # 1. 누적 감성 분석 (원형 그래프)
        total_sentiment = sum(st.session_state.sentiment_history.values())
        if total_sentiment > 0:
            st.markdown("#### 😊 누적 감성 비율")
            
            sentiment_df = pd.DataFrame([
                {"Category": "😊 긍정", "Count": st.session_state.sentiment_history["Positive"], "Color": "#4CAF50"}, # 초록
                {"Category": "😐 중립", "Count": st.session_state.sentiment_history["Neutral"], "Color": "#FFC107"},  # 노랑
                {"Category": "😡 부정", "Count": st.session_state.sentiment_history["Negative"], "Color": "#F44336"}   # 빨강
            ])
            
            # 도넛 차트 생성
            base = alt.Chart(sentiment_df).encode(
                theta=alt.Theta("Count", stack=True)
            )
            
            pie = base.mark_arc(outerRadius=120, innerRadius=60).encode(
                color=alt.Color("Category", 
                                scale=alt.Scale(domain=["😊 긍정", "😐 중립", "😡 부정"], 
                                              range=["#66BB6A", "#FFCA28", "#EF5350"]),
                                legend=alt.Legend(title="감성 상태", titleFontSize=12, labelFontSize=12)),
                order=alt.Order("Count", sort="descending"),
                tooltip=["Category", "Count", alt.Tooltip("Count", format=".0f")]
            )
            
            text = base.mark_text(radius=140).encode(
                text="Count",
                order=alt.Order("Count", sort="descending"),
                color=alt.value("black"),
                size=alt.value(16)
            )
            
            st.altair_chart(pie + text, use_container_width=True)
            
            col1, col2, col3 = st.columns(3)
            col1.metric("긍정", st.session_state.sentiment_history["Positive"])
            col2.metric("중립", st.session_state.sentiment_history["Neutral"])
            col3.metric("부정", st.session_state.sentiment_history["Negative"])
            
        else:
            st.info("데이터가 수집되면 통계가 표시됩니다.")

        st.markdown("---")

        # 2. 키워드 빈도 (가로 막대 그래프)
        if st.session_state.latest_topic_counts:
            st.markdown("#### 🔑 최신 키워드 빈도 (새 키워드 검색 시 초기화됩니다)")
            
            topic_data = st.session_state.latest_topic_counts
            topic_df = pd.DataFrame(list(topic_data.items()), columns=['Keyword', 'Count'])
            topic_df = topic_df.sort_values(by='Count', ascending=False)
            
            bar_chart = alt.Chart(topic_df).mark_bar().encode(
                x=alt.X('Count', title='빈도수', axis=alt.Axis(titleFontSize=14, labelFontSize=12)),
                y=alt.Y('Keyword', sort='-x', title='키워드', 
                        axis=alt.Axis(titleFontSize=14, labelFontSize=14, labelLimit=200)),
                color=alt.value("#7E57C2"),
                tooltip=['Keyword', 'Count']
            ).properties(
                height=300
            )
            
            text_bar = bar_chart.mark_text(
                align='left',
                baseline='middle',
                dx=3
            ).encode(
                text='Count'
            )
            
            st.altair_chart(bar_chart + text_bar, use_container_width=True)
            
        else:
            st.caption("최근 검색된 키워드 통계가 없습니다.")

# 초기 렌더링
render_stats_dashboard()

# [좌측] 채팅 인터페이스 (스크롤 가능한 컨테이너 적용)
with chat_col:
    # [변경] 메시지 출력을 위한 고정 높이 컨테이너 생성
    chat_container = st.container(height=950)
    
    with chat_container:
        # 이전 대화 출력
        for message in st.session_state.messages:
            avatar_img = "assets/purple_avatar.png" if message["role"] == "assistant" else None
            with st.chat_message(message["role"], avatar=avatar_img):
                st.markdown(message["content"])

# 사용자 입력 처리 (하단 고정)
if prompt := st.chat_input("무엇을 분석해 드릴까요?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # [변경] 새로운 메시지도 chat_container 내부에 출력
    with chat_container:
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar="assets/purple_avatar.png"):
            message_placeholder = st.empty()
            full_response = ""
            
            with st.status("🤔 사용자의 질문을 분석하고 있습니다...", expanded=True) as status:
                
                # [Step 1] 검색 계획 수립
                plan = get_search_plan(prompt)
                mode = plan.get("mode", "chat")
                
                print(f"[DEBUG] Plan: {plan}")
                
                if mode == "search":
                    tasks = plan.get("tasks", [])
                    
                    task_summary = [f"{t.get('target_source').upper()}: '{t.get('keyword')}'" for t in tasks]
                    status.write(f"📋 **검색 계획**: {', '.join(task_summary)}")
                    status.update(label="데이터를 수집하고 있습니다...", state="running")
                    
                    # [Step 2] 크롤링 실행
                    raw_df = execute_crawling(tasks)
                    
                    if not raw_df.empty:
                        if 'Content' in raw_df.columns:
                            raw_df['Content'] = raw_df['Content'].astype(str).str.slice(0, 150)

                        initial_count = len(raw_df)
                        status.write(f"✅ 총 {initial_count}건 수집 완료")
                        status.update(label="데이터 필터링 중...", state="running")
                        
                        # [Step 3] 필터링
                        try:
                            clean_df = filter_hate_speech(raw_df)
                            target_df = clean_df.head(30)
                            
                            filtered_cnt = initial_count - len(clean_df)
                            used_cnt = len(target_df)
                            
                            status.write(f"🧹 필터링: {filtered_cnt}건 제외. (분석 대상: 최신 {used_cnt}건)")
                                
                        except Exception as e:
                            st.warning(f"필터링 오류: {e}")
                            clean_df = raw_df
                            target_df = clean_df.head(30)
                        
                        status.update(label="보고서 작성 및 통계 분석 중...", state="running")
                        
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
                            
                            ref_ids = []
                            if len(parts) > 1:
                                try:
                                    json_str = parts[1].strip().replace("```json", "").replace("```", "").strip()
                                    json_data = json.loads(json_str)
                                    
                                    ref_ids = json_data.get("reference_ids", [])
                                    sentiment_counts = json_data.get("sentiment_counts", {})
                                    topic_counts = json_data.get("topic_counts", {})
                                    
                                    # [통계 업데이트]
                                    if sentiment_counts:
                                        st.session_state.sentiment_history["Positive"] += sentiment_counts.get("Positive", 0)
                                        st.session_state.sentiment_history["Neutral"] += sentiment_counts.get("Neutral", 0)
                                        st.session_state.sentiment_history["Negative"] += sentiment_counts.get("Negative", 0)
                                        
                                    if topic_counts:
                                        st.session_state.latest_topic_counts = topic_counts
                                        
                                    # 우측 대시보드 리렌더링
                                    render_stats_dashboard()

                                except json.JSONDecodeError:
                                    print(f"[DEBUG] JSON Parsing failed")

                            # 추천 링크
                            if ref_ids:
                                full_response += "\n\n---\n### 🔗 핵심 게시글\n"
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
                            
                            # 전체 목록
                            if not target_df.empty:
                                status.markdown("---")
                                status.write(f"**📑 분석에 사용된 전체 게시글 ({len(target_df)}건)**")
                                cols = {c.lower(): c for c in target_df.columns}
                                url_col = cols.get('posturl') or cols.get('url')
                                title_col = cols.get('title', 'Title')
                                
                                for i, (idx, row) in enumerate(target_df.iterrows()):
                                    status.markdown(f"{i+1}. [{row[title_col]}]({row[url_col]})")

                        except Exception as e:
                            full_response += f"\n\n(오류 발생: {str(e)})"
                            message_placeholder.markdown(full_response)

                        status.update(label="분석 완료! (클릭하여 전체 목록 확인)", state="complete", expanded=False)
                            
                    else:
                        full_response = "😥 검색 결과가 없습니다."
                        message_placeholder.markdown(full_response)
                        status.update(label="검색 실패", state="error", expanded=False)
                
                else:
                    # Chat 모드
                    full_response = plan.get("reply_message", "죄송합니다. 다시 말씀해 주시겠어요?")
                    message_placeholder.markdown(full_response)
                    status.update(label="대화 모드", state="complete", expanded=False)
                    
        st.session_state.messages.append({"role": "assistant", "content": full_response})