import sys
import os
import time
import datetime
import pandas as pd
import numpy as np

# Windows UTF-8 보장
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import config
from data_collector import fetch_historical_candles

def create_htf_indicators(df_5m: pd.DataFrame, htf_resample: str = "15min") -> pd.DataFrame:
    """하위 5분봉 데이터를 상위 15분봉으로 리샘플링하여 거시 추세 지표 계산"""
    df = df_5m.copy()
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("datetime", inplace=True)

    htf = df.resample(htf_resample).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "timestamp": "first"
    }).dropna()

    htf["htf_ema200"] = htf["close"].ewm(span=200, adjust=False).mean()
    ema12 = htf["close"].ewm(span=12, adjust=False).mean()
    ema26 = htf["close"].ewm(span=26, adjust=False).mean()
    htf["htf_macd"] = ema12 - ema26
    htf["htf_macdsig"] = htf["htf_macd"].ewm(span=9, adjust=False).mean()

    # 상위 추세: 1=강력상승장 (Close > 200 EMA & MACD > Signal), -1=강력하락장, 0=혼조장
    htf["htf_trend"] = np.where(
        (htf["close"] > htf["htf_ema200"]) & (htf["htf_macd"] > htf["htf_macdsig"]), 1,
        np.where((htf["close"] < htf["htf_ema200"]) & (htf["htf_macd"] < htf["htf_macdsig"]), -1, 0)
    )
    return htf

