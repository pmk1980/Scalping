import sys
import time
from typing import Dict, Any, List, Optional, Tuple
import ccxt
import pandas as pd

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .config import BotConfig
from .state_manager import state_manager

class BitgetExchange:
    """
    고도화된 비트겟 선물 CCXT 연동 실행기
    - Maker(Post-Only) 지정가 우선 주문 (수수료 절감)
    - 다중 타임프레임(4h / 5m 등) 캔들 데이터 수집
    - 실시간 가상 매매(Dry-Run, 엄격한 증거금/수수료 시뮬레이션) 및 실계좌 실거래 완벽 지원
    """
    def __init__(self, config: BotConfig):
        self.config = config
        self.dry_run = config.dry_run
        
        exchange_params = {
            "apiKey": config.api_key,
            "secret": config.api_secret,
            "password": config.passphrase,
            "enableRateLimit": True,
            "options": {
                "defaultType": "swap",
                "createMarketBuyOrderRequiresPrice": False,
            }
        }
        self.client = ccxt.bitget(exchange_params)
        self.markets = None
        self.market_info = None

        # 가상 거래(Dry Run) 영속적 계좌 상태 로드 (기본 시드: $750 USDT)
        saved_account = state_manager.get_section("paper_account")
        self.paper_balance = float(saved_account.get("balance", 750.0))
        self.paper_position: Optional[Dict[str, Any]] = saved_account.get("position", None)
        if self.paper_position:
            print(f"🔄 [StateManager] 기존 가상 포지션 복원: {self.paper_position['side']} {self.paper_position.get('size')}개 @ ${self.paper_position.get('entry_price', 0):,.2f}")

    def initialize(self):
        print("🔗 [BitgetExchange] 비트겟 마켓 정보 동기화 중...")
        try:
            self.markets = self.client.load_markets()
            if self.config.symbol in self.markets:
                self.market_info = self.markets[self.config.symbol]
                print(f"✅ [BitgetExchange] 마켓 로드 성공: {self.config.symbol}")
            else:
                print(f"⚠️ [BitgetExchange] {self.config.symbol} 마켓 심볼 확인 필요")
        except Exception as e:
            print(f"⚠️ [BitgetExchange] 마켓 정보 로드 알림 (네트워크 확인): {e}")

        if not self.dry_run:
            try:
                print(f"⚙️ [BitgetExchange] 레버리지 {self.config.leverage}배 설정...")
                self.client.set_leverage(self.config.leverage, self.config.symbol)
            except Exception as e:
                print(f"ℹ️ 레버리지 설정 응답: {e}")

            try:
                print(f"⚙️ [BitgetExchange] 마진 모드({self.config.margin_mode}) 설정...")
                self.client.set_margin_mode(self.config.margin_mode.upper(), self.config.symbol)
            except Exception as e:
                print(f"ℹ️ 마진 모드 설정 응답: {e}")
        else:
            print(f"🧪 [Dry-Run] 실시간 가상 모의투자 모드 (가상 시드: ${self.paper_balance:,.2f} USDT / 약 100만 원)")

    def fetch_ohlcv(self, timeframe: Optional[str] = None, limit: int = 300) -> pd.DataFrame:
        tf = timeframe or self.config.timeframe
        raw = self.client.fetch_ohlcv(symbol=self.config.symbol, timeframe=tf, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df

    def fetch_orderbook_best_price(self) -> Tuple[float, float]:
        """호가창 최우선 매수(Best Bid) / 매도(Best Ask) 조회"""
        try:
            ob = self.client.fetch_order_book(self.config.symbol, limit=5)
            best_bid = float(ob["bids"][0][0]) if ob.get("bids") and len(ob["bids"]) > 0 else 0.0
            best_ask = float(ob["asks"][0][0]) if ob.get("asks") and len(ob["asks"]) > 0 else 0.0
            return best_bid, best_ask
        except Exception as e:
            curr = self.fetch_current_price()
            return curr, curr

    def fetch_current_price(self) -> float:
        ticker = self.client.fetch_ticker(self.config.symbol)
        return float(ticker["last"])

    def fetch_balance(self) -> float:
        if self.dry_run:
            equity = self.paper_balance
            if self.paper_position:
                curr_p = self.fetch_current_price()
                pos = self.paper_position
                side = pos["side"]
                unrealized = (curr_p - pos["entry_price"]) * pos["size"] if side == "LONG" else (pos["entry_price"] - curr_p) * pos["size"]
                equity += pos.get("margin", 0.0) + unrealized
            return float(equity)

        try:
            balance = self.client.fetch_balance(params={"type": "swap"})
            # 통일 swap 지갑 필드 파싱
            if "USDT" in balance:
                usdt_info = balance["USDT"]
                if isinstance(usdt_info, dict):
                    total = usdt_info.get("total") or usdt_info.get("free")
                    if total is not None:
                        return float(total)
            if "total" in balance and "USDT" in balance["total"]:
                return float(balance["total"]["USDT"])
            if "free" in balance and "USDT" in balance["free"]:
                return float(balance["free"]["USDT"])
            return 0.0
        except Exception as e:
            print(f"⚠️ [BitgetExchange] 잔고 조회 오류: {e}")
            return 0.0

    def fetch_open_position(self) -> Optional[Dict[str, Any]]:
        if self.dry_run:
            if not self.paper_position:
                return None
            pos = self.paper_position.copy()
            curr_p = self.fetch_current_price()
            side = pos["side"]
            pnl = (curr_p - pos["entry_price"]) * pos["size"] if side == "LONG" else (pos["entry_price"] - curr_p) * pos["size"]
            pos["unrealized_pnl"] = pnl
            margin = pos.get("margin", (pos["size"] * pos["entry_price"]) / self.config.leverage)
            pos["percentage"] = (pnl / margin * 100) if margin > 0 else 0.0
            return pos

        try:
            positions = self.client.fetch_positions([self.config.symbol])
            for pos in positions:
                size = float(pos.get("contracts", 0.0) or pos.get("size", 0.0) or 0.0)
                if size > 0:
                    raw_side = str(pos.get("side", "")).lower() or str(pos.get("holdSide", "")).lower()
                    side = "LONG" if ("long" in raw_side or "buy" in raw_side) else "SHORT"
                    return {
                        "side": side,
                        "size": size,
                        "entry_price": float(pos.get("entryPrice", 0.0)),
                        "unrealized_pnl": float(pos.get("unrealizedPnl", 0.0) or 0.0),
                        "percentage": float(pos.get("percentage", 0.0) or 0.0)
                    }
        except Exception as e:
            print(f"⚠️ [BitgetExchange] 포지션 조회 오류: {e}")
        return None

    def round_amount(self, amount: float) -> float:
        try:
            if self.client and hasattr(self.client, "amount_to_precision"):
                return float(self.client.amount_to_precision(self.config.symbol, amount))
        except Exception:
            pass
        if self.market_info and "precision" in self.market_info:
            prec = self.market_info["precision"].get("amount")
            if prec is not None:
                amount = round(amount, int(prec))
        if self.market_info and "limits" in self.market_info:
            min_a = self.market_info["limits"].get("amount", {}).get("min", 0.0001)
            if amount < min_a:
                amount = min_a
        return amount

    def update_paper_position_stop(self, sl: float):
        """가상 포지션의 추종 스탑선 갱신 및 파일 영속화"""
        if self.dry_run and self.paper_position:
            if sl > self.paper_position.get("stop_loss", 0.0):
                self.paper_position["stop_loss"] = sl
                state_manager.update_section("paper_account", {
                    "balance": self.paper_balance,
                    "position": self.paper_position
                })

    def open_position(
        self,
        side: str,
        amount: float,
        current_price: float,
        sl: float,
        tp1: float = 0.0,
        atr: float = 0.0
    ) -> bool:
        """
        포지션 오픈 (Post-Only 지정가 우선 주문 + 중복 방지 가드)
        """
        amount = self.round_amount(amount)
        best_bid, best_ask = self.fetch_orderbook_best_price()
        order_price = best_bid if side == "BUY" else best_ask
        if order_price <= 0:
            order_price = current_price

        print(f"🚀 [Post-Only 진입] {side} {amount} {self.config.symbol} @ ${order_price:,.2f} (스탑로스: ${sl:,.2f})")

        if self.dry_run:
            margin = (amount * order_price) / self.config.leverage
            fee = (amount * order_price) * self.config.maker_fee_rate # Maker 0.02%
            self.paper_balance -= (margin + fee)
            self.paper_position = {
                "side": "LONG" if side == "BUY" else "SHORT",
                "size": amount,
                "initial_size": amount,
                "entry_price": order_price,
                "margin": margin,
                "stop_loss": sl,
                "take_profit_1": tp1,
                "atr": atr,
                "tp1_hit": False,
                "highest_p": order_price,
                "lowest_p": order_price,
                "entry_fee": fee
            }
            # 영속적 상태 저장
            state_manager.update_section("paper_account", {
                "balance": self.paper_balance,
                "position": self.paper_position
            })
            print(f"🧪 [Dry-Run] 체결 완료 | 투입 증거금: ${margin:.2f} | 수수료: ${fee:.4f} | 가용 잔고: ${self.paper_balance:,.2f}")
            return True

        # 실거래 모드 (Post-Only 지정가 발주 + 중복 누적 방지 가드)
        try:
            # 1. 기존 미체결 주문 검사 및 안전 정리 (중복 주문 방지)
            try:
                open_orders = self.client.fetch_open_orders(self.config.symbol)
                if open_orders:
                    print(f"⚠️ [Order Guard] 기존 미체결 주문 {len(open_orders)}건 발견 -> 전량 취소 후 재발주")
                    for o in open_orders:
                        self.client.cancel_order(o["id"], self.config.symbol)
            except Exception as e_clean:
                print(f"ℹ️ 미체결 정리 알림: {e_clean}")

            # 2. 주문 발주
            order_side = "buy" if side == "BUY" else "sell"
            params = {"postOnly": True}
            try:
                order = self.client.create_limit_order(
                    symbol=self.config.symbol,
                    side=order_side,
                    amount=amount,
                    price=order_price,
                    params=params
                )
            except Exception as e_post:
                print(f"⚠️ [Post-Only 거부]: {e_post} -> 일반 지정가 주문으로 전환 발주")
                order = self.client.create_limit_order(
                    symbol=self.config.symbol,
                    side=order_side,
                    amount=amount,
                    price=order_price
                )

            order_id = order.get("id")
            print(f"✅ [Live Order] 지정가 주문 접수 완료: ID {order_id} -> 체결 대기(최대 10초)...")

            # 3. 체결 대기 루프 (미체결 방치로 인한 주문 누적 원천 방지)
            filled = False
            for _ in range(5):
                time.sleep(2)
                try:
                    check_o = self.client.fetch_order(order_id, self.config.symbol)
                    status = check_o.get("status")
                    if status == "closed":
                        filled = True
                        print(f"🎯 [Order Filled] 주문 ID {order_id} 체결 완료!")
                        break
                    elif status == "canceled":
                        print(f"🛑 [Order Canceled] 주문 ID {order_id} 취소됨")
                        break
                except Exception:
                    pass

            # 10초 내 미체결 시 취소 처리하여 다음 기회 대기
            if not filled:
                try:
                    self.client.cancel_order(order_id, self.config.symbol)
                    print(f"⏳ [Order Timeout] 10초 내 미체결로 주문 ID {order_id} 안전 취소 (주문 누적 방지)")
                except Exception:
                    pass
                return False

            return True

        except Exception as e:
            print(f"❌ [Order Error] 주문 발주 실패: {e}")
            return False

    def close_position(self, current_price: float, reason: str = "SIGNAL") -> Optional[float]:
        """포지션 전량 청산 (Taker 시장가 또는 지정가)"""
        if self.dry_run:
            if not self.paper_position:
                return None
            pos = self.paper_position
            size = pos["size"]
            entry_p = pos["entry_price"]
            side = pos["side"]
            margin = pos.get("margin", (size * entry_p) / self.config.leverage)

            gross = (current_price - entry_p) * size if side == "LONG" else (entry_p - current_price) * size
            fee = (size * current_price) * self.config.taker_fee_rate # 청산 스탑은 보수적으로 Taker 계산
            net_pnl = gross - fee

            self.paper_balance += (margin + net_pnl)
            print(f"🎯 [Dry-Run 전량 청산] {side} ({reason}) @ ${current_price:,.2f} | 손익: {net_pnl:+,.2f} USDT | 총 잔고: ${self.paper_balance:,.2f}")
            self.paper_position = None
            # 영속적 상태 저장
            state_manager.update_section("paper_account", {
                "balance": self.paper_balance,
                "position": None
            })
            return net_pnl

        # 실거래 모드
        curr_pos = self.fetch_open_position()
        if not curr_pos:
            return None
        try:
            close_side = "sell" if curr_pos["side"] == "LONG" else "buy"
            order = self.client.create_market_order(
                symbol=self.config.symbol,
                side=close_side,
                amount=curr_pos["size"],
                params={"reduceOnly": True}
            )
            print(f"✅ [Live Full Close] 전량 청산 주문 체결: ID {order.get('id')} ({reason})")

            # 수수료 차감 정밀 net_pnl 산출
            gross_pnl = float(curr_pos.get("unrealized_pnl", 0.0))
            close_val = curr_pos["size"] * current_price
            fee = close_val * self.config.taker_fee_rate
            net_pnl = gross_pnl - fee
            return net_pnl
        except Exception as e:
            print(f"❌ [Close Error] 포지션 청산 오류: {e}")
            return None
        except Exception as e:
            print(f"❌ [Close Error] 포지션 청산 오류: {e}")
            return None
