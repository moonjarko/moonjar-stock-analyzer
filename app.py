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
# 1. Pydantic 구조 (단문 적용으로 SyntaxError 원천 차단)
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
# 2. UI 및 Firebase 통신 설정
# ==========================================
st.set_page_config(page_title="Alpha-Logic 분석기", layout="wide")
st.title("📈 Alpha-Logic 주식 분석기 (데이터 수집 강화형)")

with st.sidebar:
    st.header("⚙️ 시스템 상태")
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        PROJECT_ID = st.secrets.get("FIREBASE_PROJECT_ID", "")
        st.success("✅ 2.5 Flash + 자동 종목코드 및 2중 수집기 가동 중")
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

# ==========================================
# 3. AI 기반 자동 종목코드(Ticker) 변환기 (강력 정제)
# ==========================================
def get_auto_ticker(company_name):
    if not api_key: return company_name
    try:
        client = genai.Client(api_key=api_key)
        sys_prompt = """
        사용자가 입력한 기업명의 Yahoo Finance 전용 Ticker(종목코드)만 정확히 1개 출력하라.
        - 한국 코스피 주식은 뒤에 .KS를 붙인다 (예: 삼성전자 -> 005930.KS)
        - 한국 코스닥 주식은 뒤에 .KQ를 붙인다 (예: 에코프로 -> 086520.KQ)
        - 미국 주식은 그대로 출력한다 (예: 애플 -> AAPL)
        - 어떠한 부연 설명 없이 코드만 대답하라.
        """
        res = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=company_name,
            config=types.GenerateContentConfig(system_instruction=sys_prompt, temperature=0.0)
        )
        raw_ticker = res.text.strip()
        
        # [팩트 강화] AI가 헛소리를 섞었을 경우 대비, 정규식으로 영문/숫자/마침표만 강제 추출
        match = re.search(r'[A-Za-z0-9.]+', raw_ticker)
        if match:
            return match.group(0).upper()
        return raw_ticker.upper()
    except:
        return company_name

# ==========================================
# 4. 실시간 주가 수집 (yfinance API - 2중 안전장치)
# ==========================================
def fetch_realtime_data(ticker_symbol):
    try:
        # 안전망: 코드에 문자열이 섞여 들어왔을 수 있으니 공백 제거
        ticker_symbol = ticker_symbol.strip()
        
        stock = yf.Ticker(ticker_symbol)
        info = stock.info
        
        # 1차 시도: info(기본 메타데이터)에서 수집
        current_price = info.get('currentPrice', info.get('regularMarketPrice', None))
        prev_close = info.get('previousClose', None)
        market_cap = info.get('marketCap', None)
        
        # 2차 시도 (팩트 강화): 야후 서버가 info 접근을 막았을 경우 차트(history) 데이터에서 강제 추출
        if current_price is None:
            hist = stock.history(period="5d")
            if not hist.empty:
                current_price = float(hist['Close'].iloc[-1])
                if len(hist) > 1:
                    prev_close = float(hist['Close'].iloc[-2])
        
        if current_price is None:
            return "조회 실패(야후 응답없음)", "조회 실패", "조회 실패", ticker_symbol

        # 포맷팅 연산
        price_str = f"{current_price:,.0f}" if current_price else "데이터 없음"
        
        if current_price and prev_close:
            change_pct = ((current_price - prev_close) / prev_close) * 100
            change_str = f"{change_pct:+.2f}%"
        else:
            change_str = "데이터 없음"
            
        if market_cap:
            if market_cap > 1_000_000_000_000:
                cap_str = f"{market_cap / 1_000_000_000_000:,.1f}조"
            elif market_cap > 100_000_000:
                cap_str = f"{market_cap / 100_000_000:,.0f}억"
            else:
                cap_str = f"{market_cap:,}"
        else:
            cap_str = "데이터 없음"
            
        return price_str, change_str, cap_str, ticker_symbol
    except Exception as e:
        return f"조회 실패(에러)", "조회 실패", "조회 실패", ticker_symbol

