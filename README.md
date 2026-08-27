# 안될공학 Content Intelligence

YouTube Studio 콘텐츠 CSV를 브라우저 안에서 분석하는 정적 웹 대시보드입니다. 서버나 외부 저장소로 채널 데이터를 전송하지 않습니다.

## 실행

```bash
cd /Users/error/andol-lab
python3 server.py
```

브라우저에서 `http://localhost:4174`를 엽니다.

## 실제 데이터 사용

YouTube Studio의 **분석 → 고급 모드 → 콘텐츠**에서 CSV를 내려받아 `Studio CSV 가져오기`로 업로드합니다. 권장 열은 콘텐츠(또는 동영상 제목), 조회수, 노출수, 노출 클릭률, 평균 조회율, 구독자, 좋아요, 댓글, 게시 날짜입니다. 한글·영문 헤더를 모두 인식합니다.

경쟁력 점수는 채널 내부 중앙값에 대한 조회 성과(25%), CTR(25%), 평균 시청률(30%), 조회당 구독 전환(20%)으로 계산합니다. 서로 다른 길이와 포맷의 콘텐츠를 비교할 때는 절대 점수보다 같은 포맷 내 상대 순위를 함께 보세요.

## YouTube API 연결

Google Cloud Console에서 YouTube Data API v3와 YouTube Analytics API를 활성화하고 OAuth 2.0 웹 애플리케이션 클라이언트를 만듭니다. 승인된 리디렉션 URI에는 `http://localhost:4174/api/auth/callback`을 추가합니다.

```bash
export YOUTUBE_CLIENT_ID='발급받은-client-id'
export YOUTUBE_CLIENT_SECRET='발급받은-client-secret'
python3 server.py
```

또는 다운로드한 OAuth JSON의 이름을 `client_secret.json`으로 바꾸어 이 폴더에 넣으면 환경변수 없이 자동으로 읽습니다. 이 파일은 외부에 공유하거나 Git에 커밋하지 마세요.

현재 버전은 Data API 메타데이터와 Analytics API의 최근 90일 성과를 즉시 결합합니다. 노출·CTR의 장기 일별 축적은 Reporting API 수집 작업과 데이터베이스가 필요한 다음 단계 기능입니다.
