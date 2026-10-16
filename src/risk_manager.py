import sys
import datetime
from typing import Dict, Any, Optional, Tuple

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

class RiskManager:
    """
    🛡️ 다중 서킷 브레이커 & 리스크 관리 엔진
    1. 월간 서킷 브레이커: 월 누적 손실 -15% 시 당월 거래 완전 차단 (원금 보호)
    2. 일일 서킷 브레이커: 일 누적 손실 -5% 시 당일 거래 즉시 셧다운
    3. 일일 최대 거래 횟수: 하루 최대 N회 진입 제한 (뇌동매매 방지)
    4. 3연속 손절 시 12시간 쿨다운 (계좌 보호 및 감정 배제)
    5. 트레일링 스탑 / 수익 보존 스탑(Profit Lock) 지원
    """
    def __init__(
        self,
        position_size_ratio: float = 0.50,
        daily_max_loss_ratio: float = -0.05,
        monthly_max_loss_ratio: float = -0.15,
        max_daily_trades: int = 4,
        max_consecutive_losses: int = 3,
        cooldown_minutes: int = 720,
        profit_lock_atr: float = 0.4,
        trailing_atr_mult: float = 1.5
    ):
        self.position_size_ratio = position_size_ratio
        self.daily_max_loss_ratio = daily_max_loss_ratio
        self.monthly_max_loss_ratio = monthly_max_loss_ratio
        self.max_daily_trades = max_daily_trades
        self.max_consecutive_losses = max_consecutive_losses
        self.cooldown_minutes = cooldown_minutes
        self.profit_lock_atr = profit_lock_atr
        self.trailing_atr_mult = trailing_atr_mult

        self.current_date = datetime.date.today()
        self.current_month = (self.current_date.year, self.current_date.month)

        self.initial_monthly_balance = 0.0
        self.current_monthly_pnl = 0.0

        self.initial_daily_balance = 0.0
        self.current_daily_pnl = 0.0
        self.daily_trade_count = 0

        self.consecutive_losses = 0
        self.cooldown_until: Optional[datetime.datetime] = None

        self.total_trades = 0
        self.win_trades = 0
        self.loss_trades = 0
        self.total_realized_pnl = 0.0

    def reset_stats_if_needed(self, current_balance: float):
        if current_balance <= 0:
            return

        today = datetime.date.today()
        month_tuple = (today.year, today.month)

        # 1. 월간 리셋
        if month_tuple != self.current_month or self.initial_monthly_balance <= 0.0:
            self.current_month = month_tuple
            self.initial_monthly_balance = current_balance
            self.current_monthly_pnl = 0.0
            print(f"📅 [RiskManager] 새 월 시작! 월간 기준 잔고: ${self.initial_monthly_balance:,.2f}")

        # 2. 일일 리셋
        if today != self.current_date or self.initial_daily_balance <= 0.0:
            self.current_date = today
            self.initial_daily_balance = current_balance
            self.current_daily_pnl = 0.0
            self.daily_trade_count = 0
            print(f"🔄 [RiskManager] 새 거래일 시작! 일일 기준 잔고: ${self.initial_daily_balance:,.2f}")

    def can_open_position(self, current_balance: float) -> Tuple[bool, str]:
        self.reset_stats_if_needed(current_balance)

        # 1. 월간 서킷 브레이커
        if self.initial_monthly_balance > 0:
            monthly_loss_pct = self.current_monthly_pnl / self.initial_monthly_balance
            if monthly_loss_pct <= self.monthly_max_loss_ratio:
                return False, f"🚨 [월간 서킷 브레이커] 월 누적 손실 {monthly_loss_pct*100:.2f}% 도달 -> 당월 신규 거래 완전 차단"

        # 2. 일일 서킷 브레이커
        if self.initial_daily_balance > 0:
            daily_loss_pct = self.current_daily_pnl / self.initial_daily_balance
            if daily_loss_pct <= self.daily_max_loss_ratio:
                return False, f"🚨 [일일 서킷 브레이커] 일일 누적 손실 {daily_loss_pct*100:.2f}% 도달 -> 당일 신규 거래 차단"

        # 3. 일일 최대 거래 횟수
        if self.daily_trade_count >= self.max_daily_trades:
            return False, f"🛑 일일 최대 거래 한도({self.max_daily_trades}회) 도달 -> 뇌동매매 방지 휴식"

        # 4. 연속 손실 쿨다운
        if self.cooldown_until and datetime.datetime.now() < self.cooldown_until:
            remain = int((self.cooldown_until - datetime.datetime.now()).total_seconds() / 60)
            return False, f"🛑 {self.max_consecutive_losses}연속 손절 쿨다운 중 ({remain}분 남음)"

        return True, "진입 가능"

    def record_entry(self):
        """신규 포지션 진입 시 일일 카운터 증가"""
        self.daily_trade_count += 1

    def record_trade_result(self, pnl: float, is_partial: bool = False):
        """거래 결과(손익) 기록 및 쿨다운 관리"""
        if not is_partial:
            self.total_trades += 1
            if pnl > 0:
                self.win_trades += 1
                self.consecutive_losses = 0
            else:
                self.loss_trades += 1
                self.consecutive_losses += 1
                if self.consecutive_losses >= self.max_consecutive_losses:
                    self.cooldown_until = datetime.datetime.now() + datetime.timedelta(minutes=self.cooldown_minutes)
                    print(f"🛑 [CoolDown] {self.max_consecutive_losses}연속 손절 발생 -> {self.cooldown_minutes//60}시간 쿨다운 진입")

        self.total_realized_pnl += pnl
        self.current_daily_pnl += pnl
        self.current_monthly_pnl += pnl

    def update_trailing_stop(self, position: Dict[str, Any], current_price: float) -> Optional[float]:
        if not position.get("tp1_hit", False):
            return None

        side = position["side"]
        atr = position.get("atr", 0.0)
        highest_p = max(position.get("highest_p", current_price), current_price)
        lowest_p = min(position.get("lowest_p", current_price), current_price)
        position["highest_p"] = highest_p
        position["lowest_p"] = lowest_p

        current_sl = position.get("stop_loss", 0.0)

        if side == "LONG":
            new_trail = highest_p - (atr * self.trailing_atr_mult)
            if new_trail > current_sl:
                position["stop_loss"] = new_trail
                return new_trail
        else:
            new_trail = lowest_p + (atr * self.trailing_atr_mult)
            if new_trail < current_sl:
                position["stop_loss"] = new_trail
                return new_trail

        return None

    def get_summary(self) -> Dict[str, Any]:
        win_rate = (self.win_trades / self.total_trades * 100) if self.total_trades > 0 else 0.0
        return {
            "total_trades": self.total_trades,
            "win_trades": self.win_trades,
            "loss_trades": self.loss_trades,
            "win_rate": f"{win_rate:.1f}%",
            "daily_trades": f"{self.daily_trade_count}/{self.max_daily_trades}",
            "daily_pnl": f"${self.current_daily_pnl:+.2f}",
            "monthly_pnl": f"${self.current_monthly_pnl:+.2f}",
            "total_pnl": f"${self.total_realized_pnl:+.2f}"
        }
