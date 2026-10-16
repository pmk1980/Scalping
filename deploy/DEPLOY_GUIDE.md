# ☁️ Bitget 퀀트 봇 클라우드 서버 24/7 무중단 배포 가이드

본 문서는 AWS Lightsail, Vultr, Oracle Cloud, Naver Cloud 등 리눅스(Ubuntu) 클라우드 인스턴스에서 퀀트 봇을 24시간 365일 안전하게 무중단 구동하기 위한 가이드입니다.

---

## 📌 추천 클라우드 VPS 사양

- **운영체제**: Ubuntu 22.04 LTS 또는 Ubuntu 24.04 LTS
- **사양**: 최소 1 vCPU / 1GB RAM (월 $3.5 ~ $5 내외 저가형 서버로 충분)
  - **추천 1**: [AWS Lightsail](https://aws.amazon.com/ko/lightsail/) (월 $3.5, 도쿄/서울 리전, 가장 안정적)
  - **추천 2**: [Vultr](https://www.vultr.com/) (월 $3.5, 서울 리전 지원)
  - **추천 3**: [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/) (평생 무료 인스턴스)

---

## 🚀 1단계: 서버에 코드 배포하기

### 방법 A: Git을 사용하는 경우 (권장)
GitHub 레포지토리에 푸시한 후 서버에서 복제합니다:
```bash
git clone https://github.com/your-repo/Scalping.git
cd Scalping
```

### 방법 B: SCP/SFTP로 로컬 파일 직접 전송하는 경우
로컬 Windows 파워쉘에서 서버 IP로 파일을 복사합니다:
```powershell
scp -r C:\appl\Scalping ubuntu@<서버_공인_IP>:/home/ubuntu/
```

---

## ⚙️ 2단계: 환경 설정 (.env)

서버의 프로젝트 폴더로 이동하여 `.env` 파일을 작성합니다:
```bash
cd Scalping
cp .env.example .env
nano .env
```
필수 설정값:
```env
BITGET_API_KEY=비트겟_API_KEY
BITGET_API_SECRET=비트겟_SECRET
BITGET_PASSPHRASE=비트겟_PASSPHRASE

# 처음에는 모의투자 검증: True / 실계좌 실거래: False
DRY_RUN=False

STRATEGY_MODE=DONCHIAN_4H
SYMBOL=BTC/USDT:USDT
TIMEFRAME=4h
LEVERAGE=2

# [선택] 텔레그램 스마트폰 알림 (강력 추천)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_CHAT_ID=123456789
```

> 💡 **텔레그램 알림 설정 1분 팁**:
> 1. 텔레그램에서 `@BotFather`를 검색하고 `/newbot`을 입력하여 봇을 만듭니다. (토큰 획득)
> 2. 생성된 봇을 찾아 시작(`/start`)을 누릅니다.
> 3. `@userinfobot`을 검색해 `/start`를 누르면 내 고유 `Id` (Chat ID)를 알려줍니다.
> 4. 위 두 값을 `.env`에 입력하면 포지션 진입/청산/수익률이 스마트폰으로 즉시 날아옵니다!

---

## 🐳 3단계: 24/7 무중단 구동 (가장 추천: Docker)

서버 자동 세팅 스크립트를 실행하여 Docker 환경을 원클릭으로 구축합니다:
```bash
chmod +x deploy/setup_server.sh
./deploy/setup_server.sh
```

### 1) 백그라운드 무중단 실행
```bash
sudo docker compose up -d --build
```
- 서버가 재부팅되거나 일시적인 네트워크 순단이 발생해도 `restart: unless-stopped` 정책에 의해 자동으로 봇이 되살아납니다.

### 2) 실시간 대시보드 로그 확인
```bash
sudo docker compose logs -f
```
*(터미널을 닫아도 서버 백그라운드에서는 봇이 정상 동작합니다. 로그 창에서 나가려면 `Ctrl + C`)*

### 3) 봇 중단
```bash
sudo docker compose down
```

---

## 🛠️ 대체 방법: Docker 없이 가상환경(tmux)으로 구동하기

Docker를 쓰지 않고 파이썬으로 직접 실행하려는 경우:

```bash
# 1. tmux 가상 세션 생성
tmux new -s quant

# 2. 가상환경 활성화 및 실행
source venv/bin/activate
python bot.py

# 3. 백그라운드로 나가기 (세션 유지)
# 키보드로 [Ctrl + B] 누른 후 손 떼고 [D] 키 입력

# 4. 나중에 다시 세션 접속하여 모니터링하기
tmux attach -t quant
```

---

## 🔒 4단계: 실계좌 보안 핵심 수칙 (필독)

1. **API Key IP 제한(IP Whitelisting)**:
   - 클라우드 서버의 고정 공인 IP(Static Elastic IP)를 확인합니다:
     ```bash
     curl ifconfig.me
     ```
   - 비트겟 거래소 API 관리 화면에서 해당 IP에서만 주문 요청을 허용하도록 설정하십시오. (해킹 위험 100% 차단)
2. **출금 권한 비활성화(No Withdrawal Permission)**:
   - 비트겟 API 발급 시 **[Trade (선물 거래)]** 권한만 체크하고, **[Withdraw (출금)]** 권한은 반드시 체크 해제하십시오.
