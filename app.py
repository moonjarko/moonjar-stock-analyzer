import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Optional
import json
import requests
from datetime import datetime

# ==========================================
# 1. Pydantic 구조 (JSON 파싱 및 강제용)
# ==========================================
class SourceItem(BaseModel):
    title: str = Field(description="출처 매체명 또는 리포트명")
    date: str = Field(description="발행 날짜")
    link: Optional[str] = Field(None, description="가능한 경우 해당 정보의 URL 링크")

class IssueItem(BaseModel):
    date: str
    content: str
    source: str = Field(description="반드시 특정 매체명과 발행일 기재")

class FactSheetItem(BaseModel):
    tone: str = Field(description="'긍정', '중립', '부정' 중 하나만 입력")
    point: str = Field(description="핵심 요약 포인트")
    source: str = Field(description="반드시 특정 매체명과 발행일 기재")

class ReportData(BaseModel):
    reasoning_process: str = Field(description="검색된 최신 데이터를 바탕으로 한 팩트 체크 및 논리적 추론 과정 (가장 먼저 작성할 것)")
    current_price: str = Field(description="확인 불가 시 '데이터 없음'으로 표기")
    price_change_percent: str = Field(description="확인 불가 시 '데이터 없음'으로 표기")
    market_cap: str = Field(description="확인 불가 시 '데이터 없음'으로 표기")
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
    reasoning_process: str = Field(description="검색된 최신 데이터를 바탕으로 한 팩트 체크 및 논리적 추론 과정 (가장 먼저 작성할 것)")
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

class VolatilityCard(BaseModel):
    title: str
    category: str = Field(description="실적, 공시, 업종, 시장, 기타 중 하나")
    description: str = Field(description="추정 금지. 검색된 사실만 서술할 것.")
    impact_level: int = Field(description="영향력 크기 (1~5 점수)")
    source: str = Field(description="반드시 특정 매체명과 발행일 기재")

class VolatilityData(BaseModel):
    reasoning_process: str = Field(description="검색 결과를 바탕으로 주가 변동의 인과관계를 검증한 논리적 추론 과정")
    change_percent: str
    reason_cards: List[VolatilityCard]

class RadarCard(BaseModel):
    name: str
    ticker: str
    market: str
    reason: str
    key_point: str
    attention_level: str = Field(description="주목, 관심, 참고 중 하나")
    source: str = Field(description="반드시 특정 매체명과 발행일 기재")

class RadarData(BaseModel):
    reasoning_process: str = Field(description="검색 결과를 바탕으로 해당 조건에 부합하는 종목을 필터링하고 검증한 기준 및 과정")
    candidates: List[RadarCard]

# ==========================================
# 2. UI 및 Firebase 설정
# ==========================================
st.set_page_config(page_title="Alpha-Logic 분석기", layout="wide")
st.title("📈 Alpha-Logic 주식 분석기 (2.0 Flash / 실시간 검색)")

with st.sidebar:
    st.header("⚙️ 시스템 상태")
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        PROJECT_ID = st.secrets.get("FIREBASE_PROJECT_ID", "")
        st.success("✅ 2.0 Flash (무료 티어 표준 엔진) 가동 중")
    except Exception as e:
        api_key = ""
        PROJECT_ID = ""
        st.error("⚠️ 클라우드 비밀 금고(Secrets) 설정이 필요합니다.")
    st.markdown("---")

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
    try:
        requests.post(url, json=payload)
    except:
        pass

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

history_data = load_history_from_firestore()
if history_data:
    with st.sidebar.expander("📚 가족 최근 분석 기록 (최신순)"):
        for item in reversed(history_data[-15:]):
            if st.button(f"[{item['tab']}] {item['ticker']} ({item['timestamp']})", key=f"btn_{item['timestamp']}"):
                st.session_state[f"cached_{item['tab']}_{item['ticker']}"] = item['json_data']
                st.success(f"{item['ticker']} 데이터를 불러왔습니다. 본문 탭을 확인하세요.")

