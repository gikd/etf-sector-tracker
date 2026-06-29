# 글로벌 섹터 ETF 자금 흐름 트래커

글로벌 섹터·지역·테마 ETF 30종의 시세를 매일 수집해, **어느 섹터로 돈이 몰리는지**를 한눈에 보여주는 정적 대시보드.

## 작동 방식

```
fetch_data.py ──┬─ Yahoo Finance (1년치 일봉, OHLCV) ──▶ docs/data.json ──▶ docs/index.html (정적 대시보드)
                └─ Google News RSS (섹터별 최근 7일 한국어 뉴스)
```

- **자금 유입 추정 방식**: 실제 펀드 설정/환매 데이터는 무료 API가 없으므로,
  ① 기간별 수익률(모멘텀) ② 거래대금 급증률(5일 평균 ÷ 20일 평균)을 프록시로 사용.
  "ACWI 대비 초과수익 + 거래대금 증가" 조합을 자금 유입 시그널로 표시.
- **대시보드 구성**: finviz 스타일 성과 바차트, 누적 수익률 트렌드 라인차트(1M/3M/6M),
  히트맵 카드, 비교표. 어디든 클릭하면 일봉 캔들차트(거래량 포함) + **대표 구성종목**(일간 등락순) + 관련 뉴스 모달이 열림.
- **대표 종목**: ETF별 주요 종목 5~6개를 `CONSTITUENTS`에 정의해 시세를 함께 수집(중복 자동 제거).
  한국 종목(.KS)은 원화(₩), 그 외는 달러($)로 표시.
- 의존성 없음 (Python 표준 라이브러리만 사용), API 키 불필요.
- 뉴스 검색어는 `fetch_data.py`의 `TICKERS` 4번째 필드에서 종목별로 조정 가능.

## 로컬 실행

```bash
python3 fetch_data.py          # docs/data.json 생성
python3 -m http.server -d docs # http://localhost:8000 접속
```

## 배포 (GitHub Pages + 일일 자동 갱신)

1. GitHub 저장소 생성 후 푸시
2. Settings → Pages → Source를 `main` 브랜치 `/docs` 폴더로 설정
3. `.github/workflows/update.yml`이 평일 22:30 UTC(한국 오전 7:30, 미국 장 마감 후)에
   자동으로 데이터를 갱신·커밋함

## 글로벌 메가캡 (megacap.html)

전 세계 시총 최상위 300종목을 직접 섹터 분류(13개)해, **섹터 강세 순위 + 섹터별 모멘텀 리더**를 봄.
"자금 쏠림 → 강한 섹터의 강한 종목"을 포착하는 관측 도구. 기간(1주~YTD) 전환, 52주 신고가·저유동 배지.

**2단 갱신 구조**:
- **시세(매일)**: `fetch_megacap.py` — 명단을 읽어 가격·모멘텀만 일단위 갱신 (무인증 차트 API)
- **명단(주 1회)**: `fetch_universe.py` — 후보군(~360) 시총을 Yahoo crumb 인증으로 받아 USD 환산·랭킹 → TOP300 → `megacap_universe.json`. 일요일 `universe.yml` 워크플로로 갱신.
  후보군/섹터 분류는 `fetch_universe.py`의 `CANDIDATES`에서 편집.

## 구성 변경

추적할 ETF는 `fetch_data.py`의 `TICKERS` 목록에서 추가/삭제하면 됨 (티커, 한글명, 그룹).
상대강도 기준 지수는 `BENCHMARK` 변수로 변경.
