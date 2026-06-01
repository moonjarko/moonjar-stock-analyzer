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
from bs4 import BeautifulSoup

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
    multiple_basis: str = Field(description="AI가 판단한 적합한 멀티플 기준 (예: PER, PBR, EV/EBITDA 등)")
    current_multiple: str = Field(description="현재 기준 멀티플 (예: 15.2x)")
    forward_multiple: str = Field(description="포워드(12M Fwd) 멀티플 (예: 12.5x)")
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
st.title("📈 Alpha-Logic 주식 분석기 (오류 추적 강화형)")

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
        st.success("✅ 듀얼 데이터 엔진 (Naver/Yahoo) 가동 중")
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
            history.sort(key=lambda x: x['timestamp'], reverse=True)
            return history
    except:
        return []
    return []

all_history = load_history_from_firestore()

stock_history = []
radar_history = []
seen_stocks = set()
seen_radars = set()

for item in all_history:
    if item['tab'] == '레이더':
        if item['ticker'] not in seen_radars:
            seen_radars.add(item['ticker'])
            radar_history.append(item)
    else:
        raw_ticker = item['ticker'].split("(")[0].strip()
        if raw_ticker not in seen_stocks:
            seen_stocks.add(raw_ticker)
            stock_history.append(raw_ticker)

if stock_history:
    st.sidebar.markdown("### 🏢 최근 검색 종목 (전체 공유)")
    for stock in stock_history[:12]:
        if st.sidebar.button(f"📊 {stock}", key=f"btn_stock_{stock}"):
            for t in ["종합리포트", "펀더멘털", "급등락"]:
                st.session_state[f"{t}_data"] = None
                st.session_state[f"{t}_target"] = stock
            
            loaded_tabs = set()
            for item in all_history:
                raw_item_ticker = item['ticker'].split("(")[0].strip()
                if raw_item_ticker == stock and item['tab'] not in loaded_tabs and item['tab'] != '레이더':
                    st.session_state[f"{item['tab']}_data"] = item['json_data']
                    if item['tab'] == '급등락':
                        st.session_state["급등락_target"] = item['ticker']
                    loaded_tabs.add(item['tab'])
            st.sidebar.success(f"[{stock}] 데이터를 통합 로드했습니다.")

if radar_history:
    st.sidebar.markdown("### 📡 최근 레이더 조건")
    for item in radar_history[:5]:
        if st.sidebar.button(f"🔍 {item['ticker']}", key=f"btn_radar_{item['ticker']}"):
            st.session_state["레이더_data"] = item['json_data']
            st.session_state["레이더_target"] = item['ticker']
            st.sidebar.success(f"[{item['ticker']}] 레이더를 불러왔습니다.")

