
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

def run_100m_roadmap():
    print("=" * 95)
    print("🎯 [100만 원 시작 ➡️ 2년(24개월) 내 1억 원 달성 퀀트 로드맵 시뮬레이션]")
    print("=" * 95)
    print("• 1단계 (1~3개월) : 100만 원($750)으로 실전 트레이딩 검증")
    print("• 2단계 (4개월차~) : 수익성 검증 후 1,000만 원+ 추가 시드 투입")
    print("• 3단계 (5~24개월): 2.0x~2.5x 퀀트 복리 트레이딩 + 매월 저축(시드 부스팅) 결합")
    print("=" * 95)

    scenarios = [
        {"name": "플랜 A: 4개월차 1,000만 원 투입 + 월 50만 원 저축 (레버리지 2.0x)", "stage2": 1000, "monthly": 50, "lev": 2.0},
        {"name": "플랜 B: 4개월차 1,000만 원 투입 + 월 100만 원 저축 (레버리지 2.0x)", "stage2": 1000, "monthly": 100, "lev": 2.0},
        {"name": "플랜 C: 4개월차 2,000만 원 투입 + 월 100만 원 저축 (레버리지 2.5x)", "stage2": 2000, "monthly": 100, "lev": 2.5},
        {"name": "플랜 D: 4개월차 3,000만 원 투입 + 월 100만 원 저축 (레버리지 2.0x)", "stage2": 3000, "monthly": 100, "lev": 2.0},
    ]

    # 3년 실데이터 로드
    df_btc = pd.read_csv("data/BTC_USDT_USDT_1h_1095d.csv")
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

    df_sol = pd.read_csv("data/SOL_USDT_USDT_1h_1095d.csv")
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

    print(f"{'플랜 명':<42} | {'총 투입원금':<10} | {'2년 뒤 최종자산':<14} | {'순 트레이딩수익':<14} | {'1억 원 달성일'}")
    print("-" * 105)

    for sc in scenarios:
        balance = 750.0 # 100만 원
        total_injected = 100.0 # 만 원 단위
        curr_m = None
        m_count = 0
        reach_100m_date = None
        pos_b = None
        pos_s = None

        for i in range(205, len(merged)):
            dt = merged["datetime"].iloc[i]
            if curr_m is not None and dt.month != curr_m:
                m_count += 1
                if m_count == 3: # 4개월차에 2단계 투입
                    balance += (sc["stage2"] * 10000) / 1350.0
                    total_injected += sc["stage2"]
                elif m_count > 3:
                    balance += (sc["monthly"] * 10000) / 1350.0
                    total_injected += sc["monthly"]
            curr_m = dt.month

            if m_count >= 24: # 2년(24개월) 종료
                break

            # 청산
            if pos_b is not None:
                if merged["b_l"].iloc[i] <= merged["b_m20"].iloc[i-1]:
                    exit_p = merged["b_m20"].iloc[i-1]
                    pnl = (exit_p - pos_b["entry"]) * pos_b["size"] - (pos_b["entry"]*pos_b["size"] + exit_p*pos_b["size"])*0.0004
                    balance += pnl
                    pos_b = None

            if pos_s is not None:
                if merged["s_l"].iloc[i] <= merged["s_m20"].iloc[i-1]:
                    exit_p = merged["s_m20"].iloc[i-1]
                    pnl = (exit_p - pos_s["entry"]) * pos_s["size"] - (pos_s["entry"]*pos_s["size"] + exit_p*pos_s["size"])*0.0004
                    balance += pnl
                    pos_s = None

            bal_won = balance * 1350.0 / 10000.0 # 만 원 단위
            if bal_won >= 10000.0 and reach_100m_date is None:
                reach_100m_date = dt.strftime("%Y-%m-%d")

            # 진입
            if pos_b is None and balance > 50:
                if merged["b_c"].iloc[i-1] > merged["b_h20"].iloc[i-1] and merged["b_c"].iloc[i-1] > merged["b_ema"].iloc[i-1]:
                    size = (balance * 0.5 * sc["lev"]) / merged["b_o"].iloc[i]
                    pos_b = {"entry": merged["b_o"].iloc[i], "size": size}

            if pos_s is None and balance > 50:
                if merged["s_c"].iloc[i-1] > merged["s_h20"].iloc[i-1] and merged["s_c"].iloc[i-1] > merged["s_ema"].iloc[i-1]:
                    size = (balance * 0.5 * sc["lev"]) / merged["s_o"].iloc[i]
                    pos_s = {"entry": merged["s_o"].iloc[i], "size": size}

        final_won = balance * 1350.0 / 10000.0
        profit_won = final_won - total_injected
        reach_str = f"🏆 {reach_100m_date} 달성" if reach_100m_date else "2년 내 미도달 (추가 시드 필요)"

        print(f"{sc['name']:<42} | {total_injected:,.0f}만 원   | {final_won:,.0f}만 원      | +{profit_won:,.0f}만 원     | {reach_str}")

    print("=" * 105)

if __name__ == "__main__":
    run_100m_roadmap()
