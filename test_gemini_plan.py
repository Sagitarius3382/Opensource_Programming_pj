import os
import json
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

# Gemini 설정
YOUR_API_KEY = os.getenv("API_KEY")
YOUR_MODEL = os.getenv("MODEL")

if not YOUR_API_KEY or not YOUR_MODEL:
    print("API_KEY 또는 MODEL이 설정되지 않았습니다.")
    exit(1)

genai.configure(api_key=YOUR_API_KEY)

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

model = genai.GenerativeModel(YOUR_MODEL, safety_settings=safety_settings)

system_instruction = """
너는 '커뮤니티 여론 분석을 위한 검색 설계자'야. 
사용자의 질문을 분석해서 어떤 커뮤니티(DCInside, ArcaLive)를 어떤 키워드로 검색할지 구체적인 계획을 세워줘.

[필수 규칙]
1. 사용자가 "여론", "반응", "평가" 등을 물으면 mode="search"로 설정해.
2. **검색어(keyword)는 공식 명칭보다 실제로 커뮤니티에서 많이 쓰이는 '은어'나 '줄임말'을 우선적으로 선택해.** (예: 블루 아카이브 -> 블아, 몰루 / 리그오브레전드 -> 롤)
3. DCInside는 'gallery_id', ArcaLive는 'channel_id'를 반드시 추론해서 options에 포함해야 해. (모르면 'major'나 'breaking' 같은 기본값이라도 넣어)
4. 응답은 반드시 아래 JSON 형식으로만 출력해. (Markdown 코드블럭 없이 순수 JSON만)

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
                "gallery_type": "major", 
                "sort_type": "latest"
            }
        }
    ]
}
"""

# 테스트 질문들
test_queries = [
    "메이플스토리 여론 알려줘",
    "롤 여론은 어때?",
    "블루아카이브 반응 좀 알려줘"
]

for query in test_queries:
    print(f"\n{'='*60}")
    print(f"질문: {query}")
    print(f"{'='*60}")
    
    try:
        response = model.generate_content(
            f"{system_instruction}\n\nUser Input: {query}",
            generation_config={"response_mime_type": "application/json"}
        )
        
        if response.parts:
            result = json.loads(response.text)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("응답 없음")
            
    except Exception as e:
        print(f"오류: {e}")