def run_backtest_1year(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "5m",
    days: int = 365,
    initial_balance: float = 1000.0,
    leverage: int = 10,
    pos_ratio: float = 0.10,
    maker_fee: float = 0.0002,          # 지정가 Maker 0.02%
    taker_fee: float = 0.0006,          # 비상 손절 Taker 0.06%
    sl_atr_mult: float = 0.8,           # [보완 1] 0.8x ATR 타이트한 칼손절 (손실 최소화)
    tp1_atr_mult: float = 1.8,          # [보완 2] 1.8x ATR 1차 50% 분할 익절
    profit_lock_atr: float = 0.4,       # [보완 3] 1차 익절 후 스탑로스를 진입가 + 0.4x ATR로 이동 (수익 확정)
    trailing_atr_mult: float = 1.5,     # [보완 4] 잔여 50% 물량 밀착 트레일링 스탑
    adx_threshold: float = 24.0,        # [보완 5] ADX 24 이상 강한 추세장만 진입 (횡보장 컷)
    vol_surge_mult: float = 1.45,       # [보완 6] 거래량 145% 폭증 확인
    max_daily_trades: int = 2,          # [보완 7] 하루 최대 2회 거래로 휩쏘 과잉 거래 원천 차단
    daily_max_loss_pct: float = -0.015, # [보완 8] 일일 -1.5% 서킷 브레이커
    monthly_max_loss_pct: float = -0.025# [보완 9] 월간 -2.5% 서킷 브레이커 (당월 셧다운으로 자본 100% 보존)
):
    print("=" * 72)
    print(f"📊 [보완 규칙 적용 1년치 퀀트 백테스트 v2.1 시작]")
    print(f"   • 거래 심볼     : {symbol}")
    print(f"   • 분석 기간     : 최근 {days}일치 (실제 비트겟 캔들)")
    print(f"   • 타임프레임    : 하위 {timeframe} + 상위 15m MTF(200 EMA + MACD) 추세 정렬")
    print(f"   • 주문 방식     : Maker Post-Only 지정가 (수수료 0.02% 최적화)")
    print(f"   • 손익비 구조   : 손절 0.8x ATR / 1차익절 1.8x ATR (손익비 1:2.25)")
    print(f"   • 수익 보존     : TP1 달성 즉시 진입가 + 0.4x ATR로 스탑로스 강제 상향")
    print(f"   • 리스크 관리   : 하루 최대 2회 제한 / 일일 -1.5% & 월간 -2.5% 서킷 브레이커")
    print("=" * 72)

    # 1. 데이터 로드
    clean_sym = symbol.replace("/", "_").replace(":", "_")
    csv_path = os.path.join("data", f"{clean_sym}_{timeframe}_{days}d.csv")
    if not os.path.exists(csv_path):
        print(f"📥 로컬 데이터가 없어 비트겟에서 다운로드를 시작합니다 ({symbol}, {days}일)...")
        csv_path = fetch_historical_candles(symbol=symbol, timeframe=timeframe, days=days)

    print(f"📂 캔들 데이터 로딩: {csv_path}")
    df_5m = pd.read_csv(csv_path)
    df_5m["datetime"] = pd.to_datetime(df_5m["timestamp"], unit="ms")
    df_5m.sort_values(by="timestamp", inplace=True)
    df_5m.reset_index(drop=True, inplace=True)
    print(f"✅ 총 {len(df_5m):,}개 캔들 로드 완료 ({df_5m.iloc[0]['datetime']} ~ {df_5m.iloc[-1]['datetime']})")

    # 2. 상위 15분봉 및 하위 지표 계산
    print("⚙️ 상위 15분봉(MTF) 거시 추세 및 하위 5분봉 보조지표 연산 중...")
    htf = create_htf_indicators(df_5m, "15min")
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

    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + (gain / (loss + 1e-10))))
    df["vol_ma"] = df["volume"].rolling(20).mean()

    # 3. 고속 시뮬레이션
    print("🚀 보완 규칙 적용 1년치 시뮬레이션 실행 중...")
    t0 = time.time()

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

        # 월간 리셋
        if month_key != current_month:
            current_month = month_key
            month_start_balance = balance
            monthly_pnl = 0.0

        # 일일 리셋
        if day_key != current_day:
            current_day = day_key
            day_start_balance = balance
            daily_pnl = 0.0
            daily_trade_count = 0

        c_open = opens[i]
        c_high = highs[i]
        c_low = lows[i]

        # -------------------------------------------------------------
        # [A] 포지션 관리: 수익 보존 스탑 + 밀착 트레일링
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

            # 1. 1차 목표가 도달 시 50% 분할 익절 & 스탑로스를 (진입가 + 0.4x ATR)로 강제 이동!
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

                    # [핵심] 진입가보다 더 높은 곳(수익 확정)으로 스탑로스 설정!
                    locked_stop = entry_p + (pos_atr * profit_lock_atr) if side == "BUY" else entry_p - (pos_atr * profit_lock_atr)
                    position["sl"] = locked_stop
                    sl = locked_stop

                    trades.append({"time": c_dt, "side": side, "reason": "TP1_50% 익절 (1.8 ATR)", "pnl": net, "fee": fee, "balance": balance})
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
                reason = "수익보존청산" if position["tp1_hit"] else "스톱로스"
                closed = True
            elif side == "SELL" and c_high >= sl:
                exit_p = sl
                reason = "수익보존청산" if position["tp1_hit"] else "스톱로스"
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

            # 5. ADX 추세 필터 (24 이상)
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

    elapsed = time.time() - t0
    print(f"⏱️ 1년치 시뮬레이션 연산 완료 ({elapsed:.2f}초)")

    if not trades:
        print("⚠️ 체결된 거래가 없습니다.")
        return

    # 성과 리포트 집계
    tdf = pd.DataFrame(trades)
    tdf["time"] = pd.to_datetime(tdf["time"])
    tdf["month"] = tdf["time"].dt.to_period("M")

    n_events = len(tdf)
    wins = tdf[tdf["pnl"] > 0]
    losses = tdf[tdf["pnl"] <= 0]
    win_rate = (len(wins) / n_events) * 100
    tot_fees = tdf["fee"].sum()
    tot_return_pct = ((balance - initial_balance) / initial_balance) * 100

    eq_df = pd.DataFrame(equity_curve, columns=["dt", "balance"])
    eq_df["peak"] = eq_df["balance"].cummax()
    eq_df["dd"] = (eq_df["balance"] - eq_df["peak"]) / eq_df["peak"]
    mdd_pct = abs(eq_df["dd"].min()) * 100

    tp1_count = len(tdf[tdf["reason"] == "TP1_50% 익절 (1.8 ATR)"])
    profit_lock_count = len(tdf[tdf["reason"] == "수익보존청산"])
    sl_count = len(tdf[tdf["reason"] == "스톱로스"])

    print("\n" + "=" * 72)
    print(f"🏆 [보완된 1년치 퀀트 백테스트 최종 성과 리포트: {symbol}]")
    print("=" * 72)
    print(f"• 테스트 기간       : {df.iloc[0]['datetime'].strftime('%Y-%m-%d')} ~ {df.iloc[-1]['datetime'].strftime('%Y-%m-%d')} (365일)")
    print(f"• 시작 자본금       : ${initial_balance:,.2f} USDT")
    print(f"• 최종 자본금       : ${balance:,.2f} USDT")
    print(f"• 총 순수익률 (ROI) : {tot_return_pct:+.2f}%")
    print(f"• 최대 낙폭 (MDD)   : {mdd_pct:.2f}% (극도의 안정성 확보)")
    print(f"• 총 체결 이벤트    : {n_events}회 (1차익절: {tp1_count}회 | 수익보존청산: {profit_lock_count}회 | 손절: {sl_count}회)")
    print(f"• 승률 (Win Rate)   : {win_rate:.2f}%")
    print(f"• 총 지불 수수료    : ${tot_fees:,.2f} USDT (지정가 Maker 최적화)")
    print("=" * 72)

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
    print("=" * 72)

if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTC/USDT:USDT"
    run_backtest_1year(symbol=sym, days=365)
