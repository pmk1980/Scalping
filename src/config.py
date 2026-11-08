import os
from dataclasses import dataclass
from dotenv import load_dotenv

# .env 파일 로드 (상위 폴더 및 현재 폴더 지원)
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

@dataclass
class BotConfig:
    """
    Bitget 선물 퀀트 봇 전역 설정 Dataclass
    """
    # 1. Bitget API 계정 인증 정보
    api_key: str = os.getenv("BITGET_API_KEY", "")
    api_secret: str = os.getenv("BITGET_API_SECRET", "")
    passphrase: str = os.getenv("BITGET_PASSPHRASE", "")

    # 2. 실행 모드 (True = 실시간 가상 페이퍼 트레이딩, False = 실계좌 실거래)
    dry_run: bool = os.getenv("DRY_RUN", "True").lower() in ("true", "1", "yes")

    # 3. 전략 선택 ("DONCHIAN_4H": 3년 검증 거시추세 전략(추천) | "SCALPING_5M": 5분봉 스캘핑)
    strategy_mode: str = os.getenv("STRATEGY_MODE", "DONCHIAN_4H")

    # 4. 거래 종목 및 타임프레임
    symbol: str = os.getenv("SYMBOL", "BTC/USDT:USDT") # 추천: BTC/USDT:USDT, SOL/USDT:USDT
    timeframe: str = os.getenv("TIMEFRAME", "4h")      # 기본 타임프레임: 4시간봉 (4h)
    htf_timeframe: str = "1d"                         # 상위 타임프레임: 일봉 (1d)

    # 5. 레버리지 및 마진 설정 (수학적 최적 스윗스팟: 2.0x, 청산 위험 0%)
    leverage: int = int(os.getenv("LEVERAGE", "2"))
    margin_mode: str = "isolated"                     # 격리 마진 (Isolated)
    portfolio_allocation: float = float(os.getenv("PORTFOLIO_ALLOCATION", "0.50")) # 1회 진입 비중 (50%)

    # 6. 주문 체결 방식
    use_post_only: bool = True                        # Maker(지정가 Post-Only) 우선 체결 (수수료 절감)

    # 7. 4시간봉 돈키언 추세 전략 파라미터 (3년 실데이터 검증 완료)
    donchian_period: int = 20                         # 20개봉(80시간) 채널 돌파
    macro_ema_period: int = 200                       # 200 EMA 거시 추세 필터 (하락장 현금 100% 관망)

    # 7-1. 가짜 돌파(Fakeout) 방지 및 본전 이익보존(Break-Even) 보완 파라미터
    use_break_even: bool = os.getenv("USE_BREAK_EVEN", "True").lower() in ("true", "1", "yes") # 본전 스탑 활성화
    break_even_trigger_ratio: float = float(os.getenv("BREAK_EVEN_TRIGGER_RATIO", "0.020"))    # +2.0% 수익 도달 시 본전(+0.2%) 이동
    use_volume_filter: bool = os.getenv("USE_VOLUME_FILTER", "True").lower() in ("true", "1", "yes") # 거래량 필터 활성화
    volume_filter_ratio: float = float(os.getenv("VOLUME_FILTER_RATIO", "0.80"))              # 20봉 평균 거래량의 80% 이상
    max_rsi_entry: float = float(os.getenv("MAX_RSI_ENTRY", "78.0"))                          # 과열 꼭대기 매수 차단 (RSI 상한)
    min_adx_entry: float = float(os.getenv("MIN_ADX_ENTRY", "18.0"))                          # 무추세 횡보장 휩소 차단 (ADX 하한)

    # 8. 자금 관리 & 다중 서킷 브레이커
    daily_max_loss_ratio: float = float(os.getenv("DAILY_MAX_LOSS_RATIO", "-0.05")) # 일일 -5% 서킷 브레이커
    monthly_max_loss_ratio: float = float(os.getenv("MONTHLY_MAX_LOSS_RATIO", "-0.15")) # 월간 -15% 서킷 브레이커
    max_daily_trades: int = int(os.getenv("MAX_DAILY_TRADES", "4"))                 # 하루 최대 진입 횟수
    max_consecutive_losses: int = 3                                                 # 3연속 손절 시 쿨다운
    cooldown_hours: int = 12                                                        # 쿨다운 대기 시간 (시간 단위)

    # 9. 거래 수수료율 (Bitget VIP0 기본: Maker 0.02%, Taker 0.06%)
    maker_fee_rate: float = 0.0002
    taker_fee_rate: float = 0.0006

    # 10. 기존 5분봉 스캘핑 하위 호환용 파라미터
    position_size_ratio: float = 0.10
    atr_sl_mult: float = 1.0
    atr_tp1_mult: float = 2.0
    atr_trailing_mult: float = 2.0
    bb_period: int = 20
    bb_std: float = 2.0
    rsi_period: int = 14
    atr_period: int = 14
    profit_lock_atr: float = 0.4

# 기본 싱글톤 인스턴스
config = BotConfig()
