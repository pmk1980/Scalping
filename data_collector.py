"""
하위 호환성을 위한 data_collector 프록시 모듈
핵심 구현은 src/data_collector.py에 위치합니다.
"""
from src.data_collector import fetch_historical_candles

__all__ = ["fetch_historical_candles"]

if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTC/USDT:USDT"
    tf = sys.argv[2] if len(sys.argv) > 2 else "4h"
    days = int(sys.argv[3]) if len(sys.argv) > 3 else 365
    fetch_historical_candles(symbol=symbol, timeframe=tf, days=days)
