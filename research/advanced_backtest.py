
# 경로 호환성 보장
import os, sys
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
import sys
import os
import pandas as pd
import numpy as np

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def create_resampled_htf(df_5m: pd.DataFrame, timeframe: str = "15min") -> pd.DataFrame:
    """5분봉 데이터를 상위 타임프레임(15분봉 등)으로 합성(Resample)"""
    df = df_5m.copy()
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("datetime", inplace=True)
    
    htf = df.resample(timeframe).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "timestamp": "first"
    }).dropna()
    
    # 상위 타임프레임 지표 (200 EMA, 50 EMA, MACD)
    htf["htf_ema200"] = htf["close"].ewm(span=200, adjust=False).mean()
    htf["htf_ema50"] = htf["close"].ewm(span=50, adjust=False).mean()
    
    # MACD
    ema12 = htf["close"].ewm(span=12, adjust=False).mean()
    ema26 = htf["close"].ewm(span=26, adjust=False).mean()
    htf["htf_macd"] = ema12 - ema26
    htf["htf_macdsignal"] = htf["htf_macd"].ewm(span=9, adjust=False).mean()
    htf["htf_trend"] = np.where(
        (htf["close"] > htf["htf_ema200"]) & (htf["htf_macd"] > htf["htf_macdsignal"]), 1,
        np.where((htf["close"] < htf["htf_ema200"]) & (htf["htf_macd"] < htf["htf_macdsignal"]), -1, 0)
    )
    return htf

