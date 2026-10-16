
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

def run_all_green_backtest(
    csv_path: str = "data/BTC_USDT_USDT_5m_365d.csv",
    initial_balance: float = 1000.0,
    leverage: int = 10,
    pos_ratio: float = 0.10,
    maker_fee: float = 0.0002,     # 지정가 Maker 0.02%
    taker_fee: float = 0.0006,     # 손절 Taker 0.06%
    tp1_atr_mult: float = 1.8,     # [혁신 1] 1차 익절을 1.8x ATR로 충분한 이익 실현
    sl_atr_mult: float = 0.8,      # [혁신 2] 손절을 0.8x ATR로 칼손절 (손실 극소화)
    profit_lock_atr: float = 0.4,  # [혁신 3] 1차 익절 후 스탑로스를 진입가 + 0.4x ATR로 강제 이동 (수익 확정)
    trailing_atr_mult: float = 1.5,# [혁신 4] 잔여 50% 물량 밀착 트레일링
    adx_threshold: float = 24.0,   # [혁신 5] ADX 24 이상 강한 추세장만 진입
    vol_surge_mult: float = 1.5,   # [혁신 6] 거래량 150% 폭증 확인
    max_daily_trades: int = 2,     # [혁신 7] 하루 최대 2회 거래로 휩쏘 원천 봉쇄
    daily_max_loss_pct: float = -0.015, # 일일 -1.5% 서킷 브레이커
    monthly_max_loss_pct: float = -0.025 # [혁신 8] 월간 -2.5% 도달 시 당월 즉시 셧다운 (월간 대규모 손실 원천 차단)
):
    df_5m = pd.read_csv(csv_path)
    df_5m["datetime"] = pd.to_datetime(df_5m["timestamp"], unit="ms")
    df_5m.sort_values(by="timestamp", inplace=True)
    df_5m.reset_index(drop=True, inplace=True)

    # 상위 15분봉 리샘플링
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

    # 5분봉 지표 계산
    df["ema_fast"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=21, adjust=False).mean()
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

    # ADX
    plus_dm = df["high"].diff()
    minus_dm = -df["low"].diff()
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)
    tr_smooth = pd.Series(tr).rolling(14).mean()
    plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / (tr_smooth + 1e-10))
    minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / (tr_smooth + 1e-10))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    df["adx"] = dx.rolling(14).mean()

    # RSI & Volume MA
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + (gain / (loss + 1e-10))))
    df["vol_ma"] = df["volume"].rolling(20).mean()

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
    adx = df["adx"].values

    current_day = None
    current_month = None
    month_start_balance = initial_balance
    monthly_pnl = 0.0
    day_start_balance = initial_balance
    daily_pnl = 0.0
    daily_trade_count = 0
    cooldown_until_idx = 0

    equity_curve = [(df.iloc[0]["datetime"], initial_balance)]

    start_idx = 250
    for i in range(start_idx, len(df)):
        c_dt = pd.to_datetime(dts[i])
        day_key = c_dt.date()
        month_key = c_dt.to_period("M")

        if month_key != current_month:
            current_month = month_key
            month_start_balance = balance
            monthly_pnl = 0.0

        if day_key != current_day:
            current_day = day_key
            day_start_balance = balance
            daily_pnl = 0.0
            daily_trade_count = 0

        c_open = opens[i]
        c_high = highs[i]
        c_low = lows[i]

        # -------------------------------------------------------------
        # [A] 포지션 관리: 수익 보존 스탑(Profit Lock) + 밀착 트레일링
        # -------------------------------------------------------------
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

            # 1. 1차 익절 도달 (1.8 ATR) -> 50% 익절 & 스탑로스를 (진입가 + 0.4 ATR)로 강제 이동!
            if not position["tp1_hit"]:
                hit_tp1 = (side == "BUY" and c_high >= tp1) or (side == "SELL" and c_low <= tp1)
                if hit_tp1:
                    exit_qty = size * 0.5
                    gross = (tp1 - entry_p) * exit_qty if side == "BUY" else (entry_p - tp1) * exit_qty
                    fee = (exit_qty * entry_p + exit_qty * tp1) * maker_fee
                    net = gross - fee
                    balance += net
                    daily_pnl += net
                    monthly_pnl += net
                    position["size"] -= exit_qty
                    position["tp1_hit"] = True

                    # [핵심] 진입가보다 더 높은 곳(수익 확정 구간)으로 스탑로스 설정!
                    locked_stop = entry_p + (pos_atr * profit_lock_atr) if side == "BUY" else entry_p - (pos_atr * profit_lock_atr)
                    position["sl"] = locked_stop
                    sl = locked_stop

                    trades.append({"time": c_dt, "side": side, "reason": "1차익절 (1.8 ATR)", "pnl": net, "fee": fee, "balance": balance})
                    equity_curve.append((c_dt, balance))

            # 2. 잔여 물량 밀착 트레일링 스탑
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

            # 3. 청산 검사
            closed = False
            exit_p = None
            reason = None

            if side == "BUY" and c_low <= sl:
                exit_p = sl
                reason = "수익보존/트레일링청산" if position["tp1_hit"] else "손절"
                closed = True
            elif side == "SELL" and c_high >= sl:
                exit_p = sl
                reason = "수익보존/트레일링청산" if position["tp1_hit"] else "손절"
                closed = True

            if closed:
                rem_size = position["size"]
                fee_r = maker_fee if position["tp1_hit"] else taker_fee
                gross = (exit_p - entry_p) * rem_size if side == "BUY" else (entry_p - exit_p) * rem_size
                fee = (rem_size * entry_p + rem_size * exit_p) * fee_r
                net = gross - fee
                balance += net
                daily_pnl += net
                monthly_pnl += net

                if net <= 0 and not position["tp1_hit"]:
                    cooldown_until_idx = i + 12 # 손절 시 1시간 쿨다운

                trades.append({"time": c_dt, "side": side, "reason": reason, "pnl": net, "fee": fee, "balance": balance})
                equity_curve.append((c_dt, balance))
                position = None
                continue

        # -------------------------------------------------------------
        # [B] 신규 진입 검사 (다중 방어막)
        # -------------------------------------------------------------
        if position is None:
            # 1. 월간 최대 손실 서킷 브레이커 (월 -2.5% 도달 시 당월 즉시 셧다운)
            if month_start_balance > 0 and (monthly_pnl / month_start_balance) <= monthly_max_loss_pct:
                continue

            # 2. 일일 최대 손실 서킷 브레이커 (일 -1.5% 도달 시 당일 차단)
            if day_start_balance > 0 and (daily_pnl / day_start_balance) <= daily_max_loss_pct:
                continue

            # 3. 하루 최대 거래 횟수 제한 (하루 최대 2회)
            if daily_trade_count >= max_daily_trades:
                continue

            # 4. 쿨다운 검사
            if i < cooldown_until_idx:
                continue

            p_atr = atr[i-1]
            p_htf = htf_trend[i-1]
            p_adx = adx[i-1]

            if np.isnan(p_atr) or p_atr <= 0 or p_htf == 0 or np.isnan(p_adx):
                continue

            # 5. ADX 추세 필터
            if p_adx < adx_threshold:
                continue

            # 6. 볼륨 및 볼린저 밴드 스퀴즈 돌파
            vol_ok = volumes[i-1] > (vol_ma[i-1] * vol_surge_mult)
            sq_ok = bb_width[i-2] <= bb_width_ma[i-2] * 1.05
            p_rsi = rsi[i-1]

            sig = None
            if (p_htf == 1) and (ema_fast[i-1] > ema_slow[i-1]) and vol_ok and sq_ok and (closes[i-1] > bb_upper[i-1]) and (50 < p_rsi < 70):
                sig = "BUY"
            elif (p_htf == -1) and (ema_fast[i-1] < ema_slow[i-1]) and vol_ok and sq_ok and (closes[i-1] < bb_lower[i-1]) and (30 < p_rsi < 50):
                sig = "SELL"

            if sig:
                daily_trade_count += 1
                margin = balance * pos_ratio
                size = (margin * leverage) / c_open
                sl = c_open - (p_atr * sl_atr_mult) if sig == "BUY" else c_open + (p_atr * sl_atr_mult)
                tp1 = c_open + (p_atr * tp1_atr_mult) if sig == "BUY" else c_open - (p_atr * tp1_atr_mult)

                position = {
                    "side": sig, "entry_price": c_open, "size": size, "sl": sl, "tp1": tp1,
                    "atr": p_atr, "tp1_hit": False, "highest_p": c_open, "lowest_p": c_open
                }

    if not trades:
        print("조건 만족 거래 없음")
        return

    tdf = pd.DataFrame(trades)
    tdf["time"] = pd.to_datetime(tdf["time"])
    tdf["month"] = tdf["time"].dt.to_period("M")

    n_events = len(tdf)
    wins = tdf[tdf["pnl"] > 0]
    win_rate = (len(wins) / n_events) * 100
    tot_return_pct = ((balance - initial_balance) / initial_balance) * 100

    eq_df = pd.DataFrame(equity_curve, columns=["dt", "balance"])
    eq_df["peak"] = eq_df["balance"].cummax()
    eq_df["dd"] = (eq_df["balance"] - eq_df["peak"]) / eq_df["peak"]
    mdd_pct = abs(eq_df["dd"].min()) * 100

    tp1_count = len(tdf[tdf["reason"] == "1차익절 (1.8 ATR)"])
    trail_count = len(tdf[tdf["reason"] == "수익보존/트레일링청산"])
    sl_count = len(tdf[tdf["reason"] == "손절"])

    print("\n" + "=" * 70)
    print(f"✨ [월간 안정 수익 지향 퀀트 백테스트 결과: {os.path.basename(csv_path)}]")
    print("=" * 70)
    print(f"• 시작 자본금       : ${initial_balance:,.2f} USDT")
    print(f"• 최종 자본금       : ${balance:,.2f} USDT")
    print(f"• 총 순수익률 (ROI) : {tot_return_pct:+.2f}%")
    print(f"• 최대 낙폭 (MDD)   : {mdd_pct:.2f}%")
    print(f"• 총 체결 이벤트    : {n_events}회 (1차익절: {tp1_count}회 | 수익보존청산: {trail_count}회 | 손절: {sl_count}회)")
    print(f"• 승률 (Win Rate)   : {win_rate:.2f}%")
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
    p = sys.argv[1] if len(sys.argv) > 1 else "data/BTC_USDT_USDT_5m_365d.csv"
    run_all_green_backtest(csv_path=p)
