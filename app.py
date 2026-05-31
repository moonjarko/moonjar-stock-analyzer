import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Optional
import json
import requests
from datetime import datetime

# ==========================================
# 1. Pydantic 구조 (Gemini JSON 파싱용)
# ==========================================
class SourceItem(BaseModel):
    title: str = Field(description="출처 매체명 또는 리포트명")
    date: str = Field(description="발행 날짜")
    link: Optional[str] = Field(None, description="가능한 경우 해당 정보의 URL 링크")

class IssueItem(BaseModel):
    date: str
    content: str
    source: str

class FactSheetItem(BaseModel):
    tone: str = Field(description="'긍정', '중립', '부정' 중 하나만 입력")
    point: str = Field(description="핵심 요약 포인트")
    source: str

# 탭 1 스키마
class ReportData(BaseModel):
    current_price: str
    price_change_percent: str
    market_cap: str
    industry_type: str
    timestamp: str
    recent_issues: List[IssueItem]
    future_issues: List[IssueItem]
    consensus_opinion: str
    target_price: str
    upside_percent: str
    valuation_summary: str
    fact_sheets: List[FactSheetItem]
    catalysts: List[str]
    risks: List[str]

# 탭 2 스키마
class ValuationDetail(BaseModel):
    indicator: str
    peer_compare: str
    history_compare: str
    market_compare: str

class MoatPair(BaseModel):
    strength: str = Field(description="경제적 해자 강점 요소")
    bear_case: str = Field(description="해당 강점을 반박하는 비판적 시선 또는 무너질 위험")

class ReratingScenario(BaseModel):
    before_multiple: str
    after_multiple: str
    upside: str
    logic: str
    status: str
    probability: str

class FundamentalData(BaseModel):
    selected_multiple_type: str
    valuation_score: int
    valuation_grade: str
    valuation_basis: str
    details: List[ValuationDetail]
    moat_grade: str
    moat_pairs: List[MoatPair]
    bottleneck_pairs: List[MoatPair]
    rerating_scenarios: List[ReratingScenario]
    execution_view: str
    execution_basis: str
    attractive_zone: str
    kpi_points: List[str]

# 탭 3 스키마
class VolatilityCard(BaseModel):
    title: str
    category: str = Field(description="실적, 공시, 업종, 시장, 기타 중 하나")
    description: str
    impact_level: int = Field(description="영향력 크기 (1~5 점수)")
    source: str

class VolatilityData(BaseModel):
    change_percent: str
    reason_cards: List[VolatilityCard]

# 탭 4 스키마
class RadarCard(BaseModel):
    name: str
    ticker: str
    market: str
    reason: str
    key_point: str
    attention_level: str = Field(description="주목, 관심, 참고 중 하나")
    source: str

class RadarData(BaseModel):
    candidates: List[RadarCard]

# ==========================================
# 2. UI 및 Firebase 설정
# ==========================================
st.set_page_config(page_title="Alpha-Logic 분석기", layout="wide")
st.title("📈 Alpha-Logic 주식 분석기 (v2.0 Gemini+Firestore)")

with st.sidebar:
    st.header("⚙️ 시스템 상태")
    # Streamlit 클라우드 비밀 금고에서 키를 자동으로 꺼내옵니다.
    api_key = st.secrets["GEMINI_API_KEY"]
    PROJECT_ID = st.secrets.get("FIREBASE_PROJECT_ID", "")
    
    st.success("✅ Alpha-Logic 엔진 가동 중")
    st.caption("가족 공용 모드로 안전하게 연결되었습니다.")
    st.markdown("---")

# --- Firebase 데이터베이스 REST API ---
def save_to_firestore(ticker, tab_name, data):
    if not PROJECT_ID: return
    url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents/analysis_logs"
    payload = {
        "fields": {
            "ticker": {"stringValue": ticker},
            "tab": {"stringValue": tab_name},
            "json_data": {"stringValue": json.dumps(data, ensure_ascii=False)},
            "timestamp": {"stringValue": datetime.now().strftime("%Y-%m-%d %H:%M")}
        }
    }
    requests.post(url, json=payload)

def load_history_from_firestore():
    if not PROJECT_ID: return []
    url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents/analysis_logs"
    try:
        res = requests.get(url)
        if res.status_code == 200:
            docs = res.json().get('documents', [])
            history = []
            for doc in docs:
                fields = doc['fields']
                history.append({
                    "ticker": fields['ticker']['stringValue'],
                    "tab": fields['tab']['stringValue'],
                    "json_data": json.loads(fields['json_data']['stringValue']),
                    "timestamp": fields['timestamp']['stringValue']
                })
            return history
    except:
        return []
    return []

