import os
import google.generativeai as genai
import streamlit as st

# 환경변수 기능 import (.env 파일)
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

@st.cache_resource
def initialize_gemini():
    # 환경변수에서 API 키 불러오기
    YOUR_API_KEY = os.getenv("API_KEY")

    # 키가 없는 경우 예외 처리
    if not YOUR_API_KEY:
        st.error("API 키를 찾을 수 없습니다. `.env` 파일에 'API_KEY'를 설정해주세요.")
        st.stop()

    # gemini 기본 설정(API & 모델)
    genai.configure(api_key=YOUR_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    print("model loaded...")
    return model

model = initialize_gemini()

# 제목 설정
st.title("Gemini-Bot")

if "chat_session" not in st.session_state:    
    st.session_state["chat_session"] = model.start_chat(history=[])

for content in st.session_state.chat_session.history:
    with st.chat_message("ai" if content.role == "model" else "user"):
        st.markdown(content.parts[0].text)

if prompt := st.chat_input("메시지를 입력하세요."):    
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("ai"):
        response = st.session_state.chat_session.send_message(prompt)        
        st.markdown(response.text)
