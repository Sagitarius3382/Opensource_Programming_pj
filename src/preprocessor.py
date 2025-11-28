import h2o
import pandas as pd
import os
import pickle
from datetime import datetime
from konlpy.tag import Okt
from sklearn.feature_extraction.text import TfidfVectorizer
import joblib 

# --- 경로 및 환경 설정 ---
# 스크립트가 위치한 디렉토리를 기준으로 경로를 설정합니다.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 모델과 벡터라이저가 위치할 후보 폴더들 (우선순위: models 폴더 -> 현재 폴더)
MODEL_DIR = os.path.join(BASE_DIR, 'models')
if not os.path.exists(MODEL_DIR):
    MODEL_DIR = BASE_DIR

# 파일명 설정 (실제 저장된 모델 파일명과 일치해야 합니다)
# 주의: h2o.save_model()은 기본적으로 모델 ID를 파일명으로 저장하므로,
# 실제 파일명을 확인 후 필요하다면 아래 변수나 파일명을 수정하세요.
MODEL_FILENAME = "GLM_Classification_Model" 
VECTORIZER_FILENAME = "tfidf_vectorizer.pkl"

# 전체 경로 구성
MODEL_PATH = os.path.join(MODEL_DIR, MODEL_FILENAME)
VECTORIZER_PATH = os.path.join(MODEL_DIR, VECTORIZER_FILENAME)

# 혐오 판단 임계값 (해당 수치 이상이면 혐오로 간주)
HATE_THRESHOLD = 0.88 

# 형태소 분석기 전역 인스턴스
okt = Okt()

def init_h2o(max_mem_size="4G"):
    """
    H2O 클러스터를 초기화합니다.
    이미 실행 중이라면 연결을 시도합니다.
    
    Args:
        max_mem_size (str): H2O 인스턴스 최대 메모리 사용량 (기본 "1G")
    """
    try:
        h2o.init(max_mem_size=max_mem_size)
        print("[정보] H2O 클러스터가 성공적으로 초기화되었습니다.")
    except Exception as e:
        print(f"[오류] H2O 초기화 실패: {e}")
        raise

def load_resources(model_path, vectorizer_path):
    """
    저장된 H2O 모델(Binary)과 TF-IDF 벡터라이저를 로드합니다.
    """
    # 파일 존재 여부 확인
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"모델 파일을 찾을 수 없습니다: {model_path}\n'models' 폴더에 파일을 위치시키거나 경로를 확인해주세요.")
    if not os.path.exists(vectorizer_path):
        raise FileNotFoundError(f"벡터라이저 파일을 찾을 수 없습니다: {vectorizer_path}")

    try:
        # H2O Binary 모델 로드
        model = h2o.load_model(model_path)
        print(f"[정보] 모델 로드 완료: {os.path.basename(model_path)}")
        
        # Vectorizer 로드
        with open(vectorizer_path, 'rb') as f:
            try:
                vectorizer = pickle.load(f)
            except Exception:
                # pickle 로딩 실패 시 joblib 시도 (호환성 확보)
                try:
                    vectorizer = joblib.load(f)
                except Exception:
                    raise IOError("Vectorizer 로딩에 실패했습니다 (pickle/joblib 모두 실패).")

        print(f"[정보] 벡터라이저 로드 완료: {os.path.basename(vectorizer_path)}")
        
        return model, vectorizer
    except Exception as e:
        print(f"[오류] 리소스 로드 중 문제 발생: {e}")
        raise

def tokenize(text):
    """
    KoNLPy Okt를 사용하여 텍스트를 토큰화합니다.
    조사, 어미, 구두점을 제외하고 어간(Stem)을 추출합니다.
    """
    if pd.isna(text) or not isinstance(text, str):
        return ""
    
    EXCLUDE_POS = ['Josa', 'Eomi', 'Punctuation']
    try:
        # stem=True 옵션으로 어간 추출
        tokens = [word for word, pos in okt.pos(text, stem=True) if pos not in EXCLUDE_POS]
        return " ".join(tokens)
    except Exception as e:
        # 에러 발생 시 빈 문자열 반환 및 로그 출력
        print(f"[경고] 토큰화 오류 (텍스트: '{text[:20]}...'): {e}")
        return ""

