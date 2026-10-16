import sys
import os
import pandas as pd
import numpy as np

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def run_15m_quant_backtest(
    csv_path: str = "data/BTC_USDT_USDT_5m_365d.csv",
    initial_balance: float = 1000.0,
    leverage: int = 10,
    pos_ratio: float = 0.10,
    maker_fee: float = 0.0002
):
    df_5m = pd.read_csv(csv_path)
    df_5m["datetime"] = pd.to_datetime(df_5m["timestamp"], unit="ms")
    df_5m.set_index("datetime", inplace=True)

    # 15분봉으로 리샘플링
    df = df_5m.resample("15min").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "timestamp": "first"
    }).dropna().reset_index()

    # 상위 1시간봉 리샘플링
    df_idx = df.set_index("datetime")
    htf = df_idx.resample("1h").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
    }).dropna()
    htf["htf_ema200"] = htf["close"].ewm(span=200, adjust=False).mean()
    ema12 = htf["close"].ewm(span=12, adjust=False).mean()
    ema26 = htf["close"].ewm(span=26, adjust=False).mean()
    htf["macd"] = ema12 - ema26
    htf["macdsig"] = htf["macd"].ewm(span=9, adjust=False).mean()
    htf["htf_trend"] = np.where(
        (htf["close"] > htf["htf_ema200"]) & (htf["macd"] > htf["macdsig"]), 1,
        np.where((htf["close"] < htf["htf_ema200"]) & (htf["macd"] < htf["macdsig"]), -1, 0)
    )

    df = pd.merge_asof(
        df,
        htf[["htf_trend"]].reset_index(),
        on="datetime",
        direction="backward"
    )

    df["ema_fast"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=21, adjust=False).mean()
    df["bb_mid"] = df["close"].rolling(20).mean()
    df["bb_std"] = df["close"].rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + (df["bb_std"] * 2.0)
    df["bb_lower"] = df["bb_mid"] - (df["bb_std"] * 2.0)
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
    df["bb_width_ma"] = df["bb_width"].rolling(20).mean()

    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    df["atr"] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()
    df["vol_ma"] = df["volume"].rolling(20).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + (gain / (loss + 1e-10))))

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
            tp1 = position["tp1"]
            pos_atr = position["atr"]
            highest_p = max(position["highest_p"], c_high)
            lowest_p = min(position["lowest_p"], c_low)
            position["highest_p"] = highest_p
            position["lowest_p"] = lowest_p

            if not position["tp1_hit"]:
                hit = (side == "BUY" and c_high >= tp1) or (side == "SELL" and c_low <= tp1)
                if hit:
                    exit_qty = size * 0.5
                    gross = (tp1 - entry_p) * exit_qty if side == "BUY" else (entry_p - tp1) * exit_qty
                    fee = (exit_qty * entry_p + exit_qty * tp1) * maker_fee
                    net = gross - fee
                    balance += net
                    position["size"] -= exit_qty
                    position["tp1_hit"] = True
                    position["sl"] = entry_p + (pos_atr * 0.5 if side == "BUY" else -pos_atr * 0.5)
                    sl = position["sl"]
                    trades.append({"time": c_dt, "side": side, "reason": "TP1", "pnl": net, "balance": balance})

            if position["tp1_hit"]:
                if side == "BUY":
                    trail = highest_p - (pos_atr * 1.5)
                    if trail > position["sl"]:
                        position["sl"] = trail
                        sl = trail
                else:
                    trail = lowest_p + (pos_atr * 1.5)
                    if trail < position["sl"]:
                        position["sl"] = trail
                        sl = trail

            closed = False
            exit_p = None
            reason = None

            if side == "BUY" and c_low <= sl:
                exit_p = sl
                reason = "TRAIL" if position["tp1_hit"] else "SL"
                closed = True
            elif side == "SELL" and c_high >= sl:
                exit_p = sl
                reason = "TRAIL" if position["tp1_hit"] else "SL"
                closed = True

            if closed:
                rem_size = position["size"]
                fee_r = maker_fee if position["tp1_hit"] else 0.0006
                gross = (exit_p - entry_p) * rem_size if side == "BUY" else (entry_p - exit_p) * rem_size
                fee = (rem_size * entry_p + rem_size * exit_p) * fee_r
                net = gross - fee
                balance += net
                trades.append({"time": c_dt, "side": side, "reason": reason, "pnl": net, "balance": balance})
                position = None
                continue

        if position is None:
            p_atr = atr[i-1]
            p_htf = htf_trend[i-1]
            if np.isnan(p_atr) or p_atr <= 0 or p_htf == 0:
                continue

            vol_ok = volumes[i-1] > (vol_ma[i-1] * 1.3)
            p_rsi = rsi[i-1]

            sig = None
            if (p_htf == 1) and (ema_fast[i-1] > ema_slow[i-1]) and vol_ok and (closes[i-1] > bb_upper[i-1]) and (50 < p_rsi < 72):
                sig = "BUY"
            elif (p_htf == -1) and (ema_fast[i-1] < ema_slow[i-1]) and vol_ok and (closes[i-1] < bb_lower[i-1]) and (28 < p_rsi < 50):
                sig = "SELL"

            if sig:
                margin = balance * pos_ratio
                size = (margin * leverage) / c_open
                sl = c_open - (p_atr * 1.0) if sig == "BUY" else c_open + (p_atr * 1.0)
                tp1 = c_open + (p_atr * 2.0) if sig == "BUY" else c_open - (p_atr * 2.0)

                position = {
                    "side": sig, "entry_price": c_open, "size": size, "sl": sl, "tp1": tp1,
                    "atr": p_atr, "tp1_hit": False, "highest_p": c_open, "lowest_p": c_open
                }

    tdf = pd.DataFrame(trades)
    tdf["time"] = pd.to_datetime(tdf["time"])
    tdf["month"] = tdf["time"].dt.to_period("M")

    n_events = len(tdf)
    wins = tdf[tdf["pnl"] > 0]
    win_rate = (len(wins) / n_events) * 100
    tot_return_pct = ((balance - initial_balance) / initial_balance) * 100

    print("\n" + "=" * 70)
    print("🔥 [15분봉 + 1시간봉 MTF 퀀트 백테스트 결과: BTC 1년치]")
    print("=" * 70)
    print(f"• 시작 잔고       : ${initial_balance:,.2f} USDT")
    print(f"• 최종 잔고       : ${balance:,.2f} USDT")
    print(f"• 총 순수익률 (ROI) : {tot_return_pct:+.2f}%")
    print(f"• 총 체결 이벤트  : {n_events}회")
    print(f"• 승률 (Win Rate) : {win_rate:.2f}%")
    print("=" * 70)

    print("\n📅 [월별 상세 손익 현황]")
    print(f"{'연월 (Month)':<12} | {'체결수':<8} | {'승률':<8} | {'월간 순손익(USDT)':<18}")
    print("-" * 55)
    positive_months = 0
    total_months = 0
    for m, g in tdf.groupby("month"):
        total_months += 1
        w = len(g[g["pnl"] > 0])
        pnl = g["pnl"].sum()
        if pnl >= 0:
            positive_months += 1
        sign = "+" if pnl >= 0 else ""
        print(f"{str(m):<12} | {len(g):<8} | {(w/len(g)*100):5.1f}%  | {sign}${pnl:8.2f}")
    
    print("-" * 55)
    print(f"🏆 월간 플러스 달성률: {positive_months}/{total_months}개월 ({(positive_months/total_months)*100:.1f}%)")
    print("=" * 70)

if __name__ == "__main__":
    run_15m_quant_backtest()