# ==========================================
# 3. AI 기반 자동 종목코드(Ticker) 변환기
# ==========================================
def get_auto_ticker(company_name):
    if not api_key: return company_name
    try:
        client = genai.Client(api_key=api_key)
        sys_prompt = """
        사용자가 입력한 기업명의 주식 식별 코드를 정확히 1개 출력하라.
        - 한국 주식은 오직 '6자리 숫자'만 출력하라. (.KS나 .KQ 절대 붙이지 말 것)
        - 미국 주식은 '영어 티커'만 출력하라 (예: 애플 -> AAPL)
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

# ==========================================
# 4. 듀얼 파이프라인 (네이버 스크래핑 vs 야후 파이낸스)
# ==========================================
def get_naver_finance(ticker):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        dts = soup.select('dl.blind dt')
        dds = soup.select('dl.blind dd')
        info_dict = {dt.text.strip(): dd.text.strip() for dt, dd in zip(dts, dds)}
        
        price_str = info_dict.get('현재가', '데이터 없음')
        change_val = info_dict.get('등락률', '데이터 없음')
        change_str = f"{change_val}%" if change_val != '데이터 없음' else "데이터 없음"
        if change_str != "데이터 없음" and not change_str.startswith("-") and change_str != "0.00%":
            change_str = f"+{change_str}"

        cap_str = "데이터 없음"
        cap_elem = soup.select_one('#_market_sum')
        if cap_elem:
            cap_val = cap_elem.text.replace(',', '').strip()
            cap_num = int(cap_val)
            if cap_num >= 10000:
                cap_str = f"{cap_num // 10000}조 {cap_num % 10000}억"
            else:
                cap_str = f"{cap_num}억"
                
        return price_str, change_str, cap_str, ticker
    except:
        return "조회 실패", "조회 실패", "조회 실패", ticker

def get_yahoo_finance(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d")
        if hist.empty: return "조회 실패", "조회 실패", "조회 실패", ticker

        current_price = float(hist['Close'].iloc[-1])
        prev_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_price
        
        price_str = f"{current_price:,.2f}"
            
        if prev_close > 0:
            change_pct = ((current_price - prev_close) / prev_close) * 100
            change_str = f"{change_pct:+.2f}%"
        else: change_str = "0.00%"
            
        try:
            market_cap = stock.fast_info['marketCap']
            if market_cap > 1_000_000_000_000: cap_str = f"${market_cap / 1_000_000_000_000:,.2f}T"
            elif market_cap > 1_000_000_000: cap_str = f"${market_cap / 1_000_000_000:,.2f}B"
            else: cap_str = f"${market_cap:,.0f}"
        except: cap_str = "확인 불가"
            
        return price_str, change_str, cap_str, ticker
    except:
        return "조회 실패", "조회 실패", "조회 실패", ticker

def fetch_realtime_data(ticker_symbol):
    ticker_symbol = ticker_symbol.strip()
    if ticker_symbol.isdigit() and len(ticker_symbol) == 6:
        return get_naver_finance(ticker_symbol)
    else:
        return get_yahoo_finance(ticker_symbol)

# ==========================================
# 5. Alpha-Logic 엔진 (오류 추적 강화)
# ==========================================
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
    last_error_message = "알 수 없는 에러"
    
    for model_name in model_candidates:
        try:
            response = client.models.generate_content(
                model=model_name, contents=query,
                config=types.GenerateContentConfig(system_instruction=enhanced_system_prompt, temperature=0.0)
            )
            raw_text = response.text.strip().replace("```json", "").replace("```", "").strip()
            
            # JSON 디코딩 시도
            return json.loads(raw_text)
            
        except json.JSONDecodeError as je:
            last_error_message = f"[{model_name}] JSON 구조화 실패: {str(je)} | 반환값 일부: {raw_text[:50]}..."
            continue # 파싱 실패 시 다음 모델로 재시도
        except Exception as e:
            last_error_message = f"[{model_name}] API 통신 에러: {str(e)}"
            continue # API 에러 발생 시 다음 모델로 재시도
            
    # 모든 모델이 실패했을 경우, 화면에 정확한 원인을 노출합니다.
    st.error(f"분석 엔진 호출 실패. 상세 사유:\n{last_error_message}")
    return None

# ==========================================
# 6. 메인 화면 구성
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["📋 종합 리포트", "💎 펀더멘털 분석", "⚡ 급등락 원인", "📡 종목 레이더"])

# --- 탭 1 : 종합 리포트 ---
with tab1:
    st.subheader("📋 실시간 융합 리포트 분석")
    
    company_1 = st.text_input("기업명 입력 (예: 삼성전자, 애플):", value=st.session_state["종합리포트_target"], key="c1_name")
    
    c_btn1, c_btn2 = st.columns(2)
    b1_run = c_btn1.button("▶️ 새로 분석 실행", key="b1")
    b1_update = c_btn2.button("🔄 불러온 데이터 갱신", key="u1")
    
    if (b1_run or b1_update) and company_1:
        with st.spinner(f"[{company_1}] 코드 확인 및 주가 스크래핑 중..."):
            smart_ticker = get_auto_ticker(company_1)
            live_price, live_change, live_cap, final_ticker = fetch_realtime_data(smart_ticker)
            
        with st.spinner("AI 엔진 밸류에이션 및 정밀 분석 중..."):
            sys_p = f"""너는 Alpha-Logic이다. 
            [시스템 수집 실시간 팩트] - 현재가: {live_price}, 변동률: {live_change}, 시가총액: {live_cap}
            
            [추가 지시사항]
            1. 해당 기업의 업종과 비즈니스 모델을 분석하여 가장 적합한 밸류에이션 멀티플 기준(예: PER, PBR, EV/EBITDA, PSR 등)을 판별해 'multiple_basis'에 설정하라.
            2. 너의 객관적 사전 지식을 활용하여 해당 기업의 '현재 멀티플', '포워드 멀티플', '애널리스트 평균 목표가'를 추정하여 기입하라. (정확한 수치를 모를 경우 합리적인 추정치나 밴드를 기입)
            3. 위 실시간 수집 팩트는 지정된 항목에 그대로 기입하고 나머지 정성적 분석을 완성하라.
            """
            
            res = ask_alpha_logic(f"{company_1} 종합 분석", sys_p, ReportData)
            if res:
                st.session_state["종합리포트_data"] = res
                st.session_state["종합리포트_target"] = company_1
                save_to_firestore(company_1, "종합리포트", res)

    res_t1 = st.session_state["종합리포트_data"]
    if res_t1:
        with st.expander("🤖 엔진의 논리 검증 과정"):
            st.write(res_t1.get('reasoning_process', '기록 없음'))

        # 1행: 수집된 가격 정보
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("현재가/최근가", res_t1.get('current_price', 'N/A'))
        col2.metric("변동", res_t1.get('price_change_percent', 'N/A'))
        col3.metric("시가총액", res_t1.get('market_cap', 'N/A'))
        col4.metric("업종", res_t1.get('industry_type', 'N/A'))
        
        # 2행: AI 판단 멀티플 및 목표가
        st.markdown("### 📊 밸류에이션 지표 및 투자의견")
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("적용 멀티플", res_t1.get('multiple_basis', 'N/A'))
        m_col2.metric("현재 멀티플", res_t1.get('current_multiple', 'N/A'))
        m_col3.metric("포워드 멀티플", res_t1.get('forward_multiple', 'N/A'))
        m_col4.metric("목표가 (컨센서스)", res_t1.get('target_price', 'N/A'))
        
        st.markdown(f"**💡 투자의견:** {res_t1.get('consensus_opinion', 'N/A')} | **밸류에이션 요약:** {res_t1.get('valuation_summary', '')}")
        st.divider()
        
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
    
    c3_val = st.session_state["급등락_target"].split("(")[0].strip() if "(" in st.session_state["급등락_target"] else st.session_state["급등락_target"]
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
