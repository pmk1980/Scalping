import sys
import os
import pandas as pd
import numpy as np

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def run_compound_optimization(
    btc_csv: str = "data/BTC_USDT_USDT_5m_365d.csv",
    sol_csv: str = "data/SOL_USDT_USDT_5m_365d.csv",
    initial_balance: float = 1000.0,       # 시작 원금: $1,000 USDT (약 100만원)
    target_balance: float = 10000.0,       # 목표 금액: $10,000 USDT (약 1,000만원)
    fee_rate: float = 0.0004               # 라운드트립 수수료 (Maker 0.02% + avg slippage/taker)
):
    print("=" * 80)
    print("🚀 [100만 원 ➡️ 1,000만 원 초고속 복리 퀀트 시뮬레이션 엔진]")
    print(f"• 초기 자본금 : ${initial_balance:,.2f} USDT (약 100만 원)")
    print(f"• 목표 자본금 : ${target_balance:,.2f} USDT (약 1,000만 원, 10배 달성)")
    print("=" * 80)

    # 1. BTC 데이터 로드 및 1시간봉 리샘플링
    df_btc = pd.read_csv(btc_csv)
    df_btc["datetime"] = pd.to_datetime(df_btc["timestamp"], unit="ms")
    df_btc.set_index("datetime", inplace=True)
    btc_1h = df_btc.resample("1h").agg({
        "open": "first", "high": "max", "low": "min", "close": "last"
    }).dropna().reset_index()

    btc_1h["high_btc"] = btc_1h["high"].shift(1).rolling(16).max()
    btc_1h["low_btc"] = btc_1h["low"].shift(1).rolling(16).min()
    btc_1h["mid_btc"] = (btc_1h["high_btc"] + btc_1h["low_btc"]) / 2
    btc_1h["ema200_btc"] = btc_1h["close"].ewm(span=200, adjust=False).mean()
    btc_1h.rename(columns={
        "open": "open_btc", "high": "h_btc", "low": "l_btc", "close": "close_btc"
    }, inplace=True)

    # 2. SOL 데이터 로드 및 1시간봉 리샘플링
    df_sol = pd.read_csv(sol_csv)
    df_sol["datetime"] = pd.to_datetime(df_sol["timestamp"], unit="ms")
    df_sol.set_index("datetime", inplace=True)
    sol_1h = df_sol.resample("1h").agg({
        "open": "first", "high": "max", "low": "min", "close": "last"
    }).dropna().reset_index()

    sol_1h["high_sol"] = sol_1h["high"].shift(1).rolling(20).max()
    sol_1h["low_sol"] = sol_1h["low"].shift(1).rolling(20).min()
    sol_1h["mid_sol"] = (sol_1h["high_sol"] + sol_1h["low_sol"]) / 2
    sol_1h["ema200_sol"] = sol_1h["close"].ewm(span=200, adjust=False).mean()
    sol_1h.rename(columns={
        "open": "open_sol", "high": "h_sol", "low": "l_sol", "close": "close_sol"
    }, inplace=True)

    # 3. 데이터 병합
    merged = pd.merge(btc_1h, sol_1h, on="datetime").dropna().reset_index(drop=True)
    start_dt = merged["datetime"].iloc[0]
    end_dt = merged["datetime"].iloc[-1]
    print(f"📊 백테스트 기간: {start_dt.strftime('%Y-%m-%d')} ~ {end_dt.strftime('%Y-%m-%d')} (총 {(end_dt-start_dt).days}일)\n")

    # 시나리오 정의
    scenarios = [
        {"name": "시나리오 1: SOL 단독 공격형 (레버리지 3.5배, 월 추가입금 0원)", "type": "SOL_ONLY", "lev": 3.5, "deposit": 0.0},
        {"name": "시나리오 2: BTC+SOL 포트폴리오 안전형 (레버리지 3.0배, 월 추가입금 0원)", "type": "DUAL", "lev": 3.0, "deposit": 0.0},
        {"name": "시나리오 3: BTC+SOL 포트폴리오 성장형 (레버리지 3.5배, 월 추가입금 0원)", "type": "DUAL", "lev": 3.5, "deposit": 0.0},
        {"name": "시나리오 4: BTC+SOL 포트폴리오 고속형 (레버리지 4.0배, 월 추가입금 0원)", "type": "DUAL", "lev": 4.0, "deposit": 0.0},
        {"name": "시나리오 5: 포트폴리오 3.0배 + 월 35만원($250) 시드 부스팅", "type": "DUAL", "lev": 3.0, "deposit": 250.0},
        {"name": "시나리오 6: 포트폴리오 3.0배 + 월 55만원($400) 시드 부스팅", "type": "DUAL", "lev": 3.0, "deposit": 400.0},
    ]

    results = []

    for sc in scenarios:
        balance = initial_balance
        peak = balance
        mdd = 0.0
        pos_b = None
        pos_s = None
        trades = []
        reach_10k_date = None
        current_month = None
        total_deposited = initial_balance

        for i in range(25, len(merged)):
            c_dt = merged["datetime"].iloc[i]
            
            # 월초 추가 입금 처리
            if current_month is not None and c_dt.month != current_month:
                if sc["deposit"] > 0:
                    balance += sc["deposit"]
                    total_deposited += sc["deposit"]
            current_month = c_dt.month

            # 캔들 정보
            b_o = merged["open_btc"].iloc[i]
            b_h = merged["h_btc"].iloc[i]
            b_l = merged["l_btc"].iloc[i]
            b_pc = merged["close_btc"].iloc[i-1]
            b_ph = merged["high_btc"].iloc[i-1]
            b_pl = merged["low_btc"].iloc[i-1]
            b_pm = merged["mid_btc"].iloc[i-1]
            b_ema = merged["ema200_btc"].iloc[i-1]

            s_o = merged["open_sol"].iloc[i]
            s_h = merged["h_sol"].iloc[i]
            s_l = merged["l_sol"].iloc[i]
            s_pc = merged["close_sol"].iloc[i-1]
            s_ph = merged["high_sol"].iloc[i-1]
            s_pl = merged["low_sol"].iloc[i-1]
            s_pm = merged["mid_sol"].iloc[i-1]

            # 1. 청산 검사 (BTC)
            if pos_b is not None:
                exit_p = None
                if pos_b["side"] == "BUY" and b_l <= b_pm:
                    exit_p = b_pm
                elif pos_b["side"] == "SELL" and b_h >= b_pm:
                    exit_p = b_pm
                if exit_p is not None:
                    pnl = (exit_p - pos_b["entry"]) * pos_b["size"] if pos_b["side"] == "BUY" else (pos_b["entry"] - exit_p) * pos_b["size"]
                    fee = (pos_b["entry"] * pos_b["size"] + exit_p * pos_b["size"]) * fee_rate
                    net = pnl - fee
                    balance += net
                    trades.append({"dt": c_dt, "symbol": "BTC", "side": pos_b["side"], "pnl": net, "balance": balance})
                    pos_b = None

            # 2. 청산 검사 (SOL)
            if pos_s is not None:
                exit_p = None
                if pos_s["side"] == "BUY" and s_l <= s_pm:
                    exit_p = s_pm
                elif pos_s["side"] == "SELL" and s_h >= s_pm:
                    exit_p = s_pm
                if exit_p is not None:
                    pnl = (exit_p - pos_s["entry"]) * pos_s["size"] if pos_s["side"] == "BUY" else (pos_s["entry"] - exit_p) * pos_s["size"]
                    fee = (pos_s["entry"] * pos_s["size"] + exit_p * pos_s["size"]) * fee_rate
                    net = pnl - fee
                    balance += net
                    trades.append({"dt": c_dt, "symbol": "SOL", "side": pos_s["side"], "pnl": net, "balance": balance})
                    pos_s = None

            # 낙폭 추적
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak
            if dd > mdd:
                mdd = dd

            # 1,000만원 달성 여부 체크
            if balance >= target_balance and reach_10k_date is None:
                reach_10k_date = c_dt

            # 3. 신규 진입 검사
            if balance > 50:
                if sc["type"] == "DUAL":
                    alloc = 0.5
                    # BTC 진입 (EMA200 추세 정렬)
                    if pos_b is None:
                        if b_pc > b_ph and b_pc > b_ema:
                            size = (balance * alloc * sc["lev"]) / b_o
                            pos_b = {"side": "BUY", "entry": b_o, "size": size}
                        elif b_pc < b_pl and b_pc < b_ema:
                            size = (balance * alloc * sc["lev"]) / b_o
                            pos_b = {"side": "SELL", "entry": b_o, "size": size}

                    # SOL 진입
                    if pos_s is None:
                        if s_pc > s_ph:
                            size = (balance * alloc * sc["lev"]) / s_o
                            pos_s = {"side": "BUY", "entry": s_o, "size": size}
                        elif s_pc < s_pl:
                            size = (balance * alloc * sc["lev"]) / s_o
                            pos_s = {"side": "SELL", "entry": s_o, "size": size}
                
                elif sc["type"] == "SOL_ONLY":
                    if pos_s is None:
                        if s_pc > s_ph:
                            size = (balance * sc["lev"]) / s_o
                            pos_s = {"side": "BUY", "entry": s_o, "size": size}
                        elif s_pc < s_pl:
                            size = (balance * sc["lev"]) / s_o
                            pos_s = {"side": "SELL", "entry": s_o, "size": size}

        tdf = pd.DataFrame(trades)
        wins = len(tdf[tdf["pnl"] > 0]) if len(tdf) > 0 else 0
        wr = (wins / len(tdf) * 100) if len(tdf) > 0 else 0
        roi = ((balance - total_deposited) / total_deposited) * 100

        days_to_10k = (reach_10k_date - start_dt).days if reach_10k_date else None
        months_to_10k = round(days_to_10k / 30.4, 1) if days_to_10k else None

        results.append({
            "name": sc["name"],
            "final_balance": balance,
            "total_deposited": total_deposited,
            "roi": roi,
            "mdd": mdd * 100,
            "trades": len(tdf),
            "win_rate": wr,
            "reach_date": reach_10k_date.strftime("%Y-%m-%d") if reach_10k_date else "미도달(1년 내)",
            "months_to_10k": f"{months_to_10k}개월 ({days_to_10k}일)" if months_to_10k else "1년 초과",
            "trades_df": tdf
        })

    # 결과 테이블 출력
    print("=" * 100)
    print("🏆 [시나리오별 1,000만 원 달성 비교 결과표]")
    print("=" * 100)
    print(f"{'시나리오':<35} | {'최종잔고 (USDT)':<14} | {'수익률(ROI)':<10} | {'MDD':<7} | {'승률':<6} | {'1,000만 원 도달 소요'}")
    print("-" * 100)

    for r in results:
        bal_str = f"${r['final_balance']:,.1f}"
        roi_str = f"{r['roi']:+.1f}%"
        mdd_str = f"{r['mdd']:.1f}%"
        wr_str = f"{r['win_rate']:.1f}%"
        print(f"{r['name']:<35} | {bal_str:<14} | {roi_str:<10} | {mdd_str:<7} | {wr_str:<6} | {r['months_to_10k']}")
    print("=" * 100)

    # 1위 추천 전략의 월별 상세 출력
    top = results[2] # 시나리오 3: DUAL 3.5x
    print(f"\n📈 [추천 1위 전략 월별 손익 분석: {top['name']}]")
    print("-" * 65)
    print(f"{'연월 (Month)':<12} | {'체결수':<8} | {'승률':<8} | {'월간 순손익(USDT)':<18}")
    print("-" * 65)

    tdf = top["trades_df"]
    tdf["month"] = tdf["dt"].dt.to_period("M")
    for m, g in tdf.groupby("month"):
        w = len(g[g["pnl"] > 0])
        pnl = g["pnl"].sum()
        sign = "+" if pnl >= 0 else ""
        print(f"{str(m):<12} | {len(g):<8} | {(w/len(g)*100):5.1f}%  | {sign}${pnl:8.2f}")
    print("-" * 65)

if __name__ == "__main__":
    btc_p = sys.argv[1] if len(sys.argv) > 1 else "data/BTC_USDT_USDT_5m_365d.csv"
    sol_p = sys.argv[2] if len(sys.argv) > 2 else "data/SOL_USDT_USDT_5m_365d.csv"
    run_compound_optimization(btc_csv=btc_p, sol_csv=sol_p)
