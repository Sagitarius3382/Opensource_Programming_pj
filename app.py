import os
import json
import time
import re
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
    너는 '커뮤니티 키워드 검색을 위한 검색 설계자'야. 
    사용자의 질문을 분석해서 어떤 커뮤니티(DCInside, ArcaLive 둘 중 하나)를 어떤 키워드로 검색할지 구체적인 계획을 세워줘.
    
    [필수 규칙]
    1. 사용자가 "여론", "반응", "평가" , "의견" , "근황" 등 키워드 검색이 가능한 것을 물으면 mode="search"로 설정해.
    2. **검색어(keyword)는 공식 명칭보다 실제로 커뮤니티에서 많이 쓰이는 '은어'나 '줄임말'을 우선적으로 선택해.** (예: 블루 아카이브 -> 블아, 리그오브레전드 -> 롤, 맨체스터 유나이티드 -> 맨유)
    3. **[타겟 선정]** 특정 사이트 언급이 없으면, 해당 주제가 활발한 곳을 자동으로 판단하되 **잘 모르겠거나 대중적인 게임/이슈라면 ["dc", "arca"] 두 곳에 대해 task를 총 2개 생성해야해.**
    4. 일반적인 경우에는 통합검색을 우선시 하되, 명확한 타겟 갤러리가 존재할 경우(DCInside는 'gallery_id'를 확인해서 task['options']에 포함해야 해.
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
                "keyword": "검색어, 검색결과가 좋을 것이라고 생각되면 은어, 줄임말 적극적으로 사용. 특정 주제의 갤러리 검색 시 주제 관련 단어는 제거. (예: 원신 갤러리 검색 시, '원신 필수캐' -> '필수캐')",
                "options": {
                    # dc, arca 공통 파라미터
                    "end_page": "종료 페이지 (커뮤니티 하나만 탐색할 때는 '2', 두 곳 모두(len(tasks) == 2)일 때는 '1')",

                    # "target_source" == "dc" 일 때 입력할 내용
                    "gallery_id": "키워드를 검색할 갤러리의 갤러리 ID (예: 'maplestory_new', 'leagueoflegends6', 'chzzk'). 모르거나 통합검색이 적합할 경우 null ",
                    "gallery_type": "gallery_id값에 해당하는 갤러리의 종류로 다음 둘 중 하나 ('major' | 'minor'). 통합검색이 적합할 경우 null", 
                    "sort_type": "latest"

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
            print(f"[DEBUG] Crawling Task:")
            print(f"  - Target: {target}")
            print(f"  - Keyword: {keyword}")
            print(f"  - Options: {options}")
            
            # search_community(target_source, keyword, **kwargs)
            # 기본적으로 1~2페이지만 긁도록 설정 (속도 위해)
            future = executor.submit(search_community, target, keyword, **options)
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
    """
    수집된 데이터를 바탕으로 최종 보고서를 스트리밍 방식으로 작성합니다.
    (수정: 텍스트 스트리밍 + 히든 JSON 데이터 전송 방식 적용)
    """
    model = get_gemini_model()
    
    if df.empty:
        return None
        
    summary_text = ""
    
    # 컬럼명 처리 (대소문자 무관하게 동작하도록 안전장치)
    cols = {c.lower(): c for c in df.columns}
    title_col = cols.get('title', 'Title')
    content_col = cols.get('content', 'Content')

    # enumerate를 사용하여 1번부터 인덱스 부여
    for i, (idx, row) in enumerate(df.head(30).iterrows()):
        title = row.get(title_col, "No Title")
        # [수정] 본문 150자 제한 (이미 잘려있겠지만 안전장치 및 프롬프트 최적화)
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
    
    [보고서 포함 항목]
    1. **3줄 요약**: 전체적인 여론의 핵심 요약
    2. **긍정 여론**: 유저들이 긍정적으로 평가하는 요소
    3. **부정 여론**: 유저들이 불만이나 비판을 제기하는 요소
    4. **주요 논쟁**: 현재 가장 뜨거운 감자나 논쟁거리
    5. **종합 평가**: 결론 및 제언
    
    [특별 지시사항 - 데이터 구조]
    **중요:** 보고서 본문 작성이 모두 끝나면, 반드시 `__REF_DATA__` 라는 구분자를 출력하고, 그 바로 뒤에 분석에 가장 도움이 된 핵심 게시글의 ID 목록을 JSON 형식으로 출력해주세요. (마크다운 블록 없이 순수 텍스트로 출력)
    
    형식 예시:
    (보고서 내용...)
    ... 감사합니다.
    
    __REF_DATA__
    {{"reference_ids": [1, 5, 10]}}
    """
    # __REF_DATA__ 쪽은 실제로 채팅에 출력 안되도록 설정되어있음
    # 스트리밍 활성화 (stream=True)
    # JSON 모드는 스트리밍 뷰를 망치므로 해제하고 텍스트 모드로 받음
    return model.generate_content(prompt, stream=True)

# --------------------------------------------------------------------------
# 5. 메인 로직 
# --------------------------------------------------------------------------
st.title("🕵️‍♂️ Community Insight Bot")
st.caption("AI가 자동으로 커뮤니티를 선정하고 커뮤니티 기반 정보와 여론을 분석합니다.")

if "messages" not in st.session_state:
    st.session_state.messages = []
    welcome_msg = "안녕하세요! 궁금한 게임, 인물, 이슈 등을 물어봐주세요. 제가 적절한 커뮤니티를 찾아 관련 내용을 종합해드릴게요. 단순한 단어 보다는 현재 상황을 알려주시면 더 확실한 결과를 찾아드릴 수 있어요!"
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
                    # [수정] 수집 단계에서 미리 본문 길이 150자로 제한 (성능 향상)
                    if 'Content' in raw_df.columns:
                        raw_df['Content'] = raw_df['Content'].astype(str).str.slice(0, 150)

                    initial_count = len(raw_df)
                    status.write(f"✅ 총 {initial_count}건의 데이터를 수집했습니다.")
                    status.update(label="혐오 표현을 필터링하고 있습니다...", state="running")
                    
                    # [Step 3] 혐오 표현 필터링
                    try:
                        clean_df = filter_hate_speech(raw_df)
                        
                        # [수정] 최신 30건만 사용하도록 자르기
                        target_df = clean_df.head(30)
                        
                        final_count = len(clean_df)
                        filtered_count = initial_count - final_count
                        
                        # [수정] 필터링 결과 메시지 구체화
                        msg = f"🧹 **필터링 완료**: {filtered_count}건의 부적절한 게시물을 제외했습니다. (남은 데이터: {final_count}건"
                        if final_count > 30:
                            msg += " 중 최신의 30건을 사용합니다.)"
                        else:
                            msg += ")"
                        status.write(msg)
                            
                    except Exception as e:
                        st.warning(f"필터링 중 오류 발생: {e}")
                        clean_df = raw_df
                        target_df = clean_df.head(30)
                    
                    status.update(label="최종 보고서를 작성하고 있습니다...", state="running")
                    
                    # [Step 4] 보고서 작성 (스트리밍 + 히든 JSON)
                    try:
                        response_stream = generate_report(prompt, target_df)
                        
                        full_buffer = ""
                        json_part = None
                        
                        # 스트리밍 루프
                        for chunk in response_stream:
                            if chunk.text:
                                full_buffer += chunk.text
                                
                                # 구분자가 있는지 확인
                                if "__REF_DATA__" in full_buffer:
                                    # 구분자 이전까지만 화면에 출력 (JSON 데이터 숨김)
                                    visible_text = full_buffer.split("__REF_DATA__")[0]
                                    message_placeholder.markdown(visible_text + "▌")
                                else:
                                    # 구분자가 없으면 전체 출력
                                    message_placeholder.markdown(full_buffer + "▌")
                        
                        # 스트리밍 완료 후 후처리
                        parts = full_buffer.split("__REF_DATA__")
                        report_content = parts[0].strip()
                        full_response = report_content # 최종 저장용
                        
                        # JSON 파싱 시도
                        ref_ids = []
                        if len(parts) > 1:
                            try:
                                json_str = parts[1].strip()
                                # 혹시 모를 마크다운 코드블록 제거
                                json_str = json_str.replace("```json", "").replace("```", "").strip()
                                json_data = json.loads(json_str)
                                ref_ids = json_data.get("reference_ids", [])
                            except json.JSONDecodeError:
                                print(f"[DEBUG] JSON Parsing failed: {parts[1]}")

                        # [UI 구성 1] AI 추천 링크 섹션 추가
                        if ref_ids:
                            full_response += "\n\n---\n### 🔗 AI가 참고한 핵심 게시글\n"
                            
                            # URL 및 Title 컬럼 찾기 (대소문자 무관)
                            cols = {c.lower(): c for c in target_df.columns}
                            url_col = cols.get('posturl') or cols.get('url') or cols.get('link')
                            title_col = cols.get('title', 'Title')

                            if url_col:
                                # ref_id는 1부터 시작하는 순번이므로, 인덱스는 ref_id - 1
                                for ref_id in ref_ids:
                                    target_idx = ref_id - 1
                                    if 0 <= target_idx < len(target_df):
                                        row = target_df.iloc[target_idx]
                                        full_response += f"- [{row[title_col]}]({row[url_col]})\n"
                            else:
                                st.warning("URL 컬럼을 찾을 수 없어 링크를 표시할 수 없습니다.")
                        
                        # 최종 완성된 텍스트 출력 (커서 제거)
                        message_placeholder.markdown(full_response)
                        
                        # [UI 구성 2] 사용된 전체 게시글 목록 출력 (Status 내부)
                        if not target_df.empty:
                            st.markdown("---")
                            st.subheader(f"📑 사용된 전체 게시글 ({len(target_df)}건)")
                            
                            cols = {c.lower(): c for c in target_df.columns}
                            url_col = cols.get('posturl') or cols.get('url') or cols.get('link')
                            title_col = cols.get('title', 'Title')
                            
                            for i, (idx, row) in enumerate(target_df.iterrows()):
                                title_text = row.get(title_col, "No Title")
                                url_text = row.get(url_col, "#")
                                st.markdown(f"**{i + 1}.** [{title_text}]({url_text})")

                    except Exception as e:
                        full_response += f"\n\n(분석 중 오류 발생: {str(e)})"
                        message_placeholder.markdown(full_response)
                        print(f"[DEBUG] Report generation error: {e}")

                    # 상태창 닫기 및 라벨 업데이트
                    status.update(label="분석 완료! (클릭하여 전체 수집 목록 확인)", state="complete", expanded=False)
                        
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