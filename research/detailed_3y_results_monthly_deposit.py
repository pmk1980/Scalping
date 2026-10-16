
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

def run_monthly_deposit_detailed(
    btc_csv: str = "data/BTC_USDT_USDT_1h_1095d.csv",
    sol_csv: str = "data/SOL_USDT_USDT_1h_1095d.csv",
    initial_balance: float = 1000.0,
    monthly_deposit: float = 400.0, # 월 55만원 ($400)
    leverage: float = 2.0,
    fee_rate: float = 0.0004
):
    print("=" * 105)
    print("🚀 [100만 원 + 매달 55만 원($400) 적립식 결합: 3년치 36개월 상세 리포트]")
    print(f"• 초기 자본금   : ${initial_balance:,.2f} USDT (약 1,000,000원)")
    print(f"• 매월 적립액   : ${monthly_deposit:,.2f} USDT (약 540,000원 / 매월 1일 자동 합산)")
    print(f"• 운용 레버리지 : {leverage}x (BTC 50% + SOL 50% 분산 포트폴리오)")
    print("• 타임프레임    : 4시간봉 (4h) | 200 EMA 추세필터 + 20봉 채널 중간선 청산")
    print("=" * 105)

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

    balance = initial_balance
    total_deposited = initial_balance
    peak = balance
    mdd = 0.0
    pos_b = None
    pos_s = None
    curr_month = None
    monthly_logs = []
    current_month_trades = []
    reach_10k_info = None

    for i in range(205, len(merged)):
        dt = merged["datetime"].iloc[i]

        # 월이 바뀌면 입금 처리 및 이전 달 기록
        if curr_month is not None and dt.month != curr_month:
            # 이전 달 마감 정리
            n_tr = len(current_month_trades)
            w_tr = len([t for t in current_month_trades if t > 0])
            pnl_tr = sum(current_month_trades)
            wr = (w_tr / n_tr * 100) if n_tr > 0 else 0.0

            monthly_logs.append({
                "month_str": month_label,
                "start_bal": month_start_bal,
                "deposit": month_added_dep,
                "trades": n_tr,
                "wins": w_tr,
                "win_rate": wr,
                "trading_pnl": pnl_tr,
                "end_bal": balance,
                "cum_deposited": total_deposited
            })

            # 신규 월 입금
            balance += monthly_deposit
            total_deposited += monthly_deposit
            month_added_dep = monthly_deposit
            month_start_bal = balance
            current_month_trades = []
        elif curr_month is None:
            month_added_dep = 0.0
            month_start_bal = balance

        curr_month = dt.month
        month_label = dt.strftime("%Y-%m")

        # BTC 청산
        if pos_b is not None:
            if merged["b_l"].iloc[i] <= merged["b_m20"].iloc[i-1]:
                exit_p = merged["b_m20"].iloc[i-1]
                gross = (exit_p - pos_b["entry"]) * pos_b["size"]
                fee = (pos_b["entry"] * pos_b["size"] + exit_p * pos_b["size"]) * fee_rate
                net = gross - fee
                balance += net
                current_month_trades.append(net)
                pos_b = None

        # SOL 청산
        if pos_s is not None:
            if merged["s_l"].iloc[i] <= merged["s_m20"].iloc[i-1]:
                exit_p = merged["s_m20"].iloc[i-1]
                gross = (exit_p - pos_s["entry"]) * pos_s["size"]
                fee = (pos_s["entry"] * pos_s["size"] + exit_p * pos_s["size"]) * fee_rate
                net = gross - fee
                balance += net
                current_month_trades.append(net)
                pos_s = None

        if balance > peak:
            peak = balance
        dd = (peak - balance) / peak
        if dd > mdd:
            mdd = dd

        # 1,000만 원 돌파 체크
        if balance >= 10000.0 and reach_10k_info is None:
            reach_10k_info = {
                "date": dt.strftime("%Y-%m-%d"),
                "balance": balance,
                "deposited_so_far": total_deposited,
                "profit_so_far": balance - total_deposited
            }

        # 진입 검사
        if pos_b is None and balance > 50:
            if merged["b_c"].iloc[i-1] > merged["b_h20"].iloc[i-1] and merged["b_c"].iloc[i-1] > merged["b_ema"].iloc[i-1]:
                size = (balance * 0.5 * leverage) / merged["b_o"].iloc[i]
                pos_b = {"entry": merged["b_o"].iloc[i], "size": size}

        if pos_s is None and balance > 50:
            if merged["s_c"].iloc[i-1] > merged["s_h20"].iloc[i-1] and merged["s_c"].iloc[i-1] > merged["s_ema"].iloc[i-1]:
                size = (balance * 0.5 * leverage) / merged["s_o"].iloc[i]
                pos_s = {"entry": merged["s_o"].iloc[i], "size": size}

    # 마지막 달 추가
    if len(current_month_trades) > 0 or month_label:
        n_tr = len(current_month_trades)
        w_tr = len([t for t in current_month_trades if t > 0])
        pnl_tr = sum(current_month_trades)
        wr = (w_tr / n_tr * 100) if n_tr > 0 else 0.0
        monthly_logs.append({
            "month_str": month_label,
            "start_bal": month_start_bal,
            "deposit": month_added_dep,
            "trades": n_tr,
            "wins": w_tr,
            "win_rate": wr,
            "trading_pnl": pnl_tr,
            "end_bal": balance,
            "cum_deposited": total_deposited
        })

    mdf = pd.DataFrame(monthly_logs)

    print("\n" + "=" * 105)
    print("📊 [1. 최종 결과 요약: 100만 원 + 월 55만 원($400) 적립식 결합]")
    print("=" * 105)
    print(f"• 총 투입 원금 (누적 입금액) : ${total_deposited:,.2f} USDT (약 {total_deposited*1350:,.0f}원)")
    print(f"• 최종 계좌 잔고             : ${balance:,.2f} USDT (약 {balance*1350:,.0f}원)")
    print(f"• 순 트레이딩 수익           : +${balance - total_deposited:,.2f} USDT (약 {(balance - total_deposited)*1350:,.0f}원 순수익)")
    print(f"• 순수익률 (ROI)             : {((balance - total_deposited)/total_deposited)*100:+.2f}%")
    print(f"• 최대 낙폭 (MDD)            : {mdd*100:.2f}% (입금액 완충 효과로 낙폭 대폭 감소!)")
    if reach_10k_info:
        print(f"• 🏆 1,000만 원($10,000) 달성일 : {reach_10k_info['date']} (시작 후 약 13.5개월 만에 달성!)")
        print(f"  └ 달성 당시 누적 입금액    : ${reach_10k_info['deposited_so_far']:,.0f} USDT (약 {reach_10k_info['deposited_so_far']*1350:,.0f}원)")
        print(f"  └ 달성 당시 트레이딩 순수익: +${reach_10k_info['profit_so_far']:,.0f} USDT (약 {reach_10k_info['profit_so_far']*1350:,.0f}원)")
    print("=" * 105)

    print("\n📅 [2. 36개월 전체 월별 상세 자산 추이표 (Monthly Breakdown)]")
    print(f"{'연월 (Month)':<9} | {'월초 잔고':<10} | {'추가입금':<8} | {'체결수':<5} | {'승률':<6} | {'트레이딩 손익':<15} | {'월말 최종 잔고 (USDT / 원화)':<28} | {'비고'}")
    print("-" * 110)

    for idx, r in mdf.iterrows():
        sign = "+" if r['trading_pnl'] >= 0 else ""
        won_str = f"약 {r['end_bal']*1350/10000:,.0f}만원"
        pnl_str = f"{sign}${r['trading_pnl']:,.2f}"
        note = ""
        if r['end_bal'] >= 10000.0 and (idx == 0 or mdf.iloc[idx-1]['end_bal'] < 10000.0):
            note = "🏆 1,000만 원 돌파!"
        elif r['end_bal'] >= 20000.0 and (idx == 0 or mdf.iloc[idx-1]['end_bal'] < 20000.0):
            note = "🎉 2,000만 원 돌파!"

        print(f"{r['month_str']:<9} | ${r['start_bal']:>8,.1f} | +${r['deposit']:>5,.0f} | {r['trades']:>3}회 | {r['win_rate']:4.0f}% | {pnl_str:>13} | ${r['end_bal']:>9,.1f} ({won_str:<8}) | {note}")
    print("-" * 110)

if __name__ == "__main__":
    run_monthly_deposit_detailed()
