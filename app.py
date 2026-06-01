import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Optional
import json
import requests
import re
from datetime import datetime
import yfinance as yf

# ==========================================
# 1. Pydantic 구조 (단문 적용으로 SyntaxError 방지)
# ==========================================
class SourceItem(BaseModel):
    title: str = Field(description="출처 매체명")
    date: str = Field(description="발행 날짜")
    link: Optional[str] = Field(None, description="URL 링크")

class IssueItem(BaseModel):
    date: str
    content: str
    source: str = Field(description="출처")

class FactSheetItem(BaseModel):
    tone: str = Field(description="긍정, 중립, 부정 중 택1")
    point: str = Field(description="요약 포인트")
    source: str = Field(description="출처")

class ReportData(BaseModel):
    reasoning_process: str = Field(description="팩트 체크 및 추론 과정")
    current_price: str = Field(description="프롬프트 주입 데이터 우선 사용")
    price_change_percent: str = Field(description="프롬프트 주입 데이터 우선 사용")
    market_cap: str = Field(description="프롬프트 주입 데이터 우선 사용")
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
    strength: str = Field(description="해자 강점")
    bear_case: str = Field(description="반론 및 리스크")

class ReratingScenario(BaseModel):
    before_multiple: str
    after_multiple: str
    upside: str
    logic: str
    status: str
    probability: str

class FundamentalData(BaseModel):
    reasoning_process: str = Field(description="팩트 체크 및 추론 과정")
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
    category: str = Field(description="실적, 공시, 업종, 시장, 기타")
    description: str = Field(description="확인된 사실만 서술")
    impact_level: int = Field(description="1~5 점수")
    source: str = Field(description="출처")

class VolatilityData(BaseModel):
    reasoning_process: str = Field(description="인과관계 검증 논리")
    change_percent: str
    reason_cards: List[VolatilityCard]

class RadarCard(BaseModel):
    name: str
    ticker: str
    market: str
    reason: str
    key_point: str
    attention_level: str = Field(description="주목, 관심, 참고")
    source: str = Field(description="출처")

class RadarData(BaseModel):
    reasoning_process: str = Field(description="조건 부합 필터링 논리")
    candidates: List[RadarCard]

# ==========================================
# 2. UI 설정 및 세션(Session) 상태 초기화
# ==========================================
st.set_page_config(page_title="Alpha-Logic 분석기", layout="wide")
st.title("📈 Alpha-Logic 주식 분석기 (공유 및 저장 통합형)")

# 데이터를 유지하기 위한 세션 상태 초기화
tabs_names = ["종합리포트", "펀더멘털", "급등락", "레이더"]
for t in tabs_names:
    if f"{t}_data" not in st.session_state:
        st.session_state[f"{t}_data"] = None
    if f"{t}_target" not in st.session_state:
        st.session_state[f"{t}_target"] = ""

with st.sidebar:
    st.header("⚙️ 시스템 상태")
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        PROJECT_ID = st.secrets.get("FIREBASE_PROJECT_ID", "")
        st.success("✅ 2.5 Flash 엔진 정상 가동 중")
    except Exception as e:
        api_key = ""
        PROJECT_ID = ""
        st.error("⚠️ 클라우드 비밀 금고(Secrets) 설정이 필요합니다.")
    st.markdown("---")

