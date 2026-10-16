import sys
import pandas as pd
import numpy as np

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def run_mean_reversion_backtest(
    csv_path: str = "data/BTC_USDT_USDT_5m_365d.csv",
    fee_rate: float = 0.0002 # Maker 0.02%
):
    df = pd.read_csv(csv_path)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    
    # 지표 계산
    df["sma20"] = df["close"].rolling(20).mean()
    df["std20"] = df["close"].rolling(20).std()
    df["bb_upper"] = df["sma20"] + (df["std20"] * 2.0)
    df["bb_lower"] = df["sma20"] - (df["std20"] * 2.0)

    # RSI
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))

    # ATR
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    df["atr"] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()

    initial_balance = 1000.0
    balance = initial_balance
    leverage = 10
    pos_ratio = 0.10

    trades = []
    position = None

    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    dts = df["datetime"].values
    bb_upper = df["bb_upper"].values
    bb_lower = df["bb_lower"].values
    sma20 = df["sma20"].values
    rsi = df["rsi"].values
    atr = df["atr"].values

    for i in range(30, len(df)):
        c_open = opens[i]
        c_high = highs[i]
        c_low = lows[i]
        c_dt = dts[i]

        # 포지션 청산 검사 (중심선 도달 시 익절, 또는 손절)
        if position is not None:
            side = position["side"]
            entry_p = position["entry_price"]
            size = position["size"]
            sl = position["sl"]
            target = sma20[i-1] # 20 SMA 중심선 목표가

            closed = False
            exit_p = None
            reason = None

            if side == "BUY":
                if c_low <= sl:
                    exit_p = sl
                    reason = "STOP_LOSS"
                    closed = True
                elif c_high >= target:
                    exit_p = target
                    reason = "TAKE_PROFIT (SMA20)"
                    closed = True
            else:
                if c_high >= sl:
                    exit_p = sl
                    reason = "STOP_LOSS"
                    closed = True
                elif c_low <= target:
                    exit_p = target
                    reason = "TAKE_PROFIT (SMA20)"
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

        # 신규 진입 (Mean Reversion)
        if position is None:
            p_close = closes[i-1]
            p_low = lows[i-1]
            p_high = highs[i-1]
            p_rsi = rsi[i-1]
            p_atr = atr[i-1]

            if np.isnan(p_atr) or p_atr <= 0 or np.isnan(p_rsi):
                continue

            # 과매도 + 볼린저 하단 이탈 후 반등 -> 롱
            if p_low < bb_lower[i-1] and p_rsi < 30 and p_close > bb_lower[i-1]:
                sig = "BUY"
            # 과매수 + 볼린저 상단 이탈 후 반락 -> 숏
            elif p_high > bb_upper[i-1] and p_rsi > 70 and p_close < bb_upper[i-1]:
                sig = "SELL"
            else:
                sig = None

            if sig:
                margin = balance * pos_ratio
                size = (margin * leverage) / c_open
                # 손절: 1.5 ATR
                sl = c_open - (p_atr * 1.5) if sig == "BUY" else c_open + (p_atr * 1.5)

                position = {
                    "side": sig,
                    "entry_price": c_open,
                    "size": size,
                    "sl": sl
                }

    if not trades:
        print("거래 내역 없음")
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

    print("\n" + "=" * 60)
    print("🎯 [Mean Reversion 평균회귀 핑퐁 스캘핑 1년치 백테스트]")
    print("=" * 60)
    print(f"• 시작 잔고       : ${initial_balance:,.2f} USDT")
    print(f"• 최종 잔고       : ${balance:,.2f} USDT")
    print(f"• 총 수익률 (ROI) : {((balance - initial_balance)/initial_balance)*100:+.2f}%")
    print(f"• 총 거래 횟수    : {n_trades}회 (익절 {len(wins)}회 | 손절 {len(losses)}회)")
    print(f"• 승률 (Win Rate) : {wr:.2f}%")
    print(f"• Profit Factor   : {profit_factor:.2f}")
    print(f"• 총 수수료       : ${tot_fee:,.2f} USDT")
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
    run_mean_reversion_backtest()
