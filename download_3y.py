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

def download_3y_binance():
    os.makedirs("data", exist_ok=True)
    ex = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
    days = 1095
    start_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    since_ts = int(start_dt.timestamp() * 1000)
    end_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)

    for sym, save_sym in [("BTC/USDT", "BTC_USDT_USDT"), ("SOL/USDT", "SOL_USDT_USDT")]:
        csv_path = f"data/{save_sym}_1h_1095d.csv"
        print(f"📥 다운로드 시작: {sym} (Binance Futures, 3년치 1시간봉)...", flush=True)
        all_candles = []
        curr_since = since_ts
        batch = 0

        while curr_since < end_ts:
            try:
                candles = ex.fetch_ohlcv(sym, timeframe="1h", since=curr_since, limit=1000)
                if not candles:
                    break
                all_candles.extend(candles)
                batch += 1
                last_ts = candles[-1][0]
                if last_ts <= curr_since:
                    curr_since += 1000 * 3600 * 1000
                else:
                    curr_since = last_ts + 1
                time.sleep(0.05)
            except Exception as e:
                print(f"⚠️ 에러 발생: {e}, 1초 대기...", flush=True)
                time.sleep(1.0)

        df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df.drop_duplicates(subset=["timestamp"], inplace=True)
        df.sort_values(by="timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.to_csv(csv_path, index=False)
        print(f"✅ 저장 완료: {sym} -> 총 {len(df):,}개 캔들 ({df['datetime'].iloc[0]} ~ {df['datetime'].iloc[-1]})", flush=True)

if __name__ == "__main__":
    download_3y_binance()