# ==========================================
# 3. Firebase 통신 및 사이드바 공유 UI
# ==========================================
def save_to_firestore(ticker, tab_name, data):
    if not PROJECT_ID: return
    url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents/analysis_logs"
    payload = {
        "fields": {
            "ticker": {"stringValue": ticker},
            "tab": {"stringValue": tab_name},
            "json_data": {"stringValue": json.dumps(data, ensure_ascii=False)},
            "timestamp": {"stringValue": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
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
            # 최신순 정렬 후 최대 15개 반환
            history.sort(key=lambda x: x['timestamp'], reverse=True)
            return history[:15]
    except:
        return []
    return []

history_data = load_history_from_firestore()
if history_data:
    st.sidebar.markdown("### 🌐 최근 검색 종목 (전체 공유)")
    for idx, item in enumerate(history_data):
        # 화면에 표시될 버튼 이름 (예: [종합리포트] 삼성전자 (14:30))
        time_str = item['timestamp'][11:16] 
        btn_label = f"[{item['tab']}] {item['ticker']} ({time_str})"
        
        if st.sidebar.button(btn_label, key=f"hist_{idx}"):
            # 클릭 시 해당 탭의 세션 스토리지에 데이터 저장
            st.session_state[f"{item['tab']}_data"] = item['json_data']
            st.session_state[f"{item['tab']}_target"] = item['ticker']
            st.sidebar.success(f"데이터를 불러왔습니다. 우측 [{item['tab']}] 탭을 확인하세요.")

# ==========================================
# 4. 기능 엔진 (종목코드 변환, 실시간 주가, AI 파이프라인)
# ==========================================
def get_auto_ticker(company_name):
    if not api_key: return company_name
    try:
        client = genai.Client(api_key=api_key)
        sys_prompt = """
        사용자가 입력한 기업명의 Yahoo Finance 전용 Ticker(종목코드)만 정확히 1개 출력하라.
        - 한국 주식은 6자리 숫자만 출력하라.
        - 미국 주식은 영어 코드만 출력하라 (예: 애플 -> AAPL)
        - 어떠한 부연 설명 없이 코드만 대답하라.
        """
        res = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=company_name,
            config=types.GenerateContentConfig(system_instruction=sys_prompt, temperature=0.0)
        )
        raw_ticker = res.text.strip()
        match = re.search(r'[A-Za-z0-9]+', raw_ticker)
        if match: return match.group(0).upper()
        return raw_ticker.upper()
    except:
        return company_name

def fetch_realtime_data(ticker_symbol):
    try:
        ticker_symbol = ticker_symbol.strip()
        is_korean = False
        if ticker_symbol.isdigit() and len(ticker_symbol) == 6:
            ticker_symbol += ".KS"
            is_korean = True
            
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="5d")
        
        if hist.empty and is_korean:
            ticker_symbol = ticker_symbol.replace(".KS", ".KQ")
            stock = yf.Ticker(ticker_symbol)
            hist = stock.history(period="5d")
            
        if hist.empty: return "조회 실패", "조회 실패", "조회 실패", ticker_symbol

        current_price = float(hist['Close'].iloc[-1])
        prev_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_price
        
        if current_price < 2000 and not is_korean: price_str = f"{current_price:,.2f}"
        else: price_str = f"{current_price:,.0f}"
            
        if prev_close > 0:
            change_pct = ((current_price - prev_close) / prev_close) * 100
            change_str = f"{change_pct:+.2f}%"
        else: change_str = "0.00%"
            
        try:
            market_cap = stock.fast_info['marketCap']
            if market_cap > 1_000_000_000_000: cap_str = f"{market_cap / 1_000_000_000_000:,.1f}조"
            elif market_cap > 100_000_000: cap_str = f"{market_cap / 100_000_000:,.0f}억"
            else: cap_str = f"{market_cap:,.0f}"
        except: cap_str = "확인 불가"
            
        return price_str, change_str, cap_str, ticker_symbol
    except:
        return "에러", "에러", "에러", ticker_symbol

def ask_alpha_logic(query: str, system_prompt: str, schema_class):
    if not api_key: return None
    client = genai.Client(api_key=api_key)
    
    anti_hallucination_rules = """
    [초강력 통제 규칙: 환각 방지 지침]
    1. 프롬프트로 주입된 데이터는 절대 변형하지 말고 기입하라.
    2. 시작과 끝에 ```json 이나 ``` 기호를 절대 붙이지 말고 순수 JSON만 출력하라.
    """
    schema_json_string = json.dumps(schema_class.model_json_schema(), ensure_ascii=False)
    enhanced_system_prompt = f"{system_prompt}\n\n{anti_hallucination_rules}\n\n[중요] 반드시 다음 JSON 스키마를 완벽히 따르라:\n{schema_json_string}"
    
    model_candidates = ['gemini-2.5-flash', 'gemini-3.5-flash', 'gemini-2.0-flash']
    for model_name in model_candidates:
        try:
            response = client.models.generate_content(
                model=model_name, contents=query,
                config=types.GenerateContentConfig(system_instruction=enhanced_system_prompt, temperature=0.0)
            )
            raw_text = response.text.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(raw_text)
        except Exception as e:
            if "404" in str(e) or "429" in str(e) or "Quota" in str(e): continue 
            else: break
    st.error("분석 엔진 호출에 실패했습니다.")
    return None

# ==========================================
# 5. 메인 화면 구성 (렌더링 및 상태 분리)
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["📋 종합 리포트", "💎 펀더멘털 분석", "⚡ 급등락 원인", "📡 종목 레이더"])