# ==========================================
# 5. Alpha-Logic 엔진 (프롬프트 주입 방식)
# ==========================================
def ask_alpha_logic(query: str, system_prompt: str, schema_class):
    if not api_key:
        st.warning("API 키가 설정되지 않았습니다.")
        return None
        
    client = genai.Client(api_key=api_key)
    
    anti_hallucination_rules = """
    [초강력 통제 규칙: 환각 방지 지침]
    1. 프롬프트로 주입된 [실시간 데이터]는 절대 변형하지 말고 JSON에 그대로 기입하라.
    2. 마크다운 완전 금지: 시작과 끝에 ```json 이나 ``` 기호를 절대 붙이지 말고 오직 순수 JSON 중괄호 {} 만 출력하라.
    """
    
    schema_json_string = json.dumps(schema_class.model_json_schema(), ensure_ascii=False)
    enhanced_system_prompt = f"{system_prompt}\n\n{anti_hallucination_rules}\n\n[중요] 출력은 반드시 다음 JSON 스키마를 완벽히 따르는 순수 JSON 객체여야 한다:\n{schema_json_string}"
    
    model_candidates = ['gemini-2.5-flash', 'gemini-3.5-flash', 'gemini-2.0-flash']
    last_error = None
    
    for model_name in model_candidates:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=query,
                config=types.GenerateContentConfig(
                    system_instruction=enhanced_system_prompt,
                    temperature=0.0, 
                )
            )
            
            raw_text = response.text.strip()
            raw_text = raw_text.replace("```json", "")
            raw_text = raw_text.replace("```", "")
            raw_text = raw_text.strip()
            
            return json.loads(raw_text)
            
        except Exception as e:
            last_error = str(e)
            if "404" in last_error or "429" in last_error or "Quota" in last_error:
                continue 
            else:
                break
                
    st.error(f"모든 분석 엔진 호출에 실패했습니다.\n마지막 에러 로그: {last_error}")
    return None

# ==========================================
# 6. 메인 화면 구성
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["📋 종합 리포트", "💎 펀더멘털 분석", "⚡ 급등락 원인", "📡 종목 레이더"])

# --- 탭 1 ---
with tab1:
    st.subheader("📋 실시간 융합 리포트 분석")
    company_1 = st.text_input("기업명 입력 (예: 삼성전자, 애플, 테슬라):", key="c1_name")
    
    if st.button("분석 실행", key="b1") and company_1:
        with st.spinner(f"[{company_1}]의 정확한 종목코드를 탐색 중입니다..."):
            smart_ticker = get_auto_ticker(company_1)
            
        with st.spinner(f"주가 수집 및 정밀 분석 중... (매핑 코드: {smart_ticker})"):
            live_price, live_change, live_cap, final_ticker = fetch_realtime_data(smart_ticker)
            
            sys_p = f"""너는 Alpha-Logic이다. 
            [시스템이 수집한 실시간 절대 팩트]
            - 현재가: {live_price}
            - 변동률: {live_change}
            - 시가총액: {live_cap}
            
            위 실시간 데이터를 JSON의 current_price, price_change_percent, market_cap 항목에 반드시 그대로 입력하라. 나머지 정성적 분석은 너의 객관적 사전 지식을 활용하라."""
            
            res = ask_alpha_logic(f"{company_1} 종합 분석", sys_p, ReportData)
            if res:
                save_to_firestore(company_1, "종합리포트", res)
                
                with st.expander(f"🤖 자동 변환된 종목코드: {final_ticker}"):
                    st.write(res.get('reasoning_process', '기록 없음'))

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("현재가/최근가", res.get('current_price', live_price))
                col2.metric("변동", res.get('price_change_percent', live_change))
                col3.metric("시가총액", res.get('market_cap', live_cap))
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
        with st.spinner("지식 기반 지표 수집 및 논리 구조화 중..."):
            sys_p = "너는 Alpha-Logic이다. 사전 학습된 팩트를 기반으로 업종에 맞는 멀티플을 적용하여 해자와 리스크를 분석하라."
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
        with st.spinner("시장 데이터 교차 검증 중..."):
            sys_p = f"너는 Alpha-Logic이다. 사전 학습된 지식을 활용해 {period} 동안의 주요 주가 변동 원인을 찾아 분류하라."
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
        with st.spinner("지식 기반 스크리닝 진행 중..."):
            sys_p = "너는 Alpha-Logic이다. 사전 학습된 지식을 바탕으로 제시된 조건에 정확히 부합하는 종목을 탐색하고 반드시 그 근거를 명시하라."
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
