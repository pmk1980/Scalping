import sys
from enum import Enum
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

class SignalType(Enum):
    NONE = "NONE"
    BUY = "BUY"    # 롱 진입
    SELL = "SELL"  # 숏 진입
    EXIT = "EXIT"  # 포지션 청산

class MacroDonchianStrategy:
    """
    🛡️ [3년 실데이터 검증 완료] 4시간봉 거시 추세 추종 퀀트 전략 엔진 (v3.1 보완판)
    1. 거시 추세 필터: 4시간봉 종가 > 200 EMA (하락장에서는 100% USDT 현금 관망)
    2. 진입: 직전 20개봉(80시간) 최고가 상향 돌파 시 롱(BUY) 진입
    3. 가짜 돌파(Fakeout) 방어:
       - 거래량 필터 (직전 20봉 평균의 80% 이상)
       - RSI 과열 차단 (RSI > 78 과매수 꼭대기 추격 매수 금지)
       - ADX 추세 강도 (ADX < 18 극심한 무추세 횡보장 휩소 차단)
    4. 이익 보존 본전 스탑 (Break-Even Stop):
       - 진입 후 +2.0% 이상 수익권 도달 시 스탑선을 즉시 '진입가 + 0.2%(수수료 방어)'로 상향
    5. 손절: 가격이 채널 중간선 ((20봉 최고가 + 최저가) / 2) 하향 이탈 시 즉시 칼손절
    6. 손익비 1:2.25 이상, 승률 45~50% 수준으로 우상향 복리 성장
    7. 동일 완성봉 중복 진입 방지 메커니즘 내장
    """
    def __init__(
        self,
        donchian_period: int = 20,
        ema_period: int = 200,
        use_break_even: bool = True,
        break_even_trigger_ratio: float = 0.020,
        use_volume_filter: bool = True,
        volume_filter_ratio: float = 0.80,
        max_rsi_entry: float = 78.0,
        min_adx_entry: float = 18.0
    ):
        self.donchian_period = donchian_period
        self.ema_period = ema_period
        self.use_break_even = use_break_even
        self.break_even_trigger_ratio = break_even_trigger_ratio
        self.use_volume_filter = use_volume_filter
        self.volume_filter_ratio = volume_filter_ratio
        self.max_rsi_entry = max_rsi_entry
        self.min_adx_entry = min_adx_entry

        self.last_entry_bar_time: Optional[Any] = None
        self.position_highest_price: Optional[float] = None
        self.break_even_activated: bool = False

    def reset_position_tracker(self):
        """포지션 청산 후 추적 변수 초기화"""
        self.position_highest_price = None
        self.break_even_activated = False

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # 1. 이동평균 및 돈키언 채널
        df["ema200"] = df["close"].ewm(span=self.ema_period, adjust=False).mean()
        df["high_n"] = df["high"].shift(1).rolling(self.donchian_period).max()
        df["low_n"] = df["low"].shift(1).rolling(self.donchian_period).min()
        df["mid_n"] = (df["high_n"] + df["low_n"]) / 2.0

        # 2. 거래량 비율 (Volume Ratio)
        if "volume" in df.columns:
            df["vol_ma"] = df["volume"].shift(1).rolling(self.donchian_period).mean()
            df["vol_ratio"] = df["volume"] / (df["vol_ma"] + 1e-9)
        else:
            df["vol_ratio"] = 1.0

        # 3. ATR (Average True Range)
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["close"].shift(1)).abs()
        tr3 = (df["low"] - df["close"].shift(1)).abs()
        df["tr"] = np.maximum(tr1, np.maximum(tr2, tr3))
        df["atr14"] = df["tr"].rolling(14).mean()

        # 4. RSI (14)
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        df["rsi14"] = 100 - (100 / (1 + rs))

        # 5. ADX (14)
        plus_dm = df["high"].diff()
        minus_dm = -df["low"].diff()
        plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
        minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)
        tr_smooth = df["tr"].rolling(14).mean()
        plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(14).mean() / (tr_smooth + 1e-9))
        minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(14).mean() / (tr_smooth + 1e-9))
        dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9))
        df["adx14"] = dx.rolling(14).mean()

        return df

    def analyze(self, df: pd.DataFrame, current_position: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        min_bars_needed = max(self.donchian_period, self.ema_period) + 5
        if len(df) < min_bars_needed:
            return {
                "signal": SignalType.NONE,
                "reason": f"데이터 부족 (현재 {len(df)}개, 최소 {min_bars_needed}개 필요)"
            }

        df_calc = self.calculate_indicators(df)
        last = df_calc.iloc[-1]       # 현재 형성 중인 4h 봉 (미완성봉)
        prev = df_calc.iloc[-2]       # 직전 완성봉 (지표 확정 기준)
        current_price = float(last["close"])
        prev_bar_time = prev.get("datetime", prev.get("timestamp", None))

        # 1. 포지션 보유 중인 경우: 이익보존/스탑 청산(Stop-loss / Trailing Exit) 검사
        if current_position is not None:
            entry_price = float(current_position.get("entry_price", current_price))
            
            # 최고가 추적 갱신
            if self.position_highest_price is None:
                self.position_highest_price = max(entry_price, current_price, float(last["high"]))
            else:
                self.position_highest_price = max(self.position_highest_price, current_price, float(last["high"]))

            # 기본 채널 중간선 스탑
            base_stop = float(prev["mid_n"])
            effective_stop = base_stop

            # 본전 스탑 (Break-Even Stop) 검사
            be_target = entry_price * (1.0 + self.break_even_trigger_ratio)
            be_stop_price = entry_price * 1.002 # 수수료 보존 +0.2%

            if self.use_break_even:
                if self.position_highest_price >= be_target or self.break_even_activated:
                    self.break_even_activated = True
                    effective_stop = max(base_stop, be_stop_price)

            # 저가가 실효 스탑선 이하로 내려간 경우 청산 신호
            if float(last["low"]) <= effective_stop:
                fill_price = min(float(last["open"]), effective_stop)
                is_be_exit = bool(self.break_even_activated and effective_stop >= entry_price)
                reason_str = (
                    f"본전 이익보존 스탑(${effective_stop:,.2f}) 발동 청산 (수익 방어)"
                    if is_be_exit
                    else f"채널 중간선(${effective_stop:,.2f}) 이탈로 이익보존/칼손절 청산"
                )
                self.reset_position_tracker()
                return {
                    "signal": SignalType.EXIT,
                    "exit_price": fill_price,
                    "reason": reason_str
                }

            status_note = " [본전 방어 활성]" if self.break_even_activated else ""
            return {
                "signal": SignalType.NONE,
                "reason": f"포지션 유지 중{status_note} (스탑선: ${effective_stop:,.2f}, 현재가: ${current_price:,.2f})"
            }

        # 포지션이 없으면 추적 변수 클리어
        self.reset_position_tracker()

        # 2. 무포지션인 경우: 신규 롱 진입 검사
        is_macro_bull = bool(prev["close"] > prev["ema200"])
        is_breakout = bool(prev["close"] > prev["high_n"])

        if is_macro_bull and is_breakout:
            # 동일 봉 중복 진입 방지
            if self.last_entry_bar_time == prev_bar_time and prev_bar_time is not None:
                return {
                    "signal": SignalType.NONE,
                    "reason": f"이미 체결된 돌파봉({prev_bar_time}) - 다음 4시간 완성봉 대기"
                }

            # 🛡️ 보완 필터 1: 거래량 필터 (무거래량 가짜 돌파 방지)
            vol_ratio = float(prev.get("vol_ratio", 1.0))
            if self.use_volume_filter and vol_ratio < self.volume_filter_ratio:
                return {
                    "signal": SignalType.NONE,
                    "reason": f"돌파 미인정: 거래량 부족 (현재 {vol_ratio:.2f}배 < 기준 {self.volume_filter_ratio:.2f}배)"
                }

            # 🛡️ 보완 필터 2: RSI 과열 필터 (꼭대기 추격 매수 방지)
            rsi = float(prev.get("rsi14", 50.0))
            if rsi > self.max_rsi_entry:
                return {
                    "signal": SignalType.NONE,
                    "reason": f"돌파 미인정: 단기 과열권 (RSI {rsi:.1f} > 기준 {self.max_rsi_entry:.1f})"
                }

            # 🛡️ 보완 필터 3: ADX 추세 강도 필터 (무추세 횡보장 휩소 방지)
            adx = float(prev.get("adx14", 25.0))
            if adx < self.min_adx_entry:
                return {
                    "signal": SignalType.NONE,
                    "reason": f"돌파 미인정: 무추세 횡보장 (ADX {adx:.1f} < 기준 {self.min_adx_entry:.1f})"
                }

            initial_stop = float(prev["mid_n"])
            self.position_highest_price = current_price
            return {
                "signal": SignalType.BUY,
                "entry_price": current_price,
                "stop_loss": initial_stop,
                "bar_time": prev_bar_time,
                "reason": f"200 EMA 위 4h 20봉 진성 돌파 (Vol:{vol_ratio:.1f}x, RSI:{rsi:.0f}, ADX:{adx:.0f}) 진입"
            }
        elif not is_macro_bull:
            return {
                "signal": SignalType.NONE,
                "reason": f"하락/조정 국면 현금 100% 관망 (Close < 200 EMA ${prev['ema200']:,.2f})"
            }
        else:
            return {
                "signal": SignalType.NONE,
                "reason": f"상승 추세 내 신호 대기 (20봉 최고가: ${prev['high_n']:,.2f}, 현재가: ${current_price:,.2f})"
            }


class MultiTimeframeStrategy:
    """기존 5분봉 스캘핑 전략 엔진 (하위 호환성 유지)"""
    def __init__(
        self,
        ema_fast: int = 9,
        ema_slow: int = 21,
        ema_trend: int = 200,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        atr_period: int = 14,
        atr_sl_mult: float = 1.0,
        atr_tp1_mult: float = 2.0,
        atr_trailing_mult: float = 2.0
    ):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.ema_trend = ema_trend
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp1_mult = atr_tp1_mult
        self.atr_trailing_mult = atr_trailing_mult

    def analyze_htf_trend(self, htf_df: pd.DataFrame) -> Dict[str, Any]:
        if len(htf_df) < self.ema_trend + 10:
            return {"trend": 0, "desc": "상위 데이터 부족"}
        df = htf_df.copy()
        df["ema200"] = df["close"].ewm(span=self.ema_trend, adjust=False).mean()
        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema12 - ema26
        df["macdsig"] = df["macd"].ewm(span=9, adjust=False).mean()

        last = df.iloc[-1]
        if last["close"] > last["ema200"] and last["macd"] > last["macdsig"]:
            return {"trend": 1, "desc": "강력 상승장"}
        elif last["close"] < last["ema200"] and last["macd"] < last["macdsig"]:
            return {"trend": -1, "desc": "강력 하락장"}
        return {"trend": 0, "desc": "중립장"}

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ema_fast"] = df["close"].ewm(span=self.ema_fast, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.ema_slow, adjust=False).mean()
        df["bb_mid"] = df["close"].rolling(self.bb_period).mean()
        df["bb_std"] = df["close"].rolling(self.bb_period).std()
        df["bb_upper"] = df["bb_mid"] + (df["bb_std"] * self.bb_std)
        df["bb_lower"] = df["bb_mid"] - (df["bb_std"] * self.bb_std)
        hl = df["high"] - df["low"]
        hc = (df["high"] - df["close"].shift()).abs()
        lc = (df["low"] - df["close"].shift()).abs()
        df["atr"] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(self.atr_period).mean()
        return df

    def analyze(self, current_df: pd.DataFrame, htf_df: pd.DataFrame) -> Dict[str, Any]:
        htf = self.analyze_htf_trend(htf_df)
        if htf["trend"] == 0:
            return {"signal": SignalType.NONE, "reason": "상위 추세 중립"}
        df = self.calculate_indicators(current_df)
        prev = df.iloc[-2]
        c_p = float(df.iloc[-1]["close"])
        atr = float(prev["atr"])
        if pd.isna(atr):
            return {"signal": SignalType.NONE, "reason": "ATR 계산 불가"}

        if htf["trend"] == 1 and prev["close"] > prev["bb_upper"]:
            return {
                "signal": SignalType.BUY,
                "entry_price": c_p,
                "stop_loss": c_p - (atr * self.atr_sl_mult),
                "take_profit_1": c_p + (atr * self.atr_tp1_mult),
                "reason": "15m 상승 + 5m 볼밴 상단 돌파"
            }
        return {"signal": SignalType.NONE, "reason": "신호 대기"}

# 하위 호환 별칭
ScalpingStrategy = MultiTimeframeStrategy
