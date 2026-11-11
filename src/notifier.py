import os
import json
import urllib.request
import threading
from typing import Optional
from dotenv import load_dotenv

# .env 파일 로드
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

class TelegramNotifier:
    """
    텔레그램 스마트폰 실시간 알림 엔진 (비동기 스레드 전송 지원)
    - .env에 TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID가 설정되어 있으면 알림 전송
    - 미설정 시 오류 없이 조용히 통과(Graceful Skip)
    - 메인 루프 블로킹 방지를 위한 비동기 스레드(daemon=True) 발송
    """
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        enabled_env = os.getenv("TELEGRAM_ENABLED", "true").lower() in ("true", "1", "yes")
        self.is_enabled = bool(self.bot_token and self.chat_id and enabled_env)

    def _send_sync(self, text: str) -> bool:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        headers = {"Content-Type": "application/json"}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status == 200
        except Exception as e:
            # 타임아웃이나 네트워크 순단 시 조용히 스킵 (메인 루프 영향 차단)
            return False

    def send_message(self, text: str) -> bool:
        if not self.is_enabled:
            return False

        # 비동기 백그라운드 스레드로 발송하여 봇 메인 루프 지연 0초 달성
        t = threading.Thread(target=self._send_sync, args=(text,), daemon=True)
        t.start()
        return True

    def notify_startup(self, symbol: str, balance: float, mode: str, leverage: int):
        msg = (
            f"🚀 <b>[Bitget 퀀트 봇 클라우드 구동 시작]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• 실행 모드: <b>{mode}</b>\n"
            f"• 거래 종목: <code>{symbol}</code> (격리 {leverage}x)\n"
            f"• 시작 잔고: <b>${balance:,.2f} USDT</b> (약 {balance*1350:,.0f}원)\n"
            f"• 전략 엔진: 4시간봉 거시 추세 추종 (v3.0)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"클라우드 24/7 무중단 감시 중입니다."
        )
        self.send_message(msg)

    def notify_entry(self, symbol: str, side: str, price: float, amount: float, sl: float, margin: float):
        msg = (
            f"🟢 <b>[신규 포지션 진입 체결]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• 심볼/방향: <code>{symbol}</code> <b>{side}</b>\n"
            f"• 진입 가격: <b>${price:,.2f}</b>\n"
            f"• 주문 수량: <code>{amount}</code> (증거금 ${margin:.2f})\n"
            f"• 스탑로스  : <b>${sl:,.2f}</b> (채널 중간선)\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        self.send_message(msg)

    def notify_exit(self, symbol: str, side: str, exit_price: float, pnl: float, balance: float, reason: str):
        pnl_icon = "🎉" if pnl >= 0 else "🛑"
        msg = (
            f"{pnl_icon} <b>[포지션 전량 청산 완료]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• 종목/사유: <code>{symbol}</code> ({reason})\n"
            f"• 청산 가격: <b>${exit_price:,.2f}</b>\n"
            f"• 실현 손익: <b>{pnl:+,.2f} USDT</b> (약 {pnl*1350:+,.0f}원)\n"
            f"• 현재 잔고: <b>${balance:,.2f} USDT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        self.send_message(msg)

    def notify_circuit_breaker(self, reason: str):
        msg = (
            f"🚨 <b>[서킷 브레이커 발동 경보]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• 내용: {reason}\n"
            f"• 원금 보호를 위해 신규 거래를 일시 차단합니다.\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        self.send_message(msg)

# 싱글톤
notifier = TelegramNotifier()
