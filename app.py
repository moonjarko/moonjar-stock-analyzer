import streamlit as st
from google import genai

st.set_page_config(page_title="API 스캐너")
st.title("🔍 내 API 키 허용 모델 스캐너")

# secrets에서 API 키 로드
api_key = st.secrets.get("GEMINI_API_KEY", "")

if not api_key:
    st.error("⚠️ 클라우드 비밀 금고(Secrets)에 GEMINI_API_KEY가 설정되지 않았습니다.")
else:
    try:
        client = genai.Client(api_key=api_key)
        st.info("구글 API 서버에 접근하여 허용된 모델 리스트를 조회하고 있습니다...")
        
        # API 키에 허가된 전체 모델 목록 요청
        models = client.models.list()
        
        st.success("✅ 조회 성공! 아래 모델들만 현재 API 키로 호출 가능합니다. (이름을 복사해 주세요)")
        
        count = 0
        for model in models:
            # 텍스트 생성(generateContent)을 지원하는 모델만 화면에 출력
            if "generateContent" in getattr(model, "supported_actions", []):
                st.code(model.name)
                count += 1
                
        if count == 0:
            st.error("현재 API 키로 '텍스트 생성'이 가능한 모델이 하나도 할당되어 있지 않습니다. 구글 클라우드에서 API 키를 새로 발급받아야 합니다.")
            
    except Exception as e:
        st.error(f"서버 조회 중 치명적 오류 발생: {e}")