def run_advanced_backtest(
    csv_path: str = "data/BTC_USDT_USDT_5m_365d.csv",
    maker_fee_rate: float = 0.0002,      # 지정가 Maker 0.02%
    taker_fee_rate: float = 0.0006,      # 비상 손절 시 Taker 0.06%
    partial_tp_ratio: float = 0.5,       # 1차 목표가 달성 시 50% 분할 익절
    tp1_atr_mult: float = 1.5,           # 1차 익절: 진입가 + 1.5 ATR
    sl_atr_mult: float = 1.5,            # 기본 손절: 진입가 - 1.5 ATR
    trailing_atr_mult: float = 1.8,      # 2차 물량 추세 추종용 트레일링 스탑
    leverage: int = 10,
    pos_ratio: float = 0.10
):
    df_5m = pd.read_csv(csv_path)
    df_5m["datetime"] = pd.to_datetime(df_5m["timestamp"], unit="ms")
    df_5m.sort_values(by="timestamp", inplace=True)
    df_5m.reset_index(drop=True, inplace=True)

    # 1. 15분봉 상위 타임프레임 데이터 생성
    htf_15m = create_resampled_htf(df_5m, timeframe="15min")
    
    # 2. 5분봉에 15분봉 상위 추세 병합 (asof merge로 미래 데이터 참조 방지)
    df = pd.merge_asof(
        df_5m,
        htf_15m[["htf_trend", "htf_ema200"]].reset_index(),
        on="datetime",
        direction="backward"
    )

    # 3. 5분봉 지표 계산
    df["ema_fast"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=21, adjust=False).mean()
    
    # 볼린저 밴드
    df["bb_mid"] = df["close"].rolling(20).mean()
    df["bb_std"] = df["close"].rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + (df["bb_std"] * 2.0)
    df["bb_lower"] = df["bb_mid"] - (df["bb_std"] * 2.0)
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
    df["bb_width_ma"] = df["bb_width"].rolling(20).mean()

    # ATR
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()

    # RSI & 거래량 MA
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + (gain / (loss + 1e-10))))
    df["vol_ma"] = df["volume"].rolling(20).mean()

    initial_balance = 1000.0
    balance = initial_balance
    trades = []
    position = None

    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    volumes = df["volume"].values
    dts = df["datetime"].values

    htf_trend = df["htf_trend"].values
    ema_fast = df["ema_fast"].values
    ema_slow = df["ema_slow"].values
    bb_upper = df["bb_upper"].values
    bb_lower = df["bb_lower"].values
    bb_width = df["bb_width"].values
    bb_width_ma = df["bb_width_ma"].values
    vol_ma = df["vol_ma"].values
    rsi = df["rsi"].values
    atr = df["atr"].values

    start_idx = 250

    for i in range(start_idx, len(df)):
        c_open = opens[i]
        c_high = highs[i]
        c_low = lows[i]
        c_close = closes[i]
        c_dt = dts[i]

        # -------------------------------------------------------------------
        # [A] 보유 포지션 관리 (다단계 분할 익절 + 트레일링 스탑)
        # -------------------------------------------------------------------
        if position is not None:
            side = position["side"]
            entry_p = position["entry_price"]
            size = position["size"]
            sl = position["sl"]
            tp1 = position["tp1"]
            highest_p = max(position["highest_p"], c_high)
            lowest_p = min(position["lowest_p"], c_low)
            position["highest_p"] = highest_p
            position["lowest_p"] = lowest_p
            pos_atr = position["atr"]

            # 1. 1차 목표가(TP1) 도달 시 50% 분할 익절 및 본절 이동
            if not position["tp1_hit"]:
                if side == "BUY" and c_high >= tp1:
                    # 50% 분할 익절 실행 (지정가 체결)
                    exit_qty = size * partial_tp_ratio
                    gross = (tp1 - entry_p) * exit_qty
                    fee = (exit_qty * entry_p + exit_qty * tp1) * maker_fee_rate
                    net = gross - fee
                    balance += net
                    position["size"] -= exit_qty
                    position["tp1_hit"] = True
                    position["sl"] = entry_p + (entry_p * 0.0005) # 본절가(수수료 보전)로 스탑 상향!
                    sl = position["sl"]
                    trades.append({
                        "time": c_dt,
                        "side": side,
                        "reason": "PARTIAL_TP1 (50%)",
                        "pnl": net,
                        "fee": fee,
                        "balance": balance
                    })
                elif side == "SELL" and c_low <= tp1:
                    exit_qty = size * partial_tp_ratio
                    gross = (entry_p - tp1) * exit_qty
                    fee = (exit_qty * entry_p + exit_qty * tp1) * maker_fee_rate
                    net = gross - fee
                    balance += net
                    position["size"] -= exit_qty
                    position["tp1_hit"] = True
                    position["sl"] = entry_p - (entry_p * 0.0005)
                    sl = position["sl"]
                    trades.append({
                        "time": c_dt,
                        "side": side,
                        "reason": "PARTIAL_TP1 (50%)",
                        "pnl": net,
                        "fee": fee,
                        "balance": balance
                    })

            # 2. 1차 익절 완료 후 잔여 수량: 다이내믹 트레일링 스탑 작동!
            if position["tp1_hit"]:
                if side == "BUY":
                    # 최고점 대비 1.8 ATR 이탈 시 트레일링 스탑 청산
                    trail_sl = highest_p - (pos_atr * trailing_atr_mult)
                    if trail_sl > position["sl"]:
                        position["sl"] = trail_sl
                        sl = trail_sl
                else:
                    trail_sl = lowest_p + (pos_atr * trailing_atr_mult)
                    if trail_sl < position["sl"]:
                        position["sl"] = trail_sl
                        sl = trail_sl

            # 3. 손절 / 트레일링 스탑 이탈 검사
            closed = False
            exit_p = None
            reason = None

            if side == "BUY" and c_low <= sl:
                exit_p = sl
                reason = "TRAILING_STOP" if position["tp1_hit"] else "STOP_LOSS"
                closed = True
            elif side == "SELL" and c_high >= sl:
                exit_p = sl
                reason = "TRAILING_STOP" if position["tp1_hit"] else "STOP_LOSS"
                closed = True

            if closed:
                remain_size = position["size"]
                gross = (exit_p - entry_p) * remain_size if side == "BUY" else (entry_p - exit_p) * remain_size
                # 비상 손절이면 taker, 트레일링 스탑이면 maker/taker 절충
                fee = (remain_size * entry_p + remain_size * exit_p) * (maker_fee_rate if position["tp1_hit"] else taker_fee_rate)
                net = gross - fee
                balance += net
                trades.append({
                    "time": c_dt,
                    "side": side,
                    "reason": reason,
                    "pnl": net,
                    "fee": fee,
                    "balance": balance
                })
                position = None
                continue

        # -------------------------------------------------------------------
        # [B] 신규 진입 시그널 검사 (상위 15m 추세 + 5m 볼륨 스퀴즈 돌파)
        # -------------------------------------------------------------------
        if position is None:
            p_close = closes[i-1]
            p2_close = closes[i-2]
            p_atr = atr[i-1]
            p_htf = htf_trend[i-1]

            if np.isnan(p_atr) or p_atr <= 0 or np.isnan(p_htf):
                continue

            # 조건 1: 상위 15분봉 추세 필터 (1=강력한 상승장, -1=강력한 하락장)
            if p_htf == 0:
                continue

            # 조건 2: 5분봉 단기 EMA 정배열(롱) / 역배열(숏)
            fast_above_slow = ema_fast[i-1] > ema_slow[i-1]
            fast_below_slow = ema_fast[i-1] < ema_slow[i-1]

            # 조건 3: 거래량 유입 (평균의 1.3배 이상)
            vol_surge = volumes[i-1] > (vol_ma[i-1] * 1.3)

            # 조건 4: 볼린저 밴드 스퀴즈 후 돌파
            squeeze_condition = bb_width[i-2] <= bb_width_ma[i-2] * 1.1
            bb_break_up = (p_close > bb_upper[i-1]) and (p2_close <= bb_upper[i-2])
            bb_break_down = (p_close < bb_lower[i-1]) and (p2_close >= bb_lower[i-2])

            p_rsi = rsi[i-1]

            sig = None
            # 롱 진입 조건: 상위 15m 강력 상승(htf=1) + 5m EMA 정배열 + 거래량 폭증 + BB 상단 돌파 + RSI 50~72
            if (p_htf == 1) and fast_above_slow and vol_surge and squeeze_condition and bb_break_up and (50 < p_rsi < 72):
                sig = "BUY"
            # 숏 진입 조건: 상위 15m 강력 하락(htf=-1) + 5m EMA 역배열 + 거래량 폭증 + BB 하단 돌파 + RSI 28~50
            elif (p_htf == -1) and fast_below_slow and vol_surge and squeeze_condition and bb_break_down and (28 < p_rsi < 50):
                sig = "SELL"

            if sig:
                margin = balance * pos_ratio
                total_notional = margin * leverage
                size = total_notional / c_open

                if sig == "BUY":
                    sl = c_open - (p_atr * sl_atr_mult)
                    tp1 = c_open + (p_atr * tp1_atr_mult)
                else:
                    sl = c_open + (p_atr * sl_atr_mult)
                    tp1 = c_open - (p_atr * tp1_atr_mult)

                position = {
                    "side": sig,
                    "entry_price": c_open,
                    "size": size,
                    "sl": sl,
                    "tp1": tp1,
                    "atr": p_atr,
                    "tp1_hit": False,
                    "highest_p": c_open,
                    "lowest_p": c_open
                }

    if not trades:
        print("조건 만족 거래 없음")
        return

    tdf = pd.DataFrame(trades)
    tdf["time"] = pd.to_datetime(tdf["time"])
    tdf["month"] = tdf["time"].dt.to_period("M")

    n_trades = len(tdf)
    wins = tdf[tdf["pnl"] > 0]
    losses = tdf[tdf["pnl"] <= 0]
    wr = (len(wins) / n_trades) * 100

    tot_pnl = tdf["pnl"].sum()
    tot_fee = tdf["fee"].sum()
    profit_factor = (wins["pnl"].sum() / abs(losses["pnl"].sum())) if len(losses) > 0 else float("inf")

    tp1_count = len(tdf[tdf["reason"] == "PARTIAL_TP1 (50%)"])
    trail_count = len(tdf[tdf["reason"] == "TRAILING_STOP"])
    sl_count = len(tdf[tdf["reason"] == "STOP_LOSS"])

    print("\n" + "=" * 65)
    print("🏆 [고도화된 MTF + 트레일링 스탑 퀀트 백테스트 최종 성과]")
    print("=" * 65)
    print(f"• 테스트 기간       : {df.iloc[0]['datetime'].strftime('%Y-%m-%d')} ~ {df.iloc[-1]['datetime'].strftime('%Y-%m-%d')} (1년)")
    print(f"• 시작 자본금       : ${initial_balance:,.2f} USDT")
    print(f"• 최종 자본금       : ${balance:,.2f} USDT")
    print(f"• 총 순수익률 (ROI) : {((balance - initial_balance) / initial_balance) * 100:+.2f}%")
    print(f"• 총 이벤트 횟수    : {n_trades}회 (1차익절: {tp1_count}회 | 트레일링익절: {trail_count}회 | 손절: {sl_count}회)")
    print(f"• 승률 (Win Rate)   : {wr:.2f}%")
    print(f"• Profit Factor     : {profit_factor:.2f}")
    print(f"• 총 지불 수수료    : ${tot_fee:,.2f} USDT (지정가 Maker 최적화 적용)")
    print("=" * 65)

    print("\n📅 [월별 상세 손익 현황]")
    print(f"{'연월 (Month)':<12} | {'체결수':<8} | {'승률':<8} | {'월간 순손익(USDT)':<18}")
    print("-" * 55)
    for m, g in tdf.groupby("month"):
        w = len(g[g["pnl"] > 0])
        pnl = g["pnl"].sum()
        sign = "+" if pnl >= 0 else ""
        print(f"{str(m):<12} | {len(g):<8} | {(w/len(g)*100):5.1f}%  | {sign}${pnl:8.2f}")
    print("=" * 65)

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/BTC_USDT_USDT_5m_365d.csv"
    run_advanced_backtest(csv_path=path)
