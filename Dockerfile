# Python 3.11 Slim 경량 베이스 이미지
FROM python:3.11-slim

# 표준 출력 버퍼링 비활성화 및 서울 표준시(KST) 설정
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Seoul

WORKDIR /app

# 기본 유틸리티 및 타임존 데이터 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    curl \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 파이썬 의존성 패키지 캐시 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 소스 코드 복사
COPY . .

# 봇 실행 명령 (unbuffered stdout)
CMD ["python", "-u", "bot.py"]