# --- 탭 1 : 종합 리포트 ---
with tab1:
    st.subheader("📋 실시간 융합 리포트 분석")
    
    # 세션에 불러와진 타겟이 있으면 입력창에 반영
    company_1 = st.text_input("기업명 입력 (예: 삼성전자):", value=st.session_state["종합리포트_target"], key="c1_name")
    
    c_btn1, c_btn2 = st.columns(2)
    b1_run = c_btn1.button("▶️ 새로 분석 실행", key="b1")
    b1_update = c_btn2.button("🔄 불러온 데이터 갱신", key="u1")
    
    if (b1_run or b1_update) and company_1:
        with st.spinner(f"[{company_1}] 주가 수집 및 분석 중..."):
            smart_ticker = get_auto_ticker(company_1)
            live_price, live_change, live_cap, final_ticker = fetch_realtime_data(smart_ticker)
            
            sys_p = f"""너는 Alpha-Logic이다. 
            [시스템 수집 실시간 팩트] - 현재가: {live_price}, 변동률: {live_change}, 시가총액: {live_cap}
            위 데이터를 JSON에 기입하고, 정성적 분석은 사전 지식을 활용하라."""
            
            res = ask_alpha_logic(f"{company_1} 종합 분석", sys_p, ReportData)
            if res:
                # 분석 성공 시 상태 저장 및 DB 업로드
                st.session_state["종합리포트_data"] = res
                st.session_state["종합리포트_target"] = company_1
                save_to_firestore(company_1, "종합리포트", res)

    # 데이터 렌더링 블록 (분석 버튼을 안 눌러도 세션에 데이터가 있으면 항상 그려줌)
    res_t1 = st.session_state["종합리포트_data"]
    if res_t1:
        with st.expander("🤖 엔진의 논리 검증 과정 (Chain of Thought)"):
            st.write(res_t1.get('reasoning_process', '기록 없음'))

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("현재가/최근가", res_t1.get('current_price', 'N/A'))
        col2.metric("변동", res_t1.get('price_change_percent', 'N/A'))
        col3.metric("시가총액", res_t1.get('market_cap', 'N/A'))
        col4.metric("업종", res_t1.get('industry_type', 'N/A'))
        
        st.markdown(f"### 🎯 투자의견: **{res_t1.get('consensus_opinion', 'N/A')}** (목표가: {res_t1.get('target_price', 'N/A')})")
        st.info(f"**밸류에이션 요약**: {res_t1.get('valuation_summary', '')}")
        
        c_a, c_b = st.columns(2)
        with c_a:
            st.markdown("### 📰 검증된 주요 이슈")
            for issue in res_t1.get('recent_issues', []):
                st.write(f"- **[{issue.get('date', '')}]** {issue.get('content', '')} *(출처: {issue.get('source', '')})*")
        with c_b:
            st.markdown("### 🟢🟡🔴 팩트 시트")
            for fact in res_t1.get('fact_sheets', []):
                st.write(f"- **{fact.get('tone', '')}** | {fact.get('point', '')} *(출처: {fact.get('source', '')})*")

# --- 탭 2 : 펀더멘털 분석 ---
with tab2:
    st.subheader("💎 본질가치 및 해자 분석")
    company_2 = st.text_input("기업명 입력:", value=st.session_state["펀더멘털_target"], key="c2")
    
    c_btn1, c_btn2 = st.columns(2)
    b2_run = c_btn1.button("▶️ 새로 분석 실행", key="b2")
    b2_update = c_btn2.button("🔄 불러온 데이터 갱신", key="u2")
    
    if (b2_run or b2_update) and company_2:
        with st.spinner("지식 기반 지표 수집 및 구조화 중..."):
            sys_p = "너는 Alpha-Logic이다. 팩트를 기반으로 업종에 맞는 멀티플을 적용하여 분석하라."
            res = ask_alpha_logic(f"{company_2} 펀더멘털 정밀 분석", sys_p, FundamentalData)
            if res:
                st.session_state["펀더멘털_data"] = res
                st.session_state["펀더멘털_target"] = company_2
                save_to_firestore(company_2, "펀더멘털", res)

    res_t2 = st.session_state["펀더멘털_data"]
    if res_t2:
        with st.expander("🤖 엔진의 논리 검증 과정"):
            st.write(res_t2.get('reasoning_process', '기록 없음'))

        st.markdown(f"### 📊 종합 점수: **{res_t2.get('valuation_score', 0)}점** ({res_t2.get('valuation_grade', 'N/A')})")
        st.caption(f"산출 근거: {res_t2.get('valuation_basis', '')}")
        st.table(res_t2.get('details', []))
        
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.markdown("#### 💪 강점 (해자)")
            for pair in res_t2.get('moat_pairs', []):
                st.success(pair.get('strength', ''))
        with col_m2:
            st.markdown("#### 🐻 리스크 (반론)")
            for pair in res_t2.get('moat_pairs', []):
                st.error(pair.get('bear_case', ''))

