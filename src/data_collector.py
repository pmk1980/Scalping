import os
import sys
import time
import datetime
import pandas as pd
import ccxt

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def fetch_historical_candles(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "4h",
    days: int = 365,
    output_dir: str = "data"
) -> str:
    """
    비트겟 선물(USDT-M)에서 지정한 일수(days)만큼의 과거 캔들 데이터를
    limit=1000 순방향 페이징으로 다운로드하여 CSV 파일로 저장합니다.
    """
    os.makedirs(output_dir, exist_ok=True)
    clean_sym = symbol.replace("/", "_").replace(":", "_")
    csv_path = os.path.join(output_dir, f"{clean_sym}_{timeframe}_{days}d.csv")

    if os.path.exists(csv_path):
        print(f"📦 이미 저장된 데이터가 존재합니다: {csv_path}")
        return csv_path

    print(f"==================================================")
    print(f"📥 [데이터 수집] 비트겟 과거 {days}일치 {timeframe} 캔들 다운로드")
    print(f"   심볼: {symbol}")
    print(f"==================================================")

    ex = ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    
    start_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    since_ts = int(start_dt.timestamp() * 1000)
    end_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)

    all_candles = []
    current_since = since_ts
    total_expected = (days * 24 * 60) // (240 if timeframe == "4h" else (60 if timeframe == "1h" else 5))

    print(f"⏳ 데이터 다운로드 시작 (시작: {start_dt.strftime('%Y-%m-%d %H:%M:%S UTC')})...")
    batch_count = 0

    while current_since < end_ts:
        try:
            candles = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=current_since, limit=1000)
            if not candles:
                break

            all_candles.extend(candles)
            batch_count += 1
            last_ts = candles[-1][0]
            
            if last_ts <= current_since:
                current_since += 1000 * 60 * (240 if timeframe == "4h" else 5)
            else:
                current_since = last_ts + 1

            current_dt_str = datetime.datetime.fromtimestamp(last_ts / 1000, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
            progress_pct = min(100.0, (len(all_candles) / max(1, total_expected)) * 100)
            
            if batch_count % 10 == 0 or current_since >= end_ts:
                print(f"   [진행률: {progress_pct:5.1f}%] 수집된 캔들: {len(all_candles):>7,}개 | 현재 시점: {current_dt_str}")

            time.sleep(0.08)
        except Exception as e:
            print(f"⚠️ 요청 중 일시적 오류: {e}, 2초 후 재시도...")
            time.sleep(2.0)

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df.drop_duplicates(subset=["timestamp"], inplace=True)
    df.sort_values(by="timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    
    df.to_csv(csv_path, index=False)
    print(f"✅ 저장 완료! 총 {len(df):,}개 캔들 -> {csv_path}")
    return csv_path

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTC/USDT:USDT"
    tf = sys.argv[2] if len(sys.argv) > 2 else "4h"
    days = int(sys.argv[3]) if len(sys.argv) > 3 else 365
    fetch_historical_candles(symbol=symbol, timeframe=tf, days=days)