# 사이드바 기록 불러오기 UI
history_data = load_history_from_firestore()
if history_data:
    with st.sidebar.expander("📚 가족 최근 분석 기록 (최신순)"):
        for item in reversed(history_data[-15:]):
            if st.button(f"[{item['tab']}] {item['ticker']} ({item['timestamp']})", key=f"btn_{item['timestamp']}"):
                st.session_state[f"cached_{item['tab']}_{item['ticker']}"] = item['json_data']
                st.success(f"{item['ticker']} 데이터를 불러왔습니다. 본문 탭을 확인하세요.")

# 공통 프롬프트 호출 함수
def ask_alpha_logic(query: str, system_prompt: str, schema_class):
    if not api_key:
        st.warning("왼쪽 사이드바에 API Key를 먼저 입력해 주세요.")
        return None
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-1.5-pro-002',
            contents=query,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=[{"google_search": {}}], 
                response_mime_type="application/json",
                response_schema=schema_class,
                temperature=0.15,
            )
        )
        return json.loads(response.text)
    except Exception as e:
        st.error(f"오류 발생: {e}")
        return None

# ==========================================
# 3. 메인 화면 구성 (4개 탭)
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["📋 종합 리포트", "💎 펀더멘털 분석", "⚡ 급등락 원인", "📡 종목 레이더"])

# --- 탭 1 ---
with tab1:
    st.subheader("📋 4대 소스 종합 리포트 분석")
    company_1 = st.text_input("분석할 기업명 입력 (예: 삼성전자):", key="c1")
    
    if st.button("분석 실행", key="b1") and company_1:
        with st.spinner("데이터 수집 중..."):
            sys_p = "너는 Alpha-Logic이다. 최근 1개월 이내의 뉴스, 공시, 리포트를 전수조사하라."
            res = ask_alpha_logic(f"{company_1} 종합 분석", sys_p, ReportData)
            if res:
                save_to_firestore(company_1, "종합리포트", res)
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("현재가", res['current_price'])
                col2.metric("전일대비", res['price_change_percent'])
                col3.metric("시가총액", res['market_cap'])
                col4.metric("업종/시각", f"{res['industry_type']} / {res['timestamp']}")
                st.write(f"**목표가**: {res['target_price']}")
                
# --- 탭 2 ---
with tab2:
    st.subheader("💎 본질가치 및 해자 분석")
    company_2 = st.text_input("기업명 입력:", key="c2")
    if st.button("펀더멘털 분석", key="b2") and company_2:
        with st.spinner("밸류에이션 분석 중..."):
            sys_p = "너는 Alpha-Logic이다. 밸류에이션과 해자(강점/리스크 쌍)를 분석하라."
            res = ask_alpha_logic(f"{company_2} 펀더멘털 분석", sys_p, FundamentalData)
            if res:
                save_to_firestore(company_2, "펀더멘털", res)
                st.markdown(f"### 📊 밸류에이션 점수: **{res['valuation_score']}점**")
                st.table(res['details'])

# --- 탭 3 ---
with tab3:
    st.subheader("⚡ 급등락 원인 추적")
    company_3 = st.text_input("종목명 입력:", key="c3")
    period = st.selectbox("기간", ["오늘", "1주", "1개월"])
    if st.button("원인 추적", key="b3") and company_3:
        with st.spinner("원인 역추적 중..."):
            sys_p = "너는 Alpha-Logic이다. 해당 기간의 주가 변동 원인을 찾아라."
            res = ask_alpha_logic(f"{company_3} {period} 원인", sys_p, VolatilityData)
            if res:
                save_to_firestore(f"{company_3}({period})", "급등락", res)
                st.subheader(f"변동률: {res['change_percent']}")
                for card in res['reason_cards']:
                    st.write(f"- {card['title']} (영향력: {card['impact_level']})")

# --- 탭 4 ---
with tab4:
    st.subheader("📡 종목 레이더")
    condition = st.text_input("조건 입력:", value="저PBR 리레이팅")
    if st.button("레이더 가동", key="b4") and condition:
        with st.spinner("종목 스크리닝 중..."):
            sys_p = "너는 Alpha-Logic이다. 조건에 부합하는 종목 5개를 수집하라."
            res = ask_alpha_logic(f"조건 [{condition}] 종목 수집", sys_p, RadarData)
            if res:
                save_to_firestore(condition, "레이더", res)
                for cand in res['candidates']:
                    st.write(f"**{cand['name']}**: {cand['key_point']}")