def batch_predict(texts, model, vectorizer):
    """
    여러 텍스트 리스트를 입력받아 일괄(Batch)로 혐오 확률을 예측합니다.
    속도 향상을 위해 H2O의 병렬 처리를 활용합니다.
    """
    if not texts:
        return []
    
    # 1. 일괄 토큰화 (가장 시간이 많이 소요되는 작업)
    print(f"[진행] {len(texts)}개 텍스트 항목 토큰화 중...")
    tokenized_texts = [tokenize(text) for text in texts]
    
    # 2. 벡터화 (Sparse Matrix 생성)
    # 데이터가 매우 클 경우 메모리 이슈가 있을 수 있으나, 일반적인 CSV 규모에서는 문제없음
    try:
        X_vec = vectorizer.transform(tokenized_texts)
    except Exception as e:
        print(f"[오류] 벡터화 변환 실패: {e}")
        return [0.0] * len(texts)
        
    # 3. H2OFrame 변환 준비
    # feature_names는 학습 때와 동일해야 함
    feature_names = [f'feature_{i}' for i in range(X_vec.shape[1])]
    
    # Sparse Matrix -> Dense DataFrame -> H2OFrame
    # (참고: 대용량 처리 시 이 부분에서 메모리 최적화가 필요할 수 있음)
    X_df = pd.DataFrame(X_vec.toarray(), columns=feature_names)
    hf = h2o.H2OFrame(X_df)
    
    # 4. H2O 예측 실행
    print("[진행] H2O 모델 예측 수행 중...")
    predictions = model.predict(hf)
    result = predictions.as_data_frame(use_multi_thread=True)
    
    # 5. 결과 추출 (혐오일 확률)
    # 모델에 따라 확률 컬럼명이 다를 수 있으므로 순차적으로 확인
    if 'hate' in result.columns:
        return result['hate'].tolist()
    elif 'p1' in result.columns:
        return result['p1'].tolist()
    
    # 컬럼을 찾지 못한 경우 디버깅 정보를 출력합니다.
    print(f"[오류] 예측 결과에 확률 컬럼('hate' 또는 'p1')이 없습니다.")
    print(f"      발견된 컬럼 목록: {result.columns.tolist()}")
    return [0.0] * len(texts)

