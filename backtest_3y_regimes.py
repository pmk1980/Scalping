import sys
import os
import pandas as pd
import numpy as np

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def run_3y_regime_backtest(
    btc_csv: str = "data/BTC_USDT_USDT_1h_1095d.csv",
    sol_csv: str = "data/SOL_USDT_USDT_1h_1095d.csv",
    initial_balance: float = 1000.0,
    fee_rate: float = 0.0004
):
    print("=" * 85)
    print("🛡️ [3년치 실데이터(2023.10 ~ 2026.10) 시장 국면별(상승장·횡보장·하락장) 스트레스 백테스트]")
    print(f"• 초기 자본금 : ${initial_balance:,.2f} USDT (약 100만 원)")
    print("• 분석 대상   : BTC/USDT 및 SOL/USDT 무기한 선물 (총 26,280시간 연속 캔들)")
    print("=" * 85)

    # 1. BTC 데이터 로드 및 4시간봉 변환
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

    # 2. SOL 데이터 로드 및 4시간봉 변환
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

    # 3. 4대 역사적 시장 국면 정의
    regimes = [
        {"name": "국면 1: 1차 대세 상승장 (비트코인 ETF 랠리)", "s": "2023-10-15", "e": "2024-03-15", "desc": "BTC $2.6만 ➡️ $7.3만 폭등 (+168%)"},
        {"name": "국면 2: 7개월 박스권 횡보장 (지루한 서머 촙)", "s": "2024-03-15", "e": "2024-10-15", "desc": "BTC $5.5만~$7.2만 지루한 박스권 (-8%)"},
        {"name": "국면 3: 2차 폭등 상승장 (10만 달러 돌파 랠리)", "s": "2024-10-15", "e": "2025-01-20", "desc": "BTC $6.5만 ➡️ $10.8만 신고가 (+51%)"},
        {"name": "국면 4: 대세 하락장 & 침체기 (크립토 조정장)", "s": "2025-01-20", "e": "2026-10-10", "desc": "BTC $12.6만 ➡️ $5.7만 폭락 (-55%)"}
    ]

    print("\n" + "=" * 95)
    print("📌 [1. 시장 국면별 단독 성과 분석 (상승장 vs 횡보장 vs 하락장)]")
    print("=" * 95)
    print(f"{'시장 국면':<32} | {'체결수':<6} | {'승률':<6} | {'국면 최종잔고':<14} | {'수익률(ROI)':<10} | {'MDD':<6}")
    print("-" * 95)

    for reg in regimes:
        sub = merged[(merged["datetime"] >= reg["s"]) & (merged["datetime"] <= reg["e"])].copy().reset_index(drop=True)
        balance = initial_balance
        peak = balance
        mdd = 0.0
        pos_b = None
        pos_s = None
        trades = []

        for i in range(2, len(sub)):
            # BTC 청산
            if pos_b is not None:
                if sub["b_l"].iloc[i] <= sub["b_m20"].iloc[i-1]:
                    exit_p = sub["b_m20"].iloc[i-1]
                    pnl = (exit_p - pos_b["entry"]) * pos_b["size"]
                    fee = (pos_b["entry"] * pos_b["size"] + exit_p * pos_b["size"]) * fee_rate
                    balance += (pnl - fee)
                    trades.append(pnl - fee)
                    pos_b = None

            # SOL 청산
            if pos_s is not None:
                if sub["s_l"].iloc[i] <= sub["s_m20"].iloc[i-1]:
                    exit_p = sub["s_m20"].iloc[i-1]
                    pnl = (exit_p - pos_s["entry"]) * pos_s["size"]
                    fee = (pos_s["entry"] * pos_s["size"] + exit_p * pos_s["size"]) * fee_rate
                    balance += (pnl - fee)
                    trades.append(pnl - fee)
                    pos_s = None

            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak
            if dd > mdd:
                mdd = dd

            # BTC 진입
            if pos_b is None and balance > 50:
                if sub["b_c"].iloc[i-1] > sub["b_h20"].iloc[i-1] and sub["b_c"].iloc[i-1] > sub["b_ema"].iloc[i-1]:
                    size = (balance * 0.5 * 2.0) / sub["b_o"].iloc[i]
                    pos_b = {"entry": sub["b_o"].iloc[i], "size": size}

            # SOL 진입
            if pos_s is None and balance > 50:
                if sub["s_c"].iloc[i-1] > sub["s_h20"].iloc[i-1] and sub["s_c"].iloc[i-1] > sub["s_ema"].iloc[i-1]:
                    size = (balance * 0.5 * 2.0) / sub["s_o"].iloc[i]
                    pos_s = {"entry": sub["s_o"].iloc[i], "size": size}

        tdf = pd.Series(trades)
        wr = (tdf > 0).sum() / len(tdf) * 100 if len(tdf) > 0 else 0
        roi = ((balance - initial_balance) / initial_balance) * 100
        print(f"{reg['name']:<32} | {len(tdf):>4}회 | {wr:5.1f}% | ${balance:>11,.2f} | {roi:>+8.1f}% | {mdd*100:5.1f}%")
        print(f"  └ 시장 실제 움직임: {reg['desc']}")
    print("-" * 95)

    # 4. 3년 연속 운용(복리) 시나리오 비교
    print("\n" + "=" * 95)
    print("📌 [2. 3년 전체 연속 운용 시 1,000만 원 달성 비교 (2023.10 ~ 2026.10)]")
    print("=" * 95)
    print(f"{'운용 시나리오':<35} | {'최종잔고 (USDT)':<14} | {'총 수익률':<10} | {'MDD':<7} | {'1,000만 원 달성일'}")
    print("-" * 95)

    scenarios = [
        {"name": "순수 100만 원 (레버리지 1.5배, 월 0원 추가)", "lev": 1.5, "dep": 0.0},
        {"name": "순수 100만 원 (레버리지 2.0배, 월 0원 추가)", "lev": 2.0, "dep": 0.0},
        {"name": "100만 원 + 월 35만 원($250) 적립식 결합", "lev": 2.0, "dep": 250.0},
        {"name": "100만 원 + 월 55만 원($400) 적립식 결합", "lev": 2.0, "dep": 400.0},
    ]

    for sc in scenarios:
        balance = initial_balance
        peak = balance
        mdd = 0.0
        pos_b = None
        pos_s = None
        trades = []
        reach_10k = None
        curr_m = None
        total_dep = initial_balance

        for i in range(205, len(merged)):
            dt = merged["datetime"].iloc[i]
            if curr_m is not None and dt.month != curr_m:
                if sc["dep"] > 0:
                    balance += sc["dep"]
                    total_dep += sc["dep"]
            curr_m = dt.month

            # 청산 검사
            if pos_b is not None:
                if merged["b_l"].iloc[i] <= merged["b_m20"].iloc[i-1]:
                    exit_p = merged["b_m20"].iloc[i-1]
                    pnl = (exit_p - pos_b["entry"]) * pos_b["size"]
                    fee = (pos_b["entry"] * pos_b["size"] + exit_p * pos_b["size"]) * fee_rate
                    balance += (pnl - fee)
                    pos_b = None

            if pos_s is not None:
                if merged["s_l"].iloc[i] <= merged["s_m20"].iloc[i-1]:
                    exit_p = merged["s_m20"].iloc[i-1]
                    pnl = (exit_p - pos_s["entry"]) * pos_s["size"]
                    fee = (pos_s["entry"] * pos_s["size"] + exit_p * pos_s["size"]) * fee_rate
                    balance += (pnl - fee)
                    pos_s = None

            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak
            if dd > mdd:
                mdd = dd

            if balance >= 10000.0 and reach_10k is None:
                reach_10k = dt.strftime("%Y-%m-%d")

            # 진입 검사
            if pos_b is None and balance > 50:
                if merged["b_c"].iloc[i-1] > merged["b_h20"].iloc[i-1] and merged["b_c"].iloc[i-1] > merged["b_ema"].iloc[i-1]:
                    size = (balance * 0.5 * sc["lev"]) / merged["b_o"].iloc[i]
                    pos_b = {"entry": merged["b_o"].iloc[i], "size": size}

            if pos_s is None and balance > 50:
                if merged["s_c"].iloc[i-1] > merged["s_h20"].iloc[i-1] and merged["s_c"].iloc[i-1] > merged["s_ema"].iloc[i-1]:
                    size = (balance * 0.5 * sc["lev"]) / merged["s_o"].iloc[i]
                    pos_s = {"entry": merged["s_o"].iloc[i], "size": size}

        roi = ((balance - total_dep) / total_dep) * 100
        reach_str = f"🏆 {reach_10k} 달성" if reach_10k else "3년 내 미도달"
        print(f"{sc['name']:<35} | ${balance:>12,.1f} | {roi:>+8.1f}% | {mdd*100:5.1f}% | {reach_str}")

    print("=" * 95)

if __name__ == "__main__":
    run_3y_regime_backtest()
