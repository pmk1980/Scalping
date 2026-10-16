#!/usr/bin/env bash
# ==============================================================================
# 🛡️ Bitget 퀀트 트레이딩 봇 클라우드 서버(Ubuntu/Debian) 자동 세팅 스크립트
# ==============================================================================

set -e

echo "=========================================================="
echo "🚀 [1/4] 서버 기본 패키지 업데이트 및 타임존(Asia/Seoul) 설정..."
echo "=========================================================="
sudo apt-get update -y
sudo apt-get install -y tzdata curl git htop tmux
sudo timedatectl set-timezone Asia/Seoul

echo "=========================================================="
echo "🐳 [2/4] Docker 및 Docker Compose 플러그인 설치..."
echo "=========================================================="
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm -f get-docker.sh
    echo "✅ Docker 설치 완료!"
else
    echo "✅ Docker가 이미 설치되어 있습니다."
fi

sudo apt-get install -y docker-compose-plugin || true

echo "=========================================================="
echo "🐍 [3/4] Python 가상환경(venv) 도구 설치 (Docker 미사용 옵션 대비)..."
echo "=========================================================="
sudo apt-get install -y python3 python3-pip python3-venv

if [ ! -d "venv" ]; then
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
    echo "✅ Python 가상환경(venv) 생성 및 패키지 설치 완료!"
fi

echo "=========================================================="
echo "✨ [4/4] 클라우드 세팅 완료!"
echo "=========================================================="
echo "📌 [실행 방법 A: Docker 백그라운드 24/7 구동 (가장 추천)]"
echo "   sudo docker compose up -d --build"
echo "   # 실시간 로그 확인: sudo docker compose logs -f"
echo "   # 중단: sudo docker compose down"
echo ""
echo "📌 [실행 방법 B: tmux 백그라운드 구동]"
echo "   tmux new -s quant"
echo "   source venv/bin/activate"
echo "   python bot.py"
echo "   # (나가기: Ctrl+B 누른 후 D)"
echo "   # (다시 접속: tmux attach -t quant)"
echo "=========================================================="
