import sys
import os
import pandas as pd
import numpy as np

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def run_detailed_3y_analysis(
    btc_csv: str = "data/BTC_USDT_USDT_1h_1095d.csv",
    sol_csv: str = "data/SOL_USDT_USDT_1h_1095d.csv",
    initial_balance: float = 1000.0,
    leverage: float = 2.0,
    fee_rate: float = 0.0004
):
    print("=" * 105)
    print("🔬 [3년치 실데이터(2023.10 ~ 2026.10) 퀀트 전략 정밀 백테스트 상세 리포트]")
    print(f"• 초기 자본금 : ${initial_balance:,.2f} USDT (약 100만 원)")
    print(f"• 운용 레버리지: {leverage}x (BTC 50% + SOL 50% 분산 포트폴리오)")
    print("• 타임프레임  : 4시간봉 (4h) | 추세 필터: 200 EMA | 채널: 20봉(80시간) 돈키언 & 중간선 청산")
    print(f"• 거래 수수료 : 0.04% (Maker/Taker 가중평균 왕복)")
    print("=" * 105)

    # 1. BTC 데이터 로드 및 4h 합성
    df_btc = pd.read_csv(btc_csv)
    df_btc["datetime"] = pd.to_datetime(df_btc["timestamp"], unit="ms")
    df_btc.set_index("datetime", inplace=True)
    b_4h = df_btc.resample("4h").agg({
        "open": "first", "high": "max", "low": "min", "close": "last"
    }).dropna().reset_index()
    b_4h["ema200"] = b_4h["close"].ewm(span=200, adjust=False).mean()
    b_4h["high_20"] = b_4h["high"].shift(1).rolling(20).max()
    b_4h["mid_20"] = (b_4h["high_20"] + b_4h["low"].shift(1).rolling(20).min()) / 2
    b_4h.rename(columns={
        "open": "b_o", "high": "b_h", "low": "b_l", "close": "b_c",
        "high_20": "b_h20", "mid_20": "b_m20", "ema200": "b_ema"
    }, inplace=True)

    # 2. SOL 데이터 로드 및 4h 합성
    df_sol = pd.read_csv(sol_csv)
    df_sol["datetime"] = pd.to_datetime(df_sol["timestamp"], unit="ms")
    df_sol.set_index("datetime", inplace=True)
    s_4h = df_sol.resample("4h").agg({
        "open": "first", "high": "max", "low": "min", "close": "last"
    }).dropna().reset_index()
    s_4h["ema200"] = s_4h["close"].ewm(span=200, adjust=False).mean()
    s_4h["high_20"] = s_4h["high"].shift(1).rolling(20).max()
    s_4h["mid_20"] = (s_4h["high_20"] + s_4h["low"].shift(1).rolling(20).min()) / 2
    s_4h.rename(columns={
        "open": "s_o", "high": "s_h", "low": "s_l", "close": "s_c",
        "high_20": "s_h20", "mid_20": "s_m20", "ema200": "s_ema"
    }, inplace=True)

    merged = pd.merge(b_4h, s_4h, on="datetime").dropna().reset_index(drop=True)

    balance = initial_balance
    peak = balance
    mdd = 0.0
    pos_b = None
    pos_s = None
    trades = []
    equity_curve = []

    for i in range(205, len(merged)):
        dt = merged["datetime"].iloc[i]

        # BTC 청산 검사
        if pos_b is not None:
            if merged["b_l"].iloc[i] <= merged["b_m20"].iloc[i-1]:
                exit_p = merged["b_m20"].iloc[i-1]
                gross_pnl = (exit_p - pos_b["entry"]) * pos_b["size"]
                fee = (pos_b["entry"] * pos_b["size"] + exit_p * pos_b["size"]) * fee_rate
                net_pnl = gross_pnl - fee
                balance += net_pnl
                trades.append({
                    "entry_time": pos_b["time"], "exit_time": dt, "symbol": "BTC",
                    "entry_price": pos_b["entry"], "exit_price": exit_p,
                    "net_pnl": net_pnl, "return_pct": (exit_p - pos_b["entry"]) / pos_b["entry"] * 100,
                    "balance": balance
                })
                pos_b = None

        # SOL 청산 검사
        if pos_s is not None:
            if merged["s_l"].iloc[i] <= merged["s_m20"].iloc[i-1]:
                exit_p = merged["s_m20"].iloc[i-1]
                gross_pnl = (exit_p - pos_s["entry"]) * pos_s["size"]
                fee = (pos_s["entry"] * pos_s["size"] + exit_p * pos_s["size"]) * fee_rate
                net_pnl = gross_pnl - fee
                balance += net_pnl
                trades.append({
                    "entry_time": pos_s["time"], "exit_time": dt, "symbol": "SOL",
                    "entry_price": pos_s["entry"], "exit_price": exit_p,
                    "net_pnl": net_pnl, "return_pct": (exit_p - pos_s["entry"]) / pos_s["entry"] * 100,
                    "balance": balance
                })
                pos_s = None

        # MDD 추적
        if balance > peak:
            peak = balance
        dd = (peak - balance) / peak
        if dd > mdd:
            mdd = dd
        equity_curve.append({"dt": dt, "balance": balance})

        # BTC 신규 진입 (상승 추세 정렬 시 50% 비중)
        if pos_b is None and balance > 50:
            if merged["b_c"].iloc[i-1] > merged["b_h20"].iloc[i-1] and merged["b_c"].iloc[i-1] > merged["b_ema"].iloc[i-1]:
                size = (balance * 0.5 * leverage) / merged["b_o"].iloc[i]
                pos_b = {"time": dt, "entry": merged["b_o"].iloc[i], "size": size}

        # SOL 신규 진입 (상승 추세 정렬 시 50% 비중)
        if pos_s is None and balance > 50:
            if merged["s_c"].iloc[i-1] > merged["s_h20"].iloc[i-1] and merged["s_c"].iloc[i-1] > merged["s_ema"].iloc[i-1]:
                size = (balance * 0.5 * leverage) / merged["s_o"].iloc[i]
                pos_s = {"time": dt, "entry": merged["s_o"].iloc[i], "size": size}

    tdf = pd.DataFrame(trades)
    tdf["month"] = tdf["exit_time"].dt.to_period("M")
    tdf["year"] = tdf["exit_time"].dt.year

    total_trades = len(tdf)
    wins = tdf[tdf["net_pnl"] > 0]
    losses = tdf[tdf["net_pnl"] <= 0]
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0

    tot_profit = wins["net_pnl"].sum()
    tot_loss = abs(losses["net_pnl"].sum())
    profit_factor = (tot_profit / tot_loss) if tot_loss > 0 else 999.0
    avg_win = wins["net_pnl"].mean() if len(wins) > 0 else 0
    avg_loss = abs(losses["net_pnl"].mean()) if len(losses) > 0 else 0
    payoff_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0

    tot_roi = ((balance - initial_balance) / initial_balance) * 100

    print("\n" + "=" * 105)
    print("📊 [1. 핵심 퀀트 트레이딩 성과 요약 (KPI)]")
    print("=" * 105)
    print(f"• 시작 자본금         : ${initial_balance:,.2f} USDT (약 1,000,000원)")
    print(f"• 최종 자본금         : ${balance:,.2f} USDT (약 {balance * 1350:,.0f}원)")
    print(f"• 총 순수익률 (ROI)   : {tot_roi:+.2f}% ({balance/initial_balance:.2f}배 성장)")
    print(f"• 최대 낙폭 (MDD)     : {mdd * 100:.2f}%")
    print(f"• 총 체결 횟수        : {total_trades}회 (승: {len(wins)}회 / 패: {len(losses)}회)")
    print(f"• 승률 (Win Rate)     : {win_rate:.2f}%")
    print(f"• 프로핏 팩터 (PF)    : {profit_factor:.2f} (총수익 / 총손실)")
    print(f"• 평균 손익비 (Payoff): 1 : {payoff_ratio:.2f} (평균익절 ${avg_win:.1f} vs 평균손절 ${avg_loss:.1f})")
    print("=" * 105)

    # 2. 연도별 요약
    print("\n📅 [2. 연도별 성과 요약 (Yearly Performance)]")
    print(f"{'연도 (Year)':<12} | {'거래수':<8} | {'승률':<8} | {'연간 순손익(USDT)':<18} | {'기말 잔고(USDT)':<18}")
    print("-" * 75)
    for y, g in tdf.groupby("year"):
        w = len(g[g["net_pnl"] > 0])
        pnl = g["net_pnl"].sum()
        end_bal = g["balance"].iloc[-1]
        sign = "+" if pnl >= 0 else ""
        print(f"{str(y):<12} | {len(g):<8} | {(w/len(g)*100):5.1f}%  | {sign}${pnl:10.2f}       | ${end_bal:10.2f}")
    print("-" * 75)

    # 3. 36개월 월별 상세 손익 테이블
    print("\n📅 [3. 36개월 전체 월별 상세 손익표 (Monthly PnL Table)]")
    print(f"{'연월 (Month)':<10} | {'체결수':<6} | {'승':<4} | {'패':<4} | {'승률':<7} | {'월간 순손익(USDT)':<18} | {'월말 누적잔고(USDT)':<18}")
    print("-" * 80)
    pos_months = 0
    tot_months = 0
    for m, g in tdf.groupby("month"):
        tot_months += 1
        w = len(g[g["net_pnl"] > 0])
        l = len(g[g["net_pnl"] <= 0])
        pnl = g["net_pnl"].sum()
        end_bal = g["balance"].iloc[-1]
        if pnl >= 0:
            pos_months += 1
        sign = "+" if pnl >= 0 else ""
        print(f"{str(m):<10} | {len(g):>4}회 | {w:>2} | {l:>2} | {(w/len(g)*100):5.1f}% | {sign}${pnl:>9.2f}        | ${end_bal:>10.2f}")
    print("-" * 80)
    print(f"🏆 월간 플러스 달성률: {pos_months}/{tot_months}개월 ({(pos_months/tot_months)*100:.1f}%)")
    print("=" * 80)

    # 4. 최대 수익 거래 TOP 3 & 최대 손실 거래 TOP 3
    print("\n💎 [4. 대표 체결 거래 샘플 (Top Wins & Losses)]")
    print("-" * 90)
    print("🥇 [최고 수익 거래 TOP 3]")
    for idx, r in tdf.sort_values(by="net_pnl", ascending=False).head(3).iterrows():
        print(f"  • {r['symbol']} 매수: {r['entry_time'].strftime('%Y-%m-%d %H:%M')} (${r['entry_price']:,.2f}) ➡️ 청산: {r['exit_time'].strftime('%Y-%m-%d %H:%M')} (${r['exit_price']:,.2f}) | 수익: +${r['net_pnl']:.2f} ({r['return_pct']:+.1f}%)")
    print("\n🛡️ [최대 손실 거래 TOP 3 (철저한 칼손절 검증)]")
    for idx, r in tdf.sort_values(by="net_pnl", ascending=True).head(3).iterrows():
        print(f"  • {r['symbol']} 매수: {r['entry_time'].strftime('%Y-%m-%d %H:%M')} (${r['entry_price']:,.2f}) ➡️ 손절: {r['exit_time'].strftime('%Y-%m-%d %H:%M')} (${r['exit_price']:,.2f}) | 손실: ${r['net_pnl']:.2f} ({r['return_pct']:+.1f}%)")
    print("=" * 90)

if __name__ == "__main__":
    run_detailed_3y_analysis()
