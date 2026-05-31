import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Optional
import json
import requests
from datetime import datetime

# 데이터베이스 설정을 위한 변수 (사이드바에서 입력 가능하도록 폴백 구현)
PROJECT_ID = st.sidebar.text_input("Firebase Project ID (선택)", value="")

# --- Pydantic 데이터 구조 정의 생략 (이전 마스터 코드와 동일한 구조 사용) ---
# (스키마 생략: ReportData, FundamentalData, VolatilityData, RadarData)

st.set_page_config(page_title="Alpha-Logic 분석기", layout="wide")
st.title("📈 Alpha-Logic 주식 분석기 (v2.0 Gemini+Firestore)")

with st.sidebar:
    st.header("⚙️ 시스템 설정")
    api_key = st.text_input("Google AI Studio API Key", type="password")
    st.markdown("---")

# --- Firebase 데이터베이스 저장/불러오기 REST API 구현 ---
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
    return []

# --- 분석 기록 불러오기 UI 영역 ---
history_data = load_history_from_firestore()
if history_data:
    with st.sidebar.expander("📚 가족 최근 분석 기록 (최신순)"):
        for item in reversed(history_data[-15:]): # 최근 15개 노출
            if st.button(f"[{item['tab']}] {item['ticker']} ({item['timestamp']})"):
                st.session_state[f"cached_{item['tab']}_{item['ticker']}"] = item['json_data']
                st.success(f"{item['ticker']} 캐시 데이터를 성공적으로 불러왔습니다. 해당 탭을 확인하세요.")

# --- 메인 탭 로직 (Gemini 호출 후 성공 시 save_to_firestore 실행) ---
# 예시: 탭 1에서 결과 도출 성공 직후 아래 한 줄 추가
# save_to_firestore(company_1, "종합리포트", res)