import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Optional
import json
import requests
import re
from datetime import datetime

# ==========================================
# 1. Pydantic 구조 (Gemini JSON 파싱 및 CoT 강제용)
# ==========================================
class SourceItem(BaseModel):
    title: str = Field(description="출처 매체명 또는 리포트명")
    date: str = Field(description="발행 날짜")
    link: Optional[str] = Field(None, description="가능한 경우 해당 정보의 URL 링크")

class IssueItem(BaseModel):
    date: str
    content: str
    source: str = Field(description="엔진 내부 지식 기반 출처 (모르면 '확인 불가' 기재)")

class FactSheetItem(BaseModel):
    tone: str = Field(description="'긍정', '중립', '부정' 중 하나만 입력")
    point: str = Field(description="핵심 요약 포인트")
    source: str = Field(description="엔진 내부 지식 기반 출처 (모르면 '확인 불가' 기재)")

class ReportData(BaseModel):
    reasoning_process: str = Field(description="사전 학습된 데이터를 바탕으로 한 팩트 체크 및 논리적 추론 과정 (가장 먼저 작성할 것)")
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
    reasoning_process: str = Field(description="사전 학습된 데이터를 바탕으로 한 팩트 체크 및 논리적 추론 과정 (가장 먼저 작성할 것)")
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
    description: str = Field(description="추정 금지. 확인 가능한 사실만 서술할 것.")
    impact_level: int = Field(description="영향력 크기 (1~5 점수)")
    source: str = Field(description="엔진 내부 지식 기반 출처 (모르면 '확인 불가' 기재)")

class VolatilityData(BaseModel):
    reasoning_process: str = Field(description="주가 변동의 인과관계를 검증한 논리적 추론 과정")
    change_percent: str
    reason_cards: List[VolatilityCard]

class RadarCard(BaseModel):
    name: str
    ticker: str
    market: str
    reason: str
    key_point: str
    attention_level: str = Field(description="주목, 관심, 참고 중 하나")
    source: str = Field(description="엔진 내부 지식 기반 출처 (모르면 '확인 불가' 기재)")

class RadarData(BaseModel):
    reasoning_process: str = Field(description="해당 조건에 부합하는 종목을 필터링하고 검증한 기준 및 과정")
    candidates: List[RadarCard]

# ==========================================
# 2. UI 및 Firebase 설정
# ==========================================
st.set_page_config(page_title="Alpha-Logic 분석기", layout="wide")
st.title("📈 Alpha-Logic 주식 분석기 (오프라인 통제 모드)")

with st.sidebar:
    st.header("⚙️ 시스템 상태")
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        PROJECT_ID = st.secrets.get("FIREBASE_PROJECT_ID", "")
        st.success("✅ 1.5 Flash (검색 제외 / 에러 우회 모드) 가동 중")
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
# 3. Alpha-Logic 핵심 엔진 (검색 기능 완전 배제)
# ==========================================
def ask_alpha_logic(query: str, system_prompt: str, schema_class):
    if not api_key:
        st.warning("API 키가 설정되지 않았습니다.")
        return None
    try:
        client = genai.Client(api_key=api_key)
        
        anti_hallucination_rules = """
        [초강력 통제 규칙: 환각(Hallucination) 방지 지침]
        1. '모름'의 강제화: 사전 학습된 지식 내에서 명확히 확인되지 않는 수치, 날짜, 사실은 절대 유추하거나 지어내지 마라. 반드시 '데이터 없음' 또는 '확인 불가'로 기재하라.
        2. 마크다운 완전 금지: 시작과 끝에 ```json 이나 
``` 같은 기호를 절대 붙이지 말고 오직 순수한 JSON 중괄호 {} 만 출력하라.
        """
        
        schema_json_string = json.dumps(schema_class.model_json_schema(), ensure_ascii=False)
        enhanced_system_prompt = f"{system_prompt}\n\n{anti_hallucination_rules}\n\n[중요] 출력은 반드시 다음 JSON 스키마 구조를 완벽하게 따르는 순수 JSON 객체여야 한다:\n{schema_json_string}"
        
        response = client.models.generate_content(
            model='gemini-1.5-flash',  # 무료 할당량이 보장된 1.5 Flash
            contents=query,
            config=types.GenerateContentConfig(
                system_instruction=enhanced_system_prompt,
                # tools 파라미터가 원천 제거되었습니다. (404/429 에러 방지)
                temperature=0.0, 
            )
        )
        
        # JSON 클렌징 (마크다운 기호 제거)
        raw_text = response.text.strip()
        raw_text = re.sub(r"^```json\s*", "", raw_text)
        raw_text = re.sub(r"^
```\s*", "", raw_text)
        raw_text = re.sub(r"\s*