# --- 탭 3 : 급등락 원인 ---
with tab3:
    st.subheader("⚡ 급등락 원인 추적")
    
    # 텍스트 입력창 (불러온 데이터가 '삼성전자(최근 1주)' 형태일 경우를 대비해 괄호 제거 로직 추가)
    c3_val = st.session_state["급등락_target"].split("(")[0] if "(" in st.session_state["급등락_target"] else st.session_state["급등락_target"]
    company_3 = st.text_input("종목명 입력:", value=c3_val, key="c3")
    period = st.selectbox("기간 선택", ["최근 1주", "최근 1개월", "최근 1년"])
    
    c_btn1, c_btn2 = st.columns(2)
    b3_run = c_btn1.button("▶️ 새로 분석 실행", key="b3")
    b3_update = c_btn2.button("🔄 불러온 데이터 갱신", key="u3")
    
    if (b3_run or b3_update) and company_3:
        with st.spinner("시장 데이터 교차 검증 중..."):
            sys_p = f"너는 Alpha-Logic이다. 사전 학습된 지식을 활용해 {period} 동안의 주가 변동 원인을 찾아라."
            res = ask_alpha_logic(f"{company_3} {period} 주가 변동 원인", sys_p, VolatilityData)
            if res:
                target_str = f"{company_3}({period})"
                st.session_state["급등락_data"] = res
                st.session_state["급등락_target"] = target_str
                save_to_firestore(target_str, "급등락", res)

    res_t3 = st.session_state["급등락_data"]
    if res_t3:
        with st.expander("🤖 엔진의 논리 검증 과정"):
            st.write(res_t3.get('reasoning_process', '기록 없음'))

        st.subheader(f"변동 요약: {res_t3.get('change_percent', 'N/A')}")
        for card in res_t3.get('reason_cards', []):
            with st.expander(f"🔥 [{card.get('impact_level', 0)}/5] {card.get('title', '')} ({card.get('category', '')})", expanded=True):
                st.write(card.get('description', ''))
                st.caption(f"출처: {card.get('source', '')}")

# --- 탭 4 : 종목 레이더 ---
with tab4:
    st.subheader("📡 종목 레이더 (조건부 스크리닝)")
    condition_val = st.session_state["레이더_target"] if st.session_state["레이더_target"] else "저PBR 리레이팅"
    condition = st.text_input("조건 입력 (예: 배당 성장주):", value=condition_val, key="c4")
    
    c_btn1, c_btn2 = st.columns(2)
    b4_run = c_btn1.button("▶️ 새로 레이더 가동", key="b4")
    b4_update = c_btn2.button("🔄 불러온 조건 갱신", key="u4")
    
    if (b4_run or b4_update) and condition:
        with st.spinner("지식 기반 스크리닝 진행 중..."):
            sys_p = "너는 Alpha-Logic이다. 제시된 조건에 정확히 부합하는 종목을 탐색하고 근거를 명시하라."
            res = ask_alpha_logic(f"조건 [{condition}] 종목 수집", sys_p, RadarData)
            if res:
                st.session_state["레이더_data"] = res
                st.session_state["레이더_target"] = condition
                save_to_firestore(condition, "레이더", res)

    res_t4 = st.session_state["레이더_data"]
    if res_t4:
        with st.expander("🤖 엔진의 논리 검증 과정"):
            st.write(res_t4.get('reasoning_process', '기록 없음'))

        for cand in res_t4.get('candidates', []):
            with st.container(border=True):
                st.markdown(f"### {cand.get('name', '')} ({cand.get('ticker', '')})")
                st.write(f"**근거**: {cand.get('reason', '')}")
                st.caption(f"출처: {cand.get('source', '')}")
