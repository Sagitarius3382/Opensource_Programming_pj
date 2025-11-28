import os
import json
import time
import pandas as pd
import streamlit as st
import google.generativeai as genai
import concurrent.futures
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
# 2. 사이드바 설정 (커뮤니티 선택 제거, API 키 확인 유지)
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 설정")
    
    # API 키 및 모델 설정 확인 (기존 로직 유지)
    if not os.getenv("API_KEY"):
        st.error("🚨 API 키가 설정되지 않았습니다. .env 파일을 확인해주세요.")
    
    if not os.getenv("MODEL"):
        st.warning("⚠️ 모델이 설정되지 않았습니다. .env 파일을 확인해주세요.")
        
    st.info("AI가 사용자의 질문을 분석하여 자동으로 커뮤니티(DC/Arca)를 선정하고 데이터를 수집합니다.")
    st.markdown("---")
    st.caption("Powered by Google Gemini")

# --------------------------------------------------------------------------
# 3. Gemini 모델 로드 
# --------------------------------------------------------------------------
@st.cache_resource
def get_gemini_model():
    """
    Gemini 모델을 로드합니다. 
    st.cache_resource를 사용하여 세션 간 모델 객체를 공유합니다.
    """
    YOUR_API_KEY = os.getenv("API_KEY")
    if not YOUR_API_KEY:
        st.error("🚨 API 키가 설정되지 않았습니다. .env 파일을 확인해주세요.")
        st.stop()

    YOUR_MODEL = os.getenv("MODEL")
    if not YOUR_MODEL:
        st.error("모델이 설정되지 않았습니다. '.env' 파일에 'MODEL'을 설정해주세요.")
        st.stop()
        
    genai.configure(api_key=YOUR_API_KEY)
    
    # 안전 설정: 모든 카테고리에 대해 차단 없음(BLOCK_NONE)으로 설정하여 오탐지 방지
    safety_settings = [
        {
            "category": "HARM_CATEGORY_HARASSMENT",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_HATE_SPEECH",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
            "threshold": "BLOCK_NONE"
        },
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
    너는 '커뮤니티 여론 분석을 위한 검색 설계자'야. 
    사용자의 질문을 분석해서 어떤 커뮤니티(DCInside, ArcaLive)를 어떤 키워드로 검색할지 구체적인 계획을 세워줘.
    
    [필수 규칙]
    1. 사용자가 "여론", "반응", "평가" , "의견" , "근황" 등을 물으면 mode="search"로 설정해.
    2. **검색어(keyword)는 공식 명칭보다 실제로 커뮤니티에서 많이 쓰이는 '은어'나 '줄임말'을 우선적으로 선택해.** (예: 블루 아카이브 -> 블아, 몰루 / 리그오브레전드 -> 롤)
    3. **[타겟 선정]** 특정 사이트 언급이 없으면, 해당 주제가 활발한 곳을 자동으로 판단하되 **잘 모르겠거나 대중적인 게임/이슈라면 ["dc", "arca"] 두 곳 모두 tasks에 포함해.**
    4. DCInside는 'gallery_id', ArcaLive는 'channel_id'를 반드시 추론해서 options에 포함해야 해. (모르면 'major'나 'breaking' 같은 기본값이라도 넣어)
        - **중요:** DC의 게임/서브컬처 장르는 대부분 **'minor' (마이너 갤러리)** 타입이야. (예: 메이플 -> maplestory_new (minor))
    5. 응답은 반드시 아래 JSON 형식으로만 출력해. (Markdown 코드블럭 없이 순수 JSON만)

    [JSON 출력 형식]
    {
        "mode": "search" | "clarify" | "chat",
        "reply_message": "사용자에게 할 말 (계획을 세웠다면 '잠시만 기다려주세요, ~에 대해 알아보고 있습니다.' 등)",
        "tasks": [
            {
                "target_source": "dc" | "arca",
                "keyword": "은어_기반_검색어",
                "options": {
                    "gallery_id": "추론된_갤러리ID (dc 필수)",
                    "channel_id": "추론된_채널ID (arca 필수)",
                    "gallery_type": "minor" | "major", 
                    "sort_type": "latest"
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
            print(f"[DEBUG] Crawling Task:")
            print(f"  - Target: {target}")
            print(f"  - Keyword: {keyword}")
            print(f"  - Options: {options}")
            
            # search_community(target_source, keyword, start_page, end_page, **kwargs)
            # 기본적으로 1~2페이지만 긁도록 설정 (속도 위해)
            future = executor.submit(search_community, target, keyword, 1, 2, **options)
            future_to_task[future] = task
            
        for future in concurrent.futures.as_completed(future_to_task):
            task = future_to_task[future]
            try:
                df = future.result()
                print(f"[DEBUG] Crawling result for {task.get('target_source')}: {len(df)} rows")
                if not df.empty:
                    # 출처 표기를 위해 컬럼 추가
                    df["Source"] = task.get("target_source")
                    df["Keyword"] = task.get("keyword")
                    all_results.append(df)
                else:
                    print(f"[DEBUG] Empty DataFrame returned for {task.get('target_source')}")
            except Exception as e:
                st.error(f"크롤링 중 오류 발생 ({task}): {e}")
                print(f"[DEBUG] Exception during crawling: {e}")

    if all_results:
        final_df = pd.concat(all_results, ignore_index=True)
        return final_df
    else:
        return pd.DataFrame()

def generate_report(user_input, df):
    """
    수집된 데이터를 바탕으로 최종 보고서를 작성합니다.
    """
    model = get_gemini_model()
    
    if df.empty:
        return "수집된 데이터가 없어 보고서를 작성할 수 없습니다."
        
    # 토큰 절약을 위해 상위 30개 정도만 프롬프트에 포함
    summary_text = ""
    # 컬럼명 대소문자 호환성을 위해 처리
    cols = df.columns
    title_col = next((c for c in cols if c.lower() == 'title'), 'title')
    content_col = next((c for c in cols if c.lower() == 'content'), 'content')

    for idx, row in df.head(30).iterrows():
        title = row.get(title_col, "No Title")
        content = str(row.get(content_col, ""))[:100]
        summary_text += f"- {title}: {content}\n"
        
    prompt = f"""
    당신은 커뮤니티 여론 분석 전문가입니다.
    
    [사용자 질문]
    {user_input}
    
    [수집된 데이터 요약]
    {summary_text}
    
    위 데이터를 바탕으로 상세한 보고서를 작성해주세요.
    다음 항목을 반드시 포함하세요:
    1. **3줄 요약**: 전체적인 여론의 핵심 요약
    2. **긍정 여론**: 유저들이 긍정적으로 평가하는 요소
    3. **부정 여론**: 유저들이 불만이나 비판을 제기하는 요소
    4. **주요 논쟁**: 현재 가장 뜨거운 감자나 논쟁거리
    5. **종합 평가**: 결론 및 제언
    """
    
    return model.generate_content(prompt, stream=True)

# --------------------------------------------------------------------------
# 5. 메인 로직 
# --------------------------------------------------------------------------
st.title("🕵️‍♂️ Community Insight Bot")
st.caption("AI가 자동으로 커뮤니티를 선정하고 여론을 분석합니다.")

if "messages" not in st.session_state:
    st.session_state.messages = []
    welcome_msg = "안녕하세요! 궁금한 게임, 인물, 이슈 등을 물어봐주세요. 제가 알아서 적절한 커뮤니티를 찾아 분석해드릴게요."
    st.session_state.messages.append({"role": "assistant", "content": welcome_msg})

for message in st.session_state.messages:
    avatar_img = "assets/purple_avatar.png" if message["role"] == "assistant" else None
    with st.chat_message(message["role"], avatar=avatar_img):
        st.markdown(message["content"])

# 사용자 입력 처리
if prompt := st.chat_input("무엇을 분석해 드릴까요?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # AI 응답 생성 시작
    with st.chat_message("assistant", avatar="assets/purple_avatar.png"):
        message_placeholder = st.empty()
        full_response = ""
        
        with st.status("🤔 사용자의 질문을 분석하고 있습니다...", expanded=True) as status:
            
            # [Step 1] 검색 계획 수립
            plan = get_search_plan(prompt)
            mode = plan.get("mode", "chat")
            
            # 디버깅: Gemini가 생성한 계획 출력
            print(f"[DEBUG] Gemini Plan Generated:")
            print(f"  - Mode: {mode}")
            print(f"  - Reply Message: {plan.get('reply_message', 'N/A')}")
            print(f"  - Tasks: {plan.get('tasks', [])}")
            
            if mode == "search":
                tasks = plan.get("tasks", [])
                
                # 계획 내용 표시
                task_summary = []
                for t in tasks:
                    target = t.get('target_source')
                    keyword = t.get('keyword')
                    task_summary.append(f"{target.upper()}: '{keyword}'")
                
                status.write(f"📋 **검색 계획 수립 완료**: {', '.join(task_summary)}")
                status.update(label="데이터를 수집하고 있습니다...", state="running")
                
                # [Step 2] 크롤링 실행
                raw_df = execute_crawling(tasks)
                
                if not raw_df.empty:
                    initial_count = len(raw_df)
                    status.write(f"✅ 총 {initial_count}건의 데이터를 수집했습니다.")
                    status.update(label="혐오 표현을 필터링하고 있습니다...", state="running")
                    
                    # [Step 3] 혐오 표현 필터링
                    try:
                        clean_df = filter_hate_speech(raw_df)
                        final_count = len(clean_df)
                        filtered_count = initial_count - final_count
                        
                        if filtered_count > 0:
                            status.write(f"🧹 **필터링 완료**: {filtered_count}건의 부적절한 게시물을 제외했습니다. (남은 데이터: {final_count}건)")
                        else:
                            status.write("✨ 필터링된 게시물이 없습니다. (깨끗한 데이터)")
                            
                    except Exception as e:
                        st.warning(f"필터링 중 오류 발생: {e}")
                        clean_df = raw_df
                    
                    status.update(label="최종 보고서를 작성하고 있습니다...", state="running")
                    
                    # [Step 4] 보고서 작성
                    response_stream = generate_report(prompt, clean_df)
                    
                    try:
                        for chunk in response_stream:
                            if chunk.parts:
                                full_response += chunk.text
                                message_placeholder.markdown(full_response + "▌")
                    except Exception as e:
                        full_response += f"\n\n(분석 중 오류 발생: {str(e)})"
                    
                    message_placeholder.markdown(full_response)
                    status.update(label="분석 완료!", state="complete", expanded=False)
                    
                    # [Step 5] 원본 데이터 확인 (Expander)
                    with st.expander("📊 수집된 원본 데이터 확인"):
                        st.dataframe(clean_df, use_container_width=True)
                        
                else:
                    full_response = "😥 검색 결과가 없습니다. 다른 키워드로 질문해 보시겠어요?"
                    message_placeholder.markdown(full_response)
                    status.update(label="검색 실패", state="error", expanded=False)
            
            else:
                # Chat / Clarify 모드
                full_response = plan.get("reply_message", "죄송합니다. 다시 말씀해 주시겠어요?")
                message_placeholder.markdown(full_response)
                status.update(label="대화 모드", state="complete", expanded=False)
                
    # 세션 기록 저장
    st.session_state.messages.append({"role": "assistant", "content": full_response})
