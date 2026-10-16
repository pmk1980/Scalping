
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

def run_risk_managed_backtest(
    csv_path: str = "data/SOL_USDT_USDT_5m_180d.csv",
    maker_fee_rate: float = 0.0002,     # 지정가 Maker 0.02%
    taker_fee_rate: float = 0.0006,     # 비상 손절 Taker 0.06%
    tp1_atr_mult: float = 2.0,          # 1차 익절: 2.0 ATR (확실한 이익 확보)
    sl_atr_mult: float = 1.0,           # 손절: 1.0 ATR (칼손절로 손실 최소화! 손익비 1:2)
    trailing_atr_mult: float = 2.0,     # 잔여 50% 추세 트레일링
    daily_max_loss_pct: float = -0.03,  # 일일 -3% 손실 시 당일 셧다운 (서킷 브레이커)
    max_consec_losses: int = 2,         # 2연속 손실 시 12봉(1시간) 쿨다운
    leverage: int = 10,
    pos_ratio: float = 0.10
):
    df_5m = pd.read_csv(csv_path)
    df_5m["datetime"] = pd.to_datetime(df_5m["timestamp"], unit="ms")
    df_5m.sort_values(by="timestamp", inplace=True)
    df_5m.reset_index(drop=True, inplace=True)

    # 15분봉 상위 추세 합성
    df_idx = df_5m.set_index("datetime")
    htf = df_idx.resample("15min").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "timestamp": "first"
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
        df_5m,
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

    current_day = None
    day_start_balance = initial_balance
    daily_pnl = 0.0
    consecutive_losses = 0
    cooldown_until_idx = 0

    for i in range(250, len(df)):
        c_dt = pd.to_datetime(dts[i])
        day_key = c_dt.date()

        # 일일 리셋
        if day_key != current_day:
            current_day = day_key
            day_start_balance = balance
            daily_pnl = 0.0

        c_open = opens[i]
        c_high = highs[i]
        c_low = lows[i]

        # 1. 오픈 포지션 관리
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

            # 1차 TP (50% 익절)
            if not position["tp1_hit"]:
                if side == "BUY" and c_high >= tp1:
                    exit_qty = size * 0.5
                    net = ((tp1 - entry_p) * exit_qty) - ((exit_qty * entry_p + exit_qty * tp1) * maker_fee_rate)
                    balance += net
                    daily_pnl += net
                    position["size"] -= exit_qty
                    position["tp1_hit"] = True
                    position["sl"] = entry_p + (entry_p * 0.0005)
                    sl = position["sl"]
                    consecutive_losses = 0
                    trades.append({"time": c_dt, "side": side, "reason": "TP1_50%", "pnl": net, "balance": balance})
                elif side == "SELL" and c_low <= tp1:
                    exit_qty = size * 0.5
                    net = ((entry_p - tp1) * exit_qty) - ((exit_qty * entry_p + exit_qty * tp1) * maker_fee_rate)
                    balance += net
                    daily_pnl += net
                    position["size"] -= exit_qty
                    position["tp1_hit"] = True
                    position["sl"] = entry_p - (entry_p * 0.0005)
                    sl = position["sl"]
                    consecutive_losses = 0
                    trades.append({"time": c_dt, "side": side, "reason": "TP1_50%", "pnl": net, "balance": balance})

            # 잔여 물량 트레일링
            if position["tp1_hit"]:
                if side == "BUY":
                    trail = highest_p - (pos_atr * trailing_atr_mult)
                    if trail > position["sl"]:
                        position["sl"] = trail
                        sl = trail
                else:
                    trail = lowest_p + (pos_atr * trailing_atr_mult)
                    if trail < position["sl"]:
                        position["sl"] = trail
                        sl = trail

            # 청산 검사
            closed = False
            exit_p = None
            reason = None

            if side == "BUY" and c_low <= sl:
                exit_p = sl
                reason = "TRAILING" if position["tp1_hit"] else "STOP_LOSS"
                closed = True
            elif side == "SELL" and c_high >= sl:
                exit_p = sl
                reason = "TRAILING" if position["tp1_hit"] else "STOP_LOSS"
                closed = True

            if closed:
                rem_size = position["size"]
                fee_r = maker_fee_rate if position["tp1_hit"] else taker_fee_rate
                gross = (exit_p - entry_p) * rem_size if side == "BUY" else (entry_p - exit_p) * rem_size
                fee = (rem_size * entry_p + rem_size * exit_p) * fee_r
                net = gross - fee
                balance += net
                daily_pnl += net

                if net <= 0 and not position["tp1_hit"]:
                    consecutive_losses += 1
                    if consecutive_losses >= max_consec_losses:
                        cooldown_until_idx = i + 12 # 1시간 쿨다운
                else:
                    consecutive_losses = 0

                trades.append({"time": c_dt, "side": side, "reason": reason, "pnl": net, "balance": balance})
                position = None
                continue

        # 2. 신규 진입 검사
        if position is None:
            # 서킷 브레이커: 일일 손실 한도 초과 시 당일 신규 진입 차단
            if day_start_balance > 0 and (daily_pnl / day_start_balance) <= daily_max_loss_pct:
                continue
            # 쿨다운 검사
            if i < cooldown_until_idx:
                continue

            p_atr = atr[i-1]
            p_htf = htf_trend[i-1]
            if np.isnan(p_atr) or p_atr <= 0 or p_htf == 0:
                continue

            vol_ok = volumes[i-1] > (vol_ma[i-1] * 1.4)
            sq_ok = bb_width[i-2] <= bb_width_ma[i-2] * 1.05
            p_rsi = rsi[i-1]

            sig = None
            if (p_htf == 1) and (ema_fast[i-1] > ema_slow[i-1]) and vol_ok and sq_ok and (closes[i-1] > bb_upper[i-1]) and (52 < p_rsi < 70):
                sig = "BUY"
            elif (p_htf == -1) and (ema_fast[i-1] < ema_slow[i-1]) and vol_ok and sq_ok and (closes[i-1] < bb_lower[i-1]) and (30 < p_rsi < 48):
                sig = "SELL"

            if sig:
                margin = balance * pos_ratio
                size = (margin * leverage) / c_open
                sl = c_open - (p_atr * sl_atr_mult) if sig == "BUY" else c_open + (p_atr * sl_atr_mult)
                tp1 = c_open + (p_atr * tp1_atr_mult) if sig == "BUY" else c_open - (p_atr * tp1_atr_mult)

                position = {
                    "side": sig, "entry_price": c_open, "size": size, "sl": sl, "tp1": tp1,
                    "atr": p_atr, "tp1_hit": False, "highest_p": c_open, "lowest_p": c_open
                }

    tdf = pd.DataFrame(trades)
    tdf["time"] = pd.to_datetime(tdf["time"])
    tdf["month"] = tdf["time"].dt.to_period("M")

    n_ev = len(tdf)
    wins = tdf[tdf["pnl"] > 0]
    wr = (len(wins) / n_ev) * 100
    tot_pnl = balance - initial_balance

    print("\n" + "=" * 65)
    print(f"💎 [서킷 브레이커 & 1:2 손익비 장착 퀀트 백테스트 결과: {os.path.basename(csv_path)}]")
    print("=" * 65)
    print(f"• 시작 잔고       : ${initial_balance:,.2f} USDT")
    print(f"• 최종 잔고       : ${balance:,.2f} USDT")
    print(f"• 총 수익률 (ROI) : {(tot_pnl / initial_balance) * 100:+.2f}%")
    print(f"• 총 체결 이벤트  : {n_ev}회")
    print(f"• 승률 (Win Rate) : {wr:.2f}%")
    print(f"• 순 손익         : {tot_pnl:+.2f} USDT")
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
    p = sys.argv[1] if len(sys.argv) > 1 else "data/SOL_USDT_USDT_5m_180d.csv"
    run_risk_managed_backtest(csv_path=p)