# ==========================================
# 3. Alpha-Logic 핵심 엔진 (2.0 Flash 적용)
# ==========================================
def ask_alpha_logic(query: str, system_prompt: str, schema_class):
    if not api_key:
        st.warning("API 키가 설정되지 않았습니다.")
        return None
    try:
        client = genai.Client(api_key=api_key)
        
        anti_hallucination_rules = """
        [초강력 통제 규칙: 환각(Hallucination) 방지 지침]
        1. '모름'의 강제화: 실시간 검색 결과에서 명확히 확인되지 않는 수치, 날짜, 사실은 절대 유추하거나 지어내지 마라.
        2. 출처 1:1 매칭: 모든 주요 팩트와 수치 정보에는 검색된 팩트 기반의 출처를 명시하라.
        """
        
        schema_json_string = json.dumps(schema_class.model_json_schema(), ensure_ascii=False)
        enhanced_system_prompt = f"{system_prompt}\n\n{anti_hallucination_rules}\n\n[중요] 출력은 반드시 다음 JSON 스키마 구조를 완벽하게 따르는 순수 JSON 객체여야 한다:\n{schema_json_string}"
        
        # 팩트: 현재 구글 무료 티어에서 검색 도구를 완벽히 지원하는 공식 2.0 모델 적용
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=query,
            config=types.GenerateContentConfig(
                system_instruction=enhanced_system_prompt,
                tools=[{"google_search": {}}],  # 구글 공식 지원 실시간 검색 도구 명칭
                response_mime_type="application/json", # 안정적인 JSON 파싱 복구
                temperature=0.0, 
            )
        )
        return json.loads(response.text)
    except Exception as e:
        st.error(f"엔진 오류 발생: {e}")
        return None

# ==========================================
# 4. 메인 화면 구성 (4개 탭)
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["📋 종합 리포트", "💎 펀더멘털 분석", "⚡ 급등락 원인", "📡 종목 레이더"])

# --- 탭 1 ---
with tab1:
    st.subheader("📋 4대 소스 종합 리포트 분석")
    company_1 = st.text_input("분석할 기업명 입력 (예: 삼성전자):", key="c1")
    
    if st.button("분석 실행", key="b1") and company_1:
        with st.spinner("실시간 구글 검색 및 정밀 분석 중..."):
            sys_p = "너는 Alpha-Logic이다. 구글 검색을 적극 활용하여 해당 기업의 최신 객관적인 정보와 리포트를 조사하라."
            res = ask_alpha_logic(f"{company_1} 종합 분석", sys_p, ReportData)
            if res:
                save_to_firestore(company_1, "종합리포트", res)
                
                with st.expander("🤖 엔진의 논리 검증 과정 (Chain of Thought)"):
                    st.write(res.get('reasoning_process', '기록 없음'))

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("현재가/최근가", res.get('current_price', 'N/A'))
                col2.metric("변동", res.get('price_change_percent', 'N/A'))
                col3.metric("시가총액", res.get('market_cap', 'N/A'))
                col4.metric("업종", res.get('industry_type', 'N/A'))
                
                st.markdown(f"### 🎯 투자의견: **{res.get('consensus_opinion', 'N/A')}** (목표가: {res.get('target_price', 'N/A')})")
                st.info(f"**밸류에이션 요약**: {res.get('valuation_summary', '')}")
                
                c_a, c_b = st.columns(2)
                with c_a:
                    st.markdown("### 📰 검증된 주요 이슈")
                    for issue in res.get('recent_issues', []):
                        st.write(f"- **[{issue.get('date', '')}]** {issue.get('content', '')} *(출처: {issue.get('source', '')})*")
                with c_b:
                    st.markdown("### 🟢🟡🔴 팩트 시트")
                    for fact in res.get('fact_sheets', []):
                        st.write(f"- **{fact.get('tone', '')}** | {fact.get('point', '')} *(출처: {fact.get('source', '')})*")

