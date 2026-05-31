import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Optional
import json
import requests
from datetime import datetime

# ==========================================
# 1. Pydantic 구조 (엄격한 JSON 스키마)
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
    reasoning_process: str = Field(description="사전 학습된 데이터를 바탕으로 한 논리적 추론 과정 (가장 먼저 작성할 것)")
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
    reasoning_process: str = Field(description="사전 학습된 데이터를 바탕으로 한 논리적 추론 과정 (가장 먼저 작성할 것)")
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
    reasoning_process: str = Field(description="주가 변동의 인과관계를 검증한
