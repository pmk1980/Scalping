import os
import sys
import pandas as pd
import numpy as np

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def calculate_advanced_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # EMA
    df["ema_fast"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema_trend"] = df["close"].ewm(span=200, adjust=False).mean()

    # Bollinger Bands
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

    # ADX (Average Directional Index) - 추세 강도 측정 (횡보장 필터링)
    plus_dm = df["high"].diff()
    minus_dm = -df["low"].diff()
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)

    tr_smooth = pd.Series(tr).rolling(14).mean()
    plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / (tr_smooth + 1e-10))
    minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / (tr_smooth + 1e-10))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    df["adx"] = dx.rolling(14).mean()

    # RSI
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))

    # Volume MA
    df["vol_ma"] = df["volume"].rolling(20).mean()

    return df

def run_optimized_backtest(
    csv_path: str = "data/BTC_USDT_USDT_5m_365d.csv",
    use_maker_fee: bool = True,       # 지정가(Maker) 체결 가정 (수수료 절감)
    use_breakeven_stop: bool = True,   # 1:1 도달 시 본절 스탑 이동
    adx_threshold: float = 22.0,       # ADX 추세 필터 (22 이상 강한 추세장만 진입)
    atr_sl_mult: float = 1.8,          # 휩쏘 방지를 위한 넉넉한 손절 배수
    atr_tp_mult: float = 3.0           # 손익비 1:1.67 유지
):
    df = pd.read_csv(csv_path)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = calculate_advanced_indicators(df)

    initial_balance = 1000.0
    balance = initial_balance
    leverage = 10
    pos_ratio = 0.10
    # 비트겟 선물 수수료: Maker 0.02%, Taker 0.06%
    fee_rate = 0.0002 if use_maker_fee else 0.0006

    trades = []
    position = None

    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    volumes = df["volume"].values
    dts = df["datetime"].values

    ema_trend = df["ema_trend"].values
    ema_fast = df["ema_fast"].values
    ema_slow = df["ema_slow"].values
    bb_upper = df["bb_upper"].values
    bb_lower = df["bb_lower"].values
    bb_width = df["bb_width"].values
    bb_width_ma = df["bb_width_ma"].values
    adx = df["adx"].values
    vol_ma = df["vol_ma"].values
    rsi = df["rsi"].values
    atr = df["atr"].values

    start_idx = 210

    for i in range(start_idx, len(df)):
        c_open = opens[i]
        c_high = highs[i]
        c_low = lows[i]
        c_dt = dts[i]

        if position is not None:
            side = position["side"]
            entry_p = position["entry_price"]
            size = position["size"]
            sl = position["sl"]
            tp = position["tp"]

            # 본절(Breakeven) 스탑 로직
            if use_breakeven_stop and not position["is_breakeven"]:
                if side == "BUY" and c_high >= entry_p + (position["init_atr"] * 1.0):
                    position["sl"] = entry_p + (entry_p * 0.0005) # 본절 + 최소 수수료 보전
                    position["is_breakeven"] = True
                    sl = position["sl"]
                elif side == "SELL" and c_low <= entry_p - (position["init_atr"] * 1.0):
                    position["sl"] = entry_p - (entry_p * 0.0005)
                    position["is_breakeven"] = True
                    sl = position["sl"]

            closed = False
            exit_p = None
            reason = None

            if side == "BUY":
                if c_low <= sl:
                    exit_p = sl
                    reason = "BREAKEVEN" if position["is_breakeven"] else "STOP_LOSS"
                    closed = True
                elif c_high >= tp:
                    exit_p = tp
                    reason = "TAKE_PROFIT"
                    closed = True
            else:
                if c_high >= sl:
                    exit_p = sl
                    reason = "BREAKEVEN" if position["is_breakeven"] else "STOP_LOSS"
                    closed = True
                elif c_low <= tp:
                    exit_p = tp
                    reason = "TAKE_PROFIT"
                    closed = True

            if closed:
                gross = (exit_p - entry_p) * size if side == "BUY" else (entry_p - exit_p) * size
                fee = (size * entry_p + size * exit_p) * fee_rate
                net_pnl = gross - fee
                balance += net_pnl
                trades.append({
                    "time": c_dt,
                    "side": side,
                    "reason": reason,
                    "pnl": net_pnl,
                    "fee": fee,
                    "balance": balance
                })
                position = None
                continue

        # 신규 진입
        if position is None:
            p_close = closes[i-1]
            p2_close = closes[i-2]
            p_atr = atr[i-1]
            p_adx = adx[i-1]

            if np.isnan(p_atr) or p_atr <= 0 or np.isnan(p_adx):
                continue

            # 1. 강력한 추세 필터 (ADX > 임계값)
            if p_adx < adx_threshold:
                continue

            # 2. 이동평균 정배열 / 역배열
            bull_align = (ema_fast[i-1] > ema_slow[i-1]) and (p_close > ema_trend[i-1])
            bear_align = (ema_fast[i-1] < ema_slow[i-1]) and (p_close < ema_trend[i-1])

            # 3. 거래량 폭증 (평균의 1.4배)
            vol_ok = volumes[i-1] > (vol_ma[i-1] * 1.4)

            # 4. 볼린저 밴드 스퀴즈 후 확장 돌파
            # 밴드폭이 최근 평균 밴드폭 이하로 수축되어 있던 상태에서의 돌파
            squeeze_ready = bb_width[i-2] <= bb_width_ma[i-2] * 1.05
            bb_break_up = (p_close > bb_upper[i-1]) and (p2_close <= bb_upper[i-2])
            bb_break_down = (p_close < bb_lower[i-1]) and (p2_close >= bb_lower[i-2])

            p_rsi = rsi[i-1]

            sig = None
            if bull_align and bb_break_up and vol_ok and squeeze_ready and (50 < p_rsi < 75):
                sig = "BUY"
            elif bear_align and bb_break_down and vol_ok and squeeze_ready and (25 < p_rsi < 50):
                sig = "SELL"

            if sig:
                margin = balance * pos_ratio
                size = (margin * leverage) / c_open
                sl = c_open - (p_atr * atr_sl_mult) if sig == "BUY" else c_open + (p_atr * atr_sl_mult)
                tp = c_open + (p_atr * atr_tp_mult) if sig == "BUY" else c_open - (p_atr * atr_tp_mult)

                position = {
                    "side": sig,
                    "entry_price": c_open,
                    "size": size,
                    "sl": sl,
                    "tp": tp,
                    "init_atr": p_atr,
                    "is_breakeven": False
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
    tp_count = len(tdf[tdf["reason"] == "TAKE_PROFIT"])
    be_count = len(tdf[tdf["reason"] == "BREAKEVEN"])
    sl_count = len(tdf[tdf["reason"] == "STOP_LOSS"])

    tot_pnl = tdf["pnl"].sum()
    tot_fee = tdf["fee"].sum()
    profit_factor = (wins["pnl"].sum() / abs(losses["pnl"].sum())) if len(losses) > 0 else float("inf")

    print("\n" + "=" * 60)
    print(f"✨ [개선된 퀀트 전략 백테스트 성과 리포트]")
    print(f"   (수수료 유형: {'Maker 0.02%' if use_maker_fee else 'Taker 0.06%'} | 본절스탑: {use_breakeven_stop} | ADX필터: {adx_threshold})")
    print("=" * 60)
    print(f"• 시작 잔고       : ${initial_balance:,.2f} USDT")
    print(f"• 최종 잔고       : ${balance:,.2f} USDT")
    print(f"• 총 수익률 (ROI) : {((balance - initial_balance)/initial_balance)*100:+.2f}%")
    print(f"• 총 거래 횟수    : {n_trades}회 (익절 {tp_count}회 | 본절청산 {be_count}회 | 손절 {sl_count}회)")
    print(f"• 승률 (순수 익절): {wr:.2f}% (본절 방어로 손실 차단)")
    print(f"• Profit Factor   : {profit_factor:.2f}")
    print(f"• 총 발생 수수료  : ${tot_fee:,.2f} USDT")
    print("=" * 60)

    print("\n📅 [월별 손익 현황]")
    print(f"{'연월 (Month)':<12} | {'거래수':<8} | {'승률':<8} | {'월간 손익(USDT)':<15}")
    print("-" * 50)
    for m, g in tdf.groupby("month"):
        w = len(g[g["pnl"] > 0])
        pnl = g["pnl"].sum()
        sign = "+" if pnl >= 0 else ""
        print(f"{str(m):<12} | {len(g):<8} | {(w/len(g)*100):5.1f}%  | {sign}${pnl:8.2f}")
    print("=" * 60)

if __name__ == "__main__":
    print("🚀 [1] 지정가(Maker) + 본절스탑 + ADX 추세 필터 적용 백테스트 실행:")
    run_optimized_backtest(use_maker_fee=True, use_breakeven_stop=True, adx_threshold=22.0)