# --- 탭 2 ---
with tab2:
    st.subheader("💎 본질가치 및 해자 분석")
    company_2 = st.text_input("기업명 입력:", key="c2")
    if st.button("펀더멘털 분석", key="b2") and company_2:
        with st.spinner("실시간 검색 기반 지표 수집 및 논리 구조화 중..."):
            sys_p = "너는 Alpha-Logic이다. 실시간 구글 검색 팩트를 기반으로 업종에 맞는 멀티플을 적용하여 해자와 리스크를 분석하라."
            res = ask_alpha_logic(f"{company_2} 펀더멘털 정밀 분석", sys_p, FundamentalData)
            if res:
                save_to_firestore(company_2, "펀더멘털", res)
                
                with st.expander("🤖 엔진의 논리 검증 과정 (Chain of Thought)"):
                    st.write(res.get('reasoning_process', '기록 없음'))

                st.markdown(f"### 📊 종합 점수: **{res.get('valuation_score', 0)}점** ({res.get('valuation_grade', 'N/A')})")
                st.caption(f"산출 근거: {res.get('valuation_basis', '')}")
                st.table(res.get('details', []))
                
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.markdown("#### 💪 강점 (해자)")
                    for pair in res.get('moat_pairs', []):
                        st.success(pair.get('strength', ''))
                with col_m2:
                    st.markdown("#### 🐻 리스크 (반론)")
                    for pair in res.get('moat_pairs', []):
                        st.error(pair.get('bear_case', ''))

# --- 탭 3 ---
with tab3:
    st.subheader("⚡ 급등락 원인 추적")
    company_3 = st.text_input("종목명 입력:", key="c3")
    period = st.selectbox("기간 선택", ["최근 1주", "최근 1개월", "최근 1년"])
    if st.button("원인 추적", key="b3") and company_3:
        with st.spinner("실시간 뉴스 교차 검증 중..."):
            sys_p = f"너는 Alpha-Logic이다. 구글 검색을 활용해 {period} 동안의 주요 주가 변동 원인을 찾아 분류하라."
            res = ask_alpha_logic(f"{company_3} {period} 주가 변동 원인", sys_p, VolatilityData)
            if res:
                save_to_firestore(f"{company_3}({period})", "급등락", res)
                
                with st.expander("🤖 엔진의 논리 검증 과정 (Chain of Thought)"):
                    st.write(res.get('reasoning_process', '기록 없음'))

                st.subheader(f"변동 요약: {res.get('change_percent', 'N/A')}")
                for card in res.get('reason_cards', []):
                    with st.expander(f"🔥 [{card.get('impact_level', 0)}/5] {card.get('title', '')} ({card.get('category', '')})", expanded=True):
                        st.write(card.get('description', ''))
                        st.caption(f"출처: {card.get('source', '')}")

# --- 탭 4 ---
with tab4:
    st.subheader("📡 종목 레이더 (조건부 스크리닝)")
    condition = st.text_input("조건 입력 (예: 배당 성장주, 턴어라운드 기대주):", value="저PBR 리레이팅")
    if st.button("레이더 가동", key="b4") and condition:
        with st.spinner("구글 검색 기반 스크리닝 진행 중..."):
            sys_p = "너는 Alpha-Logic이다. 구글 검색을 활용해 제시된 조건에 정확히 부합하는 종목을 탐색하고 반드시 그 근거를 명시하라."
            res = ask_alpha_logic(f"조건 [{condition}] 종목 수집", sys_p, RadarData)
            if res:
                save_to_firestore(condition, "레이더", res)
                
                with st.expander("🤖 엔진의 논리 검증 과정 (Chain of Thought)"):
                    st.write(res.get('reasoning_process', '기록 없음'))

                for cand in res.get('candidates', []):
                    with st.container(border=True):
                        st.markdown(f"### {cand.get('name', '')} ({cand.get('ticker', '')})")
                        st.write(f"**근거**: {cand.get('reason', '')}")
                        st.caption(f"출처: {cand.get('source', '')}")
