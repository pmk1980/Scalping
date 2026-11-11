import sys
import time
import datetime
from typing import Optional

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.config import config
from src.exchange import BitgetExchange
from src.strategy import MacroDonchianStrategy, MultiTimeframeStrategy, SignalType
from src.risk_manager import RiskManager
from src.notifier import notifier

console = Console()

class QuantTradingBot:
    """
    비트겟 선물 자동매매 퀀트 봇 실행 엔진 (v3.0)
    - 모드 1: DONCHIAN_4H (3년 실데이터 검증 거시 추세 추종 전략 - 권장)
    - 모드 2: SCALPING_5M (5분봉 단기 스캘핑 전략)
    """
    def __init__(self):
        self.config = config
        self.exchange = BitgetExchange(self.config)
        
        if self.config.strategy_mode == "DONCHIAN_4H":
            self.strategy = MacroDonchianStrategy(
                donchian_period=self.config.donchian_period,
                ema_period=self.config.macro_ema_period,
                use_break_even=self.config.use_break_even,
                break_even_trigger_ratio=self.config.break_even_trigger_ratio,
                use_volume_filter=self.config.use_volume_filter,
                volume_filter_ratio=self.config.volume_filter_ratio,
                max_rsi_entry=self.config.max_rsi_entry,
                min_adx_entry=self.config.min_adx_entry
            )
        else:
            self.strategy = MultiTimeframeStrategy()

        self.risk_manager = RiskManager(
            position_size_ratio=self.config.portfolio_allocation,
            daily_max_loss_ratio=self.config.daily_max_loss_ratio,
            monthly_max_loss_ratio=self.config.monthly_max_loss_ratio,
            max_daily_trades=self.config.max_daily_trades,
            max_consecutive_losses=self.config.max_consecutive_losses,
            cooldown_minutes=self.config.cooldown_hours * 60,
            trailing_atr_mult=self.config.atr_trailing_mult
        )
        self.is_running = False

    def print_banner(self):
        mode_text = "[bold yellow]🧪 DRY-RUN (가상 모의투자 모드)[/bold yellow]" if self.config.dry_run else "[bold red]⚡ LIVE (실계좌 실거래 모드)[/bold red]"
        strat_text = "[bold green]4시간봉 거시 추세 전략 (DONCHIAN_4H, 3년 검증)[/bold green]" if self.config.strategy_mode == "DONCHIAN_4H" else "[bold yellow]5분봉 스캘핑 (SCALPING_5M)[/bold yellow]"
        
        banner = Panel(
            f"""[bold cyan]Bitget 퀀트 선물 트레이딩 봇 (v3.1 보완판)[/bold cyan]
• 거래 대상   : [bold green]{self.config.symbol}[/bold green] (레버리지 [bold magenta]{self.config.leverage}x[/bold magenta] 격리마진)
• 타임프레임  : [bold white]{self.config.timeframe}[/bold white] (상위: {self.config.htf_timeframe})
• 전략 모드   : {strat_text}
• 실행 모드   : {mode_text}
• 주문 방식   : [bold green]Maker Post-Only (지정가 우선, 수수료 0.02% 최적화)[/bold green]
• 휩소/손실방어: [bold yellow]본전 스탑({self.config.break_even_trigger_ratio*100:+.1f}%) | 거래량 필터({self.config.volume_filter_ratio*100:.0f}%) | RSI 과열제한({self.config.max_rsi_entry:.0f})[/bold yellow]
• 자본 관리   : 1회 진입 [bold yellow]{self.config.portfolio_allocation*100:.0f}%[/bold yellow] | 일일 손실한도 {self.config.daily_max_loss_ratio*100:.1f}% | 월간 한도 {self.config.monthly_max_loss_ratio*100:.1f}%""",
            title="🛡️ Institutional Quant Engine v3.1",
            border_style="cyan"
        )
        console.print(banner)

    def print_status_table(
        self,
        current_price: float,
        balance: float,
        position: Optional[dict],
        last_reason: str
    ):
        table = Table(title="📊 실시간 퀀트 모니터링 대시보드", expand=False)
        table.add_column("구분", style="cyan", justify="left")
        table.add_column("상태값", style="white", justify="right")

        krw_balance = balance * 1350.0
        table.add_row("현재 시세", f"${current_price:,.2f}")
        table.add_row("계좌 잔고", f"${balance:,.2f} USDT (약 {krw_balance:,.0f}원)")
        table.add_row("전략 상태", f"[italic]{last_reason}[/italic]")

        # 리스크 매니저 현황
        summary = self.risk_manager.get_summary()
        table.add_row("일일 실현손익", summary["daily_pnl"])
        table.add_row("월간 실현손익", summary["monthly_pnl"])
        table.add_row("금일 거래횟수", summary["daily_trades"])

        if position:
            side_color = "green" if position["side"] == "LONG" else "red"
            entry_p = float(position.get("entry_price", current_price))
            sl = float(position.get("stop_loss", 0.0))
            pnl_pct = float(position.get("percentage", 0.0))
            unrealized_pnl = float(position.get("unrealized_pnl", 0.0))
            pnl_color = "bold green" if pnl_pct >= 0 else "bold red"

            be_active = getattr(self.strategy, "break_even_activated", False)
            sl_text = f"[bold yellow]${sl:,.2f} (본전이익보존 활성)[/bold yellow]" if be_active else f"[red]${sl:,.2f}[/red]"
            table.add_row("포지션 상태", f"[{side_color}]{position['side']} ({position.get('size', 0)} qty)[/{side_color}]")
            table.add_row("진입가 / 현재가", f"${entry_p:,.2f} / ${current_price:,.2f}")
            table.add_row("추종 스탑선", sl_text)
            table.add_row("미실현 손익", f"[{pnl_color}]{unrealized_pnl:+,.2f} USDT ({pnl_pct:+.2f}%)[/{pnl_color}]")
        else:
            table.add_row("포지션 상태", "[grey50]무포지션 (현금 100% 관망 및 진입 대기)[/grey50]")

        console.print(table)

    def start(self, max_iterations: Optional[int] = None):
        self.print_banner()
        self.exchange.initialize()
        
        current_balance = self.exchange.fetch_balance()
        self.risk_manager.reset_stats_if_needed(current_balance)
        self.is_running = True

        mode_str = "DRY-RUN (가상 모의투자)" if self.config.dry_run else "LIVE (실계좌 실거래)"
        notifier.notify_startup(
            symbol=self.config.symbol,
            balance=current_balance,
            mode=mode_str,
            leverage=self.config.leverage
        )

        console.print("\n🚀 [bold green]퀀트 자동매매 감시를 시작합니다. (중단: Ctrl+C)[/bold green]\n")

        iteration = 0
        last_reason = "시장 데이터 동기화 중..."

        while self.is_running:
            try:
                iteration += 1
                if max_iterations and iteration > max_iterations:
                    console.print(f"\n[bold green]테스트 완료 ({max_iterations}회 반복)[/bold green]")
                    break

                # 1. 시세 및 계좌 데이터 갱신
                df = self.exchange.fetch_ohlcv(timeframe=self.config.timeframe, limit=300)
                current_price = self.exchange.fetch_current_price()
                current_balance = self.exchange.fetch_balance()
                position = self.exchange.fetch_open_position()

                # 2. 4시간봉 거시 추세 전략 분석
                if self.config.strategy_mode == "DONCHIAN_4H":
                    analysis = self.strategy.analyze(df, current_position=position)
                    last_reason = analysis["reason"]

                    # 포지션 보유 중인 경우 대시보드 및 가상계좌 스탑선 실시간 동기화
                    if position is not None and "effective_stop" in analysis:
                        eff_sl = float(analysis["effective_stop"])
                        position["stop_loss"] = eff_sl
                        if hasattr(self.exchange, "update_paper_position_stop"):
                            self.exchange.update_paper_position_stop(eff_sl)

                    # 청산 신호 처리
                    if analysis["signal"] == SignalType.EXIT and position is not None:
                        exit_price = analysis.get("exit_price", current_price)
                        console.print(f"\n🔔 [bold yellow]청산 신호 발생: {last_reason}[/bold yellow]")
                        pnl = self.exchange.close_position(current_price=exit_price, reason=last_reason)
                        if pnl is not None:
                            self.risk_manager.record_trade_result(pnl)
                            notifier.notify_exit(
                                symbol=self.config.symbol,
                                side=position["side"],
                                exit_price=exit_price,
                                pnl=pnl,
                                balance=self.exchange.fetch_balance(),
                                reason=last_reason
                            )
                        position = None
                        if hasattr(self.strategy, "reset_position_tracker"):
                            self.strategy.reset_position_tracker()

                    # 신규 롱 진입 신호 처리
                    elif analysis["signal"] == SignalType.BUY and position is None:
                        can_open, risk_reason = self.risk_manager.can_open_position(current_balance)
                        if not can_open:
                            last_reason = f"진입 차단: {risk_reason}"
                            console.print(f"\n⚠️ [bold red]{last_reason}[/bold red]")
                            if "서킷 브레이커" in risk_reason:
                                notifier.notify_circuit_breaker(risk_reason)
                        else:
                            entry_price = analysis["entry_price"]
                            sl_price = analysis["stop_loss"]
                            margin = current_balance * self.config.portfolio_allocation
                            qty = (margin * self.config.leverage) / entry_price

                            console.print(f"\n🚀 [bold green]신규 롱 진입 신호 발생: {last_reason}[/bold green]")
                            success = self.exchange.open_position(
                                side="BUY",
                                amount=qty,
                                current_price=entry_price,
                                sl=sl_price,
                                tp1=0.0,
                                atr=0.0
                            )
                            if success:
                                self.risk_manager.record_entry()
                                if hasattr(self.strategy, "record_entry_state"):
                                    self.strategy.record_entry_state(analysis.get("bar_time"), entry_price)
                                elif hasattr(self.strategy, "last_entry_bar_time"):
                                    self.strategy.last_entry_bar_time = analysis.get("bar_time")
                                notifier.notify_entry(
                                    symbol=self.config.symbol,
                                    side="BUY",
                                    price=entry_price,
                                    amount=qty,
                                    sl=sl_price,
                                    margin=margin
                                )
                                position = self.exchange.fetch_open_position()

                # 3. 5분봉 스캘핑 모드 (하위 호환)
                elif self.config.strategy_mode == "SCALPING_5M":
                    htf_df = self.exchange.fetch_ohlcv(timeframe=self.config.htf_timeframe, limit=250)
                    analysis = self.strategy.analyze(df, htf_df)
                    last_reason = analysis["reason"]

                    if analysis["signal"] == SignalType.BUY and position is None:
                        can_open, risk_reason = self.risk_manager.can_open_position(current_balance)
                        if can_open:
                            entry_price = analysis["entry_price"]
                            sl_price = analysis["stop_loss"]
                            margin = current_balance * self.config.position_size_ratio
                            qty = (margin * self.config.leverage) / entry_price
                            success = self.exchange.open_position(
                                side="BUY",
                                amount=qty,
                                current_price=entry_price,
                                sl=sl_price,
                                tp1=analysis.get("take_profit_1", 0.0),
                                atr=0.0
                            )
                            if success:
                                self.risk_manager.record_entry()
                                position = self.exchange.fetch_open_position()

                # 대시보드 상태 출력
                self.print_status_table(current_price, current_balance, position, last_reason)

                if max_iterations and iteration >= max_iterations:
                    console.print(f"\n[bold green]테스트 완료 ({max_iterations}회 반복)[/bold green]")
                    break

                # 4시간봉 전략은 60초 간격 갱신 (서버 부하 및 API 호출 최소화)
                sleep_sec = 60 if self.config.strategy_mode == "DONCHIAN_4H" else 15
                time.sleep(sleep_sec)

            except KeyboardInterrupt:
                console.print("\n[bold red]사용자에 의해 봇 실행이 중단되었습니다.[/bold red]")
                self.is_running = False
                break
            except Exception as e:
                console.print(f"\n[bold red]루프 실행 중 예외 발생:[/bold red] {e}")
                time.sleep(5)

if __name__ == "__main__":
    bot = QuantTradingBot()
    bot.start()
