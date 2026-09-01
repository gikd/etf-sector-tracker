# 글로벌 메가캡 트래커

전 세계 시총 최상위 ~300종목을 직접 섹터 분류해, **어느 섹터로 돈이 쏠리는지 → 그 안에서 잘 가는 종목**을 보는 정적 대시보드. GitHub Pages + Actions 자동 갱신.

## 페이지 구성 (`docs/`)

| 페이지 | 내용 | 데이터 |
|---|---|---|
| **index.html** (홈·글로벌 메가캡) | 섹터 강세 순위 + 섹터별 모멘텀 리더. 기간(1주~YTD)·범위(TOP100/300) 전환. 카드 클릭 = 일봉 캔들 + 수익률 + 뉴스 모달. | `megacap.json` + `commentary.json` |
| **news.html** (뉴스플로우) | 시총 TOP300 종목 뉴스를 최신순 통합 피드로. 섹터(13)·종목 검색·TOP100/300 필터. | `megacap.json`(종목별 `news`) |

`megacap.html`은 옛 링크 보존용 `index.html` 리다이렉트 스텁.

## 데이터 파이프라인

```
fetch_universe.py ─▶ docs/megacap_universe.json  (시총 TOP300 명단, 주 1회)
fetch_megacap.py  ─▶ docs/megacap.json           (가격·모멘텀·PER·뉴스, 매일)
megacap-sector-commentary 스킬 ─▶ docs/commentary.json  (섹터 해석, 매일)
```

- **2단 갱신**: 명단(`fetch_universe.py`, 주 1회)과 시세(`fetch_megacap.py`, 매일)를 분리. 후보군·섹터 분류는 `fetch_universe.py`의 `CANDIDATES`에서 편집.
- **뉴스**: `fetch_megacap.py`가 종목별 Google News RSS(최근 7일)를 함께 수집해 `megacap.json`에 넣음. 뉴스플로우는 이걸 재사용(별도 파일 없음).
- 한국 종목(.KS)은 원화(₩), 그 외는 달러($) 등 현지 통화로 표시.
- 의존성 없음(Python 표준 라이브러리), API 키 불필요.

## 자동 갱신 (GitHub Actions)

- **`update.yml`** — 시세 갱신. `fetch_megacap.py` 실행 후 `megacap.json` 커밋(diff 가드: 실제 변경 시에만). 정시 실행은 Cloudflare Worker(`trigger/`)가 `workflow_dispatch`로 담당, GitHub 스케줄은 백업.
- **`universe.yml`** — 일요일 시총 TOP300 명단 재산정 → `megacap_universe.json`.

## 로컬 실행

```bash
python3 fetch_universe.py       # docs/megacap_universe.json (명단, 최초 1회)
python3 fetch_megacap.py        # docs/megacap.json (시세·뉴스)
python3 -m http.server -d docs  # http://localhost:8000
```
