"""
Bitget 선물 퀀트 트레이딩 엔진 패키지 (v3.0)
- config: 환경설정 & 봇 파라미터
- exchange: 비트겟 CCXT 연동 및 실시간 모의/실거래 래퍼
- strategy: 4시간봉 거시추세 전략 (Donchian + 200 EMA) & 5분봉 스캘핑 전략
- risk_manager: 일일/월간 서킷 브레이커 & 리스크 관리 엔진
- data_collector: 과거 데이터 수집기
"""

from .config import BotConfig, config
from .strategy import MacroDonchianStrategy, MultiTimeframeStrategy, SignalType
from .exchange import BitgetExchange
from .risk_manager import RiskManager
from .notifier import notifier, TelegramNotifier

__all__ = [
    "BotConfig",
    "config",
    "MacroDonchianStrategy",
    "MultiTimeframeStrategy",
    "SignalType",
    "BitgetExchange",
    "RiskManager",
    "notifier",
    "TelegramNotifier",
]
