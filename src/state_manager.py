import os
import json
from typing import Dict, Any, Optional

STATE_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bot_state.json")

class BotStateManager:
    """
    🛡️ 퀀트 봇 영속적 상태 저장소 (State Persistence Manager)
    - 도커 컨테이너/서버 재부팅 시에도 가상 잔고, 보유 포지션, 본전스탑 활성 여부,
      동일봉 중복진입 방지 시간을 100% 보존
    - Atomic write 방식을 사용하여 파일 손상 방지
    """
    def __init__(self, file_path: str = STATE_FILE_PATH):
        self.file_path = file_path
        self._ensure_dir()

    def _ensure_dir(self):
        d = os.path.dirname(self.file_path)
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)

    def load_state(self) -> Dict[str, Any]:
        if not os.path.exists(self.file_path):
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ [StateManager] 상태 파일 읽기 오류 ({e}) -> 초기 상태로 진행")
            return {}

    def save_state(self, state: Dict[str, Any]):
        self._ensure_dir()
        temp_file = self.file_path + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False, default=str)
            os.replace(temp_file, self.file_path)
        except Exception as e:
            print(f"⚠️ [StateManager] 상태 파일 저장 오류: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    def update_section(self, section: str, data: Dict[str, Any]):
        curr = self.load_state()
        if section not in curr or not isinstance(curr[section], dict):
            curr[section] = {}
        curr[section].update(data)
        self.save_state(curr)

    def get_section(self, section: str) -> Dict[str, Any]:
        curr = self.load_state()
        return curr.get(section, {})

# 전역 싱글톤 인스턴스
state_manager = BotStateManager()