def filter_hate_speech(df, model_path=MODEL_PATH, vectorizer_path=VECTORIZER_PATH):
    """
    데이터프레임의 Title, Content, Comments를 검사하여 혐오 표현을 필터링합니다.
    모든 텍스트를 모아서 배치 처리를 수행하므로 속도가 빠릅니다.
    """
    # 🌟🌟🌟 수정 지점: h2o.init 옵션을 여기에 직접 전달합니다. 🌟🌟🌟
    # ip와 start_h2o 옵션을 init_h2o 함수에 전달하여 H2O 클러스터에 연결을 시도합니다.
    init_h2o()
    
    model, vectorizer = load_resources(model_path, vectorizer_path)
    
    # 1. 모든 텍스트 수집 및 인덱싱
    all_texts_to_predict = []
    text_map = [] # (행 인덱스, 항목 타입, 댓글 인덱스)

    for index, row in df.iterrows():
        # 제목 (Title)
        all_texts_to_predict.append(row.get('Title', ''))
        text_map.append((index, 'Title', None))

        # 본문 (Content)
        all_texts_to_predict.append(row.get('Content', ''))
        text_map.append((index, 'Content', None))

        # 댓글 (Comments) - ' ||| '로 구분됨
        comments_str = row.get('Comments', '')
        if pd.notna(comments_str) and comments_str:
            comment_list = comments_str.split(' ||| ')
            for c_idx, comment in enumerate(comment_list):
                comment = comment.strip()
                # 빈 댓글이나 http 링크는 예측에서 제외 (속도 최적화)
                if comment and not comment.lower().startswith('http'):
                    all_texts_to_predict.append(comment)
                    text_map.append((index, 'Comment', c_idx))
    
    if not all_texts_to_predict:
        print("[정보] 분석할 텍스트가 없습니다.")
        return df
        
    # 2. 배치 예측 실행
    print(f"[시작] 총 {len(all_texts_to_predict)}개 항목에 대한 배치 분석 시작...")
    # 수정된 batch_predict 호출 ('hate' 또는 'p1' 컬럼 값 자동 감지)
    hate_probs = batch_predict(all_texts_to_predict, model, vectorizer)
    print("[완료] 배치 예측 완료.")

    # 3. 예측 결과를 구조화
    # 인덱스별로 결과를 그룹화하여 쉽게 조회할 수 있게 만듭니다.
    prediction_results = list(zip(text_map, hate_probs))
    
    # 기본값 설정
    row_data = {index: {'Title': 0.0, 'Content': 0.0, 'Comments': {}} for index in df.index}
    
    for (r_idx, item_type, c_idx), p_score in prediction_results:
        if item_type == 'Title':
            row_data[r_idx]['Title'] = p_score
        elif item_type == 'Content':
            row_data[r_idx]['Content'] = p_score
        elif item_type == 'Comment':
            row_data[r_idx]['Comments'][c_idx] = p_score

    # 4. 필터링 로직 적용
    filtered_rows = []
    dropped_rows = []
    
    for index, row in df.iterrows():
        original_row = row.copy()
        current_data = row_data[index]
        
        # 4.1. 제목 및 본문 혐오 체크 (발견 시 행 전체 삭제)
        if current_data['Title'] >= HATE_THRESHOLD:
            dropped_rows.append({'reason': 'Title Hate', 'p_hate': current_data['Title'], 'data': original_row.to_dict()})
            continue
            
        if current_data['Content'] >= HATE_THRESHOLD:
            dropped_rows.append({'reason': 'Content Hate', 'p_hate': current_data['Content'], 'data': original_row.to_dict()})
            continue

        # 4.2. 댓글 필터링 (혐오 댓글만 제거하고 행은 유지)
        comments_str = row.get('Comments', '')
        
        if pd.notna(comments_str) and comments_str:
            comment_list = comments_str.split(' ||| ')
            clean_comments_list = []
            
            # 예측 결과 맵
            comment_predictions = current_data['Comments']

            for c_idx, comment in enumerate(comment_list):
                comment = comment.strip()
                if not comment: continue

                # 링크 필터링 (예측 건너뛴 항목)
                if comment.lower().startswith('http'):
                    continue

                # 혐오 점수 확인 (예측을 수행하지 않은 항목은 0.0)
                p_score = comment_predictions.get(c_idx, 0.0)
                
                if p_score >= HATE_THRESHOLD:
                    # 혐오 댓글 기록
                    dropped_rows.append({
                        'reason': 'Comment Hate', 
                        'p_hate': p_score, 
                        'data': {'PostID': row.get('PostID'), 'Comment': comment}
                    })
                else:
                    # 정상 댓글 유지
                    clean_comments_list.append(comment)
            
            # 정제된 댓글로 업데이트
            row['Comments'] = " ||| ".join(clean_comments_list)
        
        filtered_rows.append(row)
        
    # 5. 결과 저장 및 로그 출력
    filtered_df = pd.DataFrame(filtered_rows)
    
    # 제거된 항목 로그 저장
    if dropped_rows:
        log_dir = os.path.join(BASE_DIR, 'logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f'dropped_hate_speech_{timestamp}.csv')
        
        log_df = pd.DataFrame([
            {'Reason': item['reason'], 'PHate': item['p_hate'], **item['data']} 
            for item in dropped_rows
        ])
        
        # [수정] 오직 로그 파일(사람 확인용)에 대해서만 줄바꿈 제거 적용
        # Title, Content, Comments, Comment 등 텍스트 컬럼이 존재하면 공백으로 치환
        if not log_df.empty:
            for col in ['Title', 'Content', 'Comments', 'Comment']: 
                if col in log_df.columns:
                    log_df[col] = log_df[col].apply(lambda x: x.replace('\n', ' ') if isinstance(x, str) else x)

        log_df.to_csv(log_file, index=False, encoding='utf-8-sig')
        print(f"[결과] {len(dropped_rows)}개의 혐오 콘텐츠가 필터링되었습니다.")
        print(f"      상세 로그: {log_file}")
        
    # H2O 리소스 정리
    if h2o.cluster().get_status() == "running":
        h2o.cluster().shutdown()
        
    return filtered_df

# --- 실행 예시 (Github 업로드 시 사용자 가이드용) ---
if __name__ == "__main__":
    # 데이터 폴더 경로 설정 (data 폴더가 없으면 생성하거나 경로 수정 필요)
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    INPUT_FILE = "test_ARCA_breaking_맨유.csv" # 테스트용 파일명
    INPUT_PATH = os.path.join(DATA_DIR, INPUT_FILE)
    
    print(f"--- 혐오 표현 필터링 시작 ---")
    print(f"입력 파일 경로: {INPUT_PATH}")
    
    if os.path.exists(INPUT_PATH):
        try:
            # 데이터 로드
            df = pd.read_csv(INPUT_PATH)
            
            # 필터링 수행
            filtered_df = filter_hate_speech(df)
            
            # 결과 저장
            OUTPUT_FILE = f"filtered_{INPUT_FILE}"
            OUTPUT_PATH = os.path.join(DATA_DIR, OUTPUT_FILE)
            
            filtered_df.to_csv(OUTPUT_PATH, index=False, encoding='utf-8-sig')
            print(f"[완료] 필터링된 데이터가 저장되었습니다: {OUTPUT_PATH}")
            
        except Exception as e:
            print(f"[오류] 처리 중 예외 발생: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"[경고] 입력 파일을 찾을 수 없습니다. '{DATA_DIR}' 폴더에 '{INPUT_FILE}'이 있는지 확인해주세요.")