# 🛡️ Bitget 고도화 퀀트 선물 트레이딩 봇 (v3.0 Institutional)

비트겟(Bitget) 선물 시장에서 **"3년 실데이터(2023~2026) 전주기 검증", "4시간봉 200 EMA 거시 추세 필터(하락장 현금 100% 방어)", "20봉 Donchian 채널 돌파 & 중간선 칼손절(손익비 1:2.25)", "레버리지 2.0x 황금 비율 복리 운용"**을 통합 적용한 고성능 퀀트 트레이딩 시스템입니다.

---

## 🎯 100만 원 시작 ➡️ 2년 내 1억 원 달성 실전 마일스톤

| 단계 | 시기 | 운용 자본금 | 핵심 목표 및 액션 플랜 |
| :--- | :--- | :--- | :--- |
| **1단계: 실전 검증기** | 1~3개월차 | **100만 원** ($750) | • 비트겟 실계좌 API 연동 및 소액 실거래 가동<br>• Maker Post-Only 지정가 체결률 및 슬리피지 검증<br>• 1~3회 거시 추세 익절로 +15~20% 실계좌 수익 검증 |
| **2단계: 스케일업** | 4~12개월차 | **1,000만 원+** | • 수익성 확인 후 본격 시드 투입 (1,000만~2,000만 원)<br>• 2.0x 레버리지로 거시 상승 추세 탑승<br>• 매월 저축액(50~100만 원) 시드 부스팅 결합 |
| **3단계: 1억 원 돌파** | 13~24개월차 | **1억 원 목표** | • 복리 가속 구간 (원금 + 누적수익 + 월 저축)<br>• 24개월차 총 자산 1억 원 돌파 (Plan D 기준 2025.10 달성) |

---

## 📂 프로젝트 모듈 구조

```
c:\appl\Scalping\
├── src/                                  # 🚀 핵심 퀀트 트레이딩 엔진 패키지
│   ├── __init__.py
│   ├── config.py                         # 봇 전역 설정 Dataclass
│   ├── exchange.py                       # 비트겟 CCXT 연동 실행기 (Post-Only, 잔고/포지션)
│   ├── strategy.py                       # 4h 거시추세 전략(MacroDonchian) & 5m 스캘핑
│   ├── risk_manager.py                   # 다중 서킷 브레이커 & 쿨다운 엔진
│   └── data_collector.py                 # CCXT 과거 캔들 다운로더
│
├── research/                             # 📊 퀀트 리서치 & 백테스트 & 시뮬레이션
│   ├── roadmap_to_100m.py                # 🎯 100만원 -> 1억원 24개월 시뮬레이션
│   ├── compare_winrate_realities.py      # 🚨 유튜브 90% 승률 허구 vs 정통 퀀트 비교
│   ├── backtest_3y_regimes.py            # 🛡️ 3년 4대 국면(상승/횡보/하락) 스트레스 테스트
│   ├── detailed_3y_results.py            # 📈 36개월 월별 상세 PnL 및 성과 지표
│   ├── detailed_3y_results_monthly_deposit.py # 💰 월 55만 원 적립식 결합 36개월 리포트
│   ├── leverage_comparison_report.py     # ⚖️ 레버리지 1.5x~10x 리스크-수익 곡선
│   └── compound_strategy_optimizer.py    # ⚙️ 복리 최적화기
│
├── data/                                 # 💾 3년치 1시간봉 실제 체결 데이터 캐시 (Binance/Bitget)
│   ├── BTC_USDT_USDT_1h_1095d.csv
│   └── SOL_USDT_USDT_1h_1095d.csv
│
├── bot.py                                # ⚡ 실전/모의 자동매매 메인 실행기 (Rich 콘솔 대시보드)
├── config.py / strategy.py / ...         # 하위 호환 루트 프록시 모듈
├── .env / .env.example                   # API 키 및 런타임 환경설정
└── requirements.txt                      # 파이썬 의존성 패키지
```

---

## 🚀 빠른 시작 가이드

### 1. 모의 가상 매매 (DRY-RUN) 실행
실제 자금 투입 없이 실시간 비트겟 시세 및 호가창으로 전략을 실시간 감시합니다:
```powershell
python bot.py
```

### 2. 100만 원 ➡️ 1억 원 2년 로드맵 시뮬레이션 실행
```powershell
python research/roadmap_to_100m.py
```

### 3. 유튜브 90% 승률 허구 vs 퀀트 실증 비교 실행
```powershell
python research/compare_winrate_realities.py
```

### 4. 실계좌 실거래(Live Trading) 전환 방법
1. `.env` 파일에 비트겟 API 키 입력:
   ```env
   BITGET_API_KEY=your_api_key_here
   BITGET_API_SECRET=your_api_secret_here
   BITGET_PASSPHRASE=your_passphrase_here
   ```
2. 실거래 모드로 변경:
   ```env
   DRY_RUN=False
   ```
3. 봇 실행:
   ```powershell
   python bot.py
   ```

---

## ☁️ 클라우드 서버(AWS / Vultr / Oracle Cloud) 24/7 무중단 배포

원격 서버에서 봇을 24시간 365일 무중단으로 구동하고, 체결 내역을 스마트폰 텔레그램으로 실시간 전송받을 수 있습니다:

1. **Docker 컨테이너 무중단 구동 (가장 추천)**:
   ```bash
   sudo docker compose up -d --build
   ```
2. **실시간 로그 모니터링**:
   ```bash
   sudo docker compose logs -f
   ```
자세한 클라우드 세팅 방법과 텔레그램 알림 연동 가이드는 [deploy/DEPLOY_GUIDE.md](file:///c:/appl/Scalping/deploy/DEPLOY_GUIDE.md)를 참고하세요.

