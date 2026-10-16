
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

def run_leverage_comparison():
    btc_csv = "data/BTC_USDT_USDT_1h_1095d.csv"
    sol_csv = "data/SOL_USDT_USDT_1h_1095d.csv"
    fee_rate = 0.0004

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

    print("=" * 105)
    print("⚖️ [레버리지 배율별 3년 실데이터(2023.10 ~ 2026.10) 수익률 vs 리스크 비교 분석]")
    print("=" * 105)

    leverages = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 7.0, 10.0]

    # 1. 100만 원 + 월 55만 원 적립식 결합
    print("\n📌 [케이스 A: 100만 원 + 매월 55만 원($400) 적립식 결합]")
    print(f"{'레버리지':<8} | {'최종 잔고 (USDT / 원화)':<26} | {'순 트레이딩 수익':<16} | {'MDD':<7} | {'1,000만 원 달성일':<14} | {'평가'}")
    print("-" * 100)

    for lev in leverages:
        balance = 1000.0
        total_dep = 1000.0
        peak = balance
        mdd = 0.0
        pos_b = None
        pos_s = None
        curr_m = None
        reach_10k = None

        for i in range(205, len(merged)):
            dt = merged["datetime"].iloc[i]
            if curr_m is not None and dt.month != curr_m:
                balance += 400.0
                total_dep += 400.0
            curr_m = dt.month

            if pos_b is not None:
                if merged["b_l"].iloc[i] <= merged["b_m20"].iloc[i-1]:
                    exit_p = merged["b_m20"].iloc[i-1]
                    pnl = (exit_p - pos_b["entry"]) * pos_b["size"] - (pos_b["entry"]*pos_b["size"] + exit_p*pos_b["size"])*fee_rate
                    balance += pnl
                    pos_b = None

            if pos_s is not None:
                if merged["s_l"].iloc[i] <= merged["s_m20"].iloc[i-1]:
                    exit_p = merged["s_m20"].iloc[i-1]
                    pnl = (exit_p - pos_s["entry"]) * pos_s["size"] - (pos_s["entry"]*pos_s["size"] + exit_p*pos_s["size"])*fee_rate
                    balance += pnl
                    pos_s = None

            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak
            if dd > mdd:
                mdd = dd

            if balance >= 10000.0 and reach_10k is None:
                reach_10k = dt.strftime("%Y-%m-%d")

            if pos_b is None and balance > 50:
                if merged["b_c"].iloc[i-1] > merged["b_h20"].iloc[i-1] and merged["b_c"].iloc[i-1] > merged["b_ema"].iloc[i-1]:
                    size = (balance * 0.5 * lev) / merged["b_o"].iloc[i]
                    pos_b = {"entry": merged["b_o"].iloc[i], "size": size}

            if pos_s is None and balance > 50:
                if merged["s_c"].iloc[i-1] > merged["s_h20"].iloc[i-1] and merged["s_c"].iloc[i-1] > merged["s_ema"].iloc[i-1]:
                    size = (balance * 0.5 * lev) / merged["s_o"].iloc[i]
                    pos_s = {"entry": merged["s_o"].iloc[i], "size": size}

        won_str = f"약 {balance*1350/10000:,.0f}만 원"
        eval_str = ""
        if lev == 2.0:
            eval_str = "⭐ 안정성과 속도의 황금비율"
        elif lev == 3.0:
            eval_str = "🔥 공격형 (약 3주 단축, 낙폭 50%)"
        elif lev == 4.0:
            eval_str = "⚠️ 수익률 정점 (낙폭 61.8% 감내 필요)"
        elif lev >= 5.0 and lev < 10.0:
            eval_str = "❌ 역효과 (낙폭 과다로 수익 감소)"
        elif lev == 10.0:
            eval_str = "💀 파산/원금 손실 (MDD 96.3%)"

        print(f"{lev:4.1f}x    | ${balance:>10,.1f} ({won_str:<8}) | +${balance-total_dep:>10,.1f} | {mdd*100:5.1f}% | {reach_10k or '미도달':<14} | {eval_str}")
    print("=" * 100)

if __name__ == "__main__":
    run_leverage_comparison()
