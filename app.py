import os
import json
import time
import pandas as pd
import streamlit as st
import google.generativeai as genai
from dotenv import load_dotenv

# 스크래퍼 모듈 임포트
from src.dc_scraper import get_integrated_search_data, get_regular_post_data
from src.arca_scraper import get_arca_posts

# --------------------------------------------------------------------------
# 1. 초기 설정 및 환경 변수 로드
# --------------------------------------------------------------------------
load_dotenv()

st.set_page_config(
    page_title="Community Insight Bot",
    page_icon="🕵️‍♂️",
    layout="wide"
)

# 사이드바 설정 (커뮤니티 선택)
with st.sidebar:
    st.header("⚙️ 설정")
    community_type = st.radio(
        "분석할 커뮤니티를 선택하세요:",
        ( "ArcaLive", "DCInside"),
        index=0
    )
    st.info(f"현재 선택된 커뮤니티: **{community_type}**")
    st.info("DCInside의 경우 사이트 약관 위반의 소지가 있으므로 신중히 사용함을 권고합니다.")

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
    return genai.GenerativeModel(YOUR_MODEL)

# --------------------------------------------------------------------------
# 2. LLM 로직 (Controller & Analyst)
# --------------------------------------------------------------------------

def query_controller_DC(user_input):
    """
    DC Inside용 의도 파악 컨트롤러
    """
    model = get_gemini_model()
    
    system_instruction = """
    너는 '디시인사이드 검색 의도 판단 AI'야. 사용자의 입력을 분석해서 반드시 아래 JSON 형식으로만 응답해. 설명이나 다른 말은 하지 마.
    
    [판단 기준]
    1. "search": 특정 게임, 인물, 사건의 여론이나 정보 등 명확한 주제에 대해 묻는 경우.
    2. "clarify": 키워드가 너무 모호해서(예: '헤르타'가 작가 헤르타 뮐러인지, 축구팀 헤르타 BSC인지, 붕괴 스타레일 게임의 등장인물 헤르타인지 불분명함) 검색 대상을 확정할 수 없는 경우.
    3. "chat": 단순 인사, 잡담, 혹은 분석과 관련 없는 대화.

    [JSON 출력 형식]
    {
        "mode": "search" | "clarify" | "chat",
        "search_keyword": "디시인사이드에서 검색할 핵심 주제어 (검색 결과가 최대한 잘 나올 수 있는 단순 키워드",
        "gallery_name": "키워드를 검색할 갤러리의 갤러리명 (예: 메이플스토리, 리그오브레전드, 치지직). 모르거나 통합검색이 적합할 경우 null",
        "gallery_id": "키워드를 검색할 갤러리의 갤러리 ID (예: 'maplestory_new', 'leagueoflegends6', 'chzzk'). 모르거나 통합검색이 적합할 경우 null",
        "gallery_type": "gallery_id값에 해당하는 갤러리의 종류로 다음 셋 중 하나 ('major' | 'minor' | 'mini'). 명확하지 않을 때는 'major', 통합검색이 적합할 경우 null",
        "sort_type": "통합검색이 적합할 경우 정렬 방식으로 셋 중 하나 ('latest' | 'accuracy'). 통합검색이 필요하지 않을 경우 null",
        "reply_message": "mode가 clarify혹은 chat일 때 사용자의 입력에 대한 응답"
    }
    """
    
    try:
        response = model.generate_content(
            f"{system_instruction}\n\nUser Input: {user_input}",
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except Exception as e:
        return {"mode": "chat", "reply_message": "죄송합니다. 의도를 파악하는 중 오류가 발생했습니다."}

def query_controller_Arca(user_input):
    """
    ArcaLive용 의도 파악 컨트롤러
    """
    model = get_gemini_model()
    
    system_instruction = """
    너는 '아카라이브 검색 의도 판단 AI'야. 사용자의 입력을 분석해서 반드시 아래 JSON 형식으로만 응답해. 설명이나 다른 말은 하지 마.
    
    [판단 기준]
    1. "search": 특정 게임, 인물, 사건의 여론이나 정보 등 명확한 주제에 대해 묻는 경우.
    2. "clarify": 키워드가 너무 모호해서(예: '헤르타'가 작가 헤르타 뮐러인지, 축구팀 헤르타 BSC인지, 붕괴 스타레일 게임의 등장인물 헤르타인지 불분명함) 검색 대상을 확정할 수 없는 경우.
    3. "chat": 단순 인사, 잡담, 혹은 분석과 관련 없는 대화.

    [JSON 출력 형식]
    {
        "mode": "search" | "clarify" | "chat",
        "search_keyword": "아카라이브에서 검색할 핵심 주제어",
        "channel_name": "키워드를 검색할 채널명 (예: 핫딜, 원신). 모르거나 통합검색이 적합할 경우 null",
        "channel_id": "키워드를 검색할 채널 ID (예: 'hotdeal', 'genshin'). 모르거나 통합검색이 적합할 경우 null",
        "reply_message": "mode가 clarify혹은 chat일 때 사용자의 입력에 대한 응답"
    }
    """
    
    try:
        response = model.generate_content(
            f"{system_instruction}\n\nUser Input: {user_input}",
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except Exception as e:
        return {"mode": "chat", "reply_message": "죄송합니다. 의도를 파악하는 중 오류가 발생했습니다."}

def query_analyst(user_input, data_summary, community_name):
    """
    수집된 데이터를 바탕으로 보고서를 작성하는 분석가입니다.
    """
    model = get_gemini_model()
    
    prompt = f"""
    당신은 커뮤니티 여론 분석 전문가입니다.
    사용자 질문: "{user_input}"
    대상 커뮤니티: {community_name}
    
    아래는 수집된 관련 게시물 요약 데이터입니다:
    -----
    {data_summary}
    -----
    
    위 데이터를 바탕으로 다음 형식에 맞춰 보고서를 작성해주세요:
    1. **3줄 요약**: 현재 여론의 핵심을 요약.
    2. **긍정 여론**: 유저들이 호평하는 부분.
    3. **부정 여론**: 유저들이 불만인 부분.
    4. **주요 논쟁**: 현재 커뮤니티에서 핫한 토픽이나 싸움 거리.
    5. **종합 평가**: (0~10점 민심 점수와 한줄 평)
    
    데이터가 부족하거나 관련이 없으면 솔직하게 "분석할 충분한 데이터가 없습니다"라고 말해주세요.
    """
    
    return model.generate_content(prompt, stream=True)

# --------------------------------------------------------------------------
# 3. 데이터 수집 로직 (라우팅 & 폴백)
# --------------------------------------------------------------------------

# 테스트용 end_page = 1
def fetch_data_DC(keyword, gallery_name=None, gallery_id=None, start_page=1, end_page=1, sort='latest'):
    """DC Inside 데이터 수집"""
    df = pd.DataFrame()
    status_msg = ""

    # 1. 갤러리 ID가 있으면 -> 갤러리 직접 크롤링 시도
    if gallery_id:
        st.write(f"🎯 특정 갤러리 감지: `{gallery_id}`")
        df = get_regular_post_data(gallery_id=gallery_id, search_keyword=keyword, start_page=start_page, end_page=end_page)
        
        if not df.empty:
            status_msg = f"'{gallery_name}' 갤러리에서 {len(df)}개 수집 성공"
            return df, status_msg
        else:
            st.warning(f"'{gallery_name}' 갤러리 검색 실패. 통합 검색으로 전환합니다.")

    # 2. 갤러리 ID가 없거나 실패 시 -> 통합 검색 시도 (Fallback)
    st.write(f"🌐 통합 검색 시도: `{keyword}`")
    df = get_integrated_search_data(search_keyword=keyword, sort_type=sort, start_page=start_page, end_page=end_page)
    
    if not df.empty:
        status_msg = f"통합 검색에서 {len(df)}개 수집 성공"
    else:
        status_msg = "검색 결과 없음"
        
    return df, status_msg

# 테스트용 end_page = 1
def fetch_data_Arca(keyword, channel_name=None, channel_id=None, start_page=1, end_page=1):
    """ArcaLive 데이터 수집"""
    df = pd.DataFrame()
    status_msg = ""

    # 채널 ID가 없으면 통합 검색(breaking) 사용
    target_channel = channel_id if channel_id else "breaking"
    
    if channel_id:
        st.write(f"🎯 특정 채널 감지: `{channel_id}`")
    else:
        st.write(f"🌐 통합 검색 시도: `{keyword}`")

    df = get_arca_posts(channel_id=target_channel, search_keyword=keyword, start_page=start_page, end_page=end_page)
    
    if not df.empty:
        status_msg = f"'{target_channel}' 채널/검색에서 {len(df)}개 수집 성공"
    else:
        status_msg = "검색 결과 없음"
        
    return df, status_msg

# --------------------------------------------------------------------------
# 4. UI 및 메인 실행 루프 (전체 구현 포함)
# --------------------------------------------------------------------------

st.title(f"🕵️‍♂️ {community_type} Insight Chatbot")
st.caption(f"{community_type} 실시간 여론 분석기 powered by Gemini")

# 세션 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []
    welcome_msg = "안녕하세요! 커뮤니티 여론 분석 봇입니다. 궁금한 게임, 인물, 이슈를 물어봐주세요."
    st.session_state.messages.append({"role": "assistant", "content": welcome_msg})

# 화면에 이전 대화 기록 출력
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 사용자 입력 처리
if prompt := st.chat_input("무엇을 분석해 드릴까요?"):
    # 1. 사용자 메시지를 세션에 추가하고 화면에 표시
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. AI 응답 생성 시작
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        # 상태 표시 컨테이너 (진행 상황 시각화)
        with st.status("🤔 의도를 파악하고 있습니다...", expanded=True) as status:
            
            # [Step 1] 의도 파악 (Controller 호출)
            # 커뮤니티별 컨트롤러 호출
            if community_type == "DC Inside":
                intent = query_controller_DC(prompt)
            else:
                intent = query_controller_Arca(prompt)
                
            mode = intent.get("mode", "chat")
            
            if mode == "search":
                keyword = intent.get("search_keyword", prompt)
                
                status.write(f"🔍 검색 키워드: **{keyword}**")
                status.update(label="데이터를 수집하고 있습니다...", state="running")
                
                # [Step 2] 데이터 수집 (fetch_data 호출)
                try:
                    # 커뮤니티별 데이터 수집
                    if community_type == "DC Inside":
                        gallery_id = intent.get("gallery_id")
                        gallery_name = intent.get("gallery_name")
                        sort = intent.get("sort_type", "latest")
                        df, log_msg = fetch_data_DC(keyword=keyword, gallery_name=gallery_name, gallery_id=gallery_id, sort=sort)
                    else:
                        channel_id = intent.get("channel_id")
                        channel_name = intent.get("channel_name")
                        df, log_msg = fetch_data_Arca(keyword=keyword, channel_name=channel_name, channel_id=channel_id)
                    
                    if not df.empty:
                        # [Step 3] 데이터 전처리 (LLM 프롬프트용 요약)
                        # 토큰 제한을 고려해 상위 20개 글만 사용하여 요약 텍스트 생성
                        top_posts = df.head(20)
                        data_summary = ""
                        for idx, row in top_posts.iterrows():
                            # 컬럼명 통일 (DC: GalleryName, Arca: GalleryID or similar)
                            # Arca scraper returns 'GalleryID' as channel name/id
                            source = row.get('GalleryName', row.get('GalleryID', 'Unknown'))
                            title = row.get('Title', 'No Title')
                            content = row.get('Content', '')[:150] # 본문 길면 150자에서 자름
                            comments = row.get('Comments', '')
                            
                            summary_line = f"- [{source}] {title}: {content}..."
                            if comments:
                                summary_line += f" / 댓글: {comments[:100]}..."
                            data_summary += summary_line + "\n"
                        
                        status.write(f"✅ {log_msg}")
                        status.update(label="심층 분석 중입니다...", state="running")
                        
                        # [Step 4] 분석 리포트 생성 (Analyst 호출 및 스트리밍)
                        response_stream = query_analyst(prompt, data_summary, community_type)
                        
                        # 스트리밍 출력 루프
                        for chunk in response_stream:
                            if chunk.text:
                                full_response += chunk.text
                                message_placeholder.markdown(full_response + "▌")
                        
                        # 스트리밍 완료 후 커서 제거
                        message_placeholder.markdown(full_response)
                        status.update(label="분석 완료!", state="complete", expanded=False)
                        
                        # 부가 정보: 참고한 데이터 테이블 보여주기 (접이식)
                        with st.expander("📊 참고한 게시물 원본 데이터 확인"):
                            cols_to_show = ['Title', 'Content', 'GalleryID', 'PostURL']
                            if 'Comments' in df.columns:
                                cols_to_show.append('Comments')
                            
                            # 존재하는 컬럼만 선택
                            valid_cols = [c for c in cols_to_show if c in df.columns]
                            
                            st.dataframe(
                                df[valid_cols].head(20),
                                use_container_width=True
                            )
                            
                    else:
                        # 검색 결과가 0건인 경우
                        full_response = f"😥 '{keyword}'에 대한 유의미한 검색 결과를 찾지 못했습니다."
                        message_placeholder.markdown(full_response)
                        status.update(label="검색 실패", state="error", expanded=False)
                        
                except Exception as e:
                    # 실행 중 에러 발생 시 처리
                    st.error(f"오류 발생: {str(e)}")
                    full_response = "시스템 오류가 발생하여 분석을 중단했습니다."
                    message_placeholder.markdown(full_response)
                    status.update(label="오류 발생", state="error")
            
            else:
                # [Chat/Clarify 모드] 단순 대화나 되묻기 처리
                full_response = intent.get("reply_message", "죄송합니다. 다시 말씀해 주시겠어요?")
                message_placeholder.markdown(full_response)
                status.update(label="대화 모드", state="complete", expanded=False)

    # 3. 최종 응답을 세션 기록에 저장
    st.session_state.messages.append({"role": "assistant", "content": full_response})