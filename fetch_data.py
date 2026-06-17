#!/usr/bin/env python3
"""글로벌 섹터 ETF 일봉 시세 + 섹터 뉴스를 받아 docs/data.json 생성.

표준 라이브러리만 사용 (Yahoo Finance chart API + Google News RSS, 키 불필요).
사용법: python3 fetch_data.py
"""
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

# (티커, 한글명, 그룹, 뉴스 검색어 — 글로벌 영문 뉴스를 검색해 한국어로 번역)
TICKERS = [
    # 미국 11개 섹터 (SPDR)
    ("XLK",  "기술",          "us_sector", "technology sector stocks"),
    ("XLF",  "금융",          "us_sector", "bank financial sector stocks"),
    ("XLV",  "헬스케어",      "us_sector", "healthcare pharma stocks"),
    ("XLY",  "경기소비재",    "us_sector", "consumer discretionary retail stocks"),
    ("XLP",  "필수소비재",    "us_sector", "consumer staples stocks"),
    ("XLE",  "에너지",        "us_sector", "oil prices energy stocks"),
    ("XLI",  "산업재",        "us_sector", "industrial sector stocks"),
    ("XLB",  "소재",          "us_sector", "materials mining stocks"),
    ("XLU",  "유틸리티",      "us_sector", "utilities sector stocks"),
    ("XLRE", "부동산",        "us_sector", "real estate REIT market"),
    ("XLC",  "커뮤니케이션",  "us_sector", "big tech media communication stocks"),
    # 글로벌 지역
    ("SPY",  "미국 S&P500",   "region", "S&P 500 stock market"),
    ("ACWI", "전세계",        "region", "global stock markets"),
    ("EFA",  "선진국(ex-US)", "region", "international developed markets equities"),
    ("EEM",  "신흥국",        "region", "emerging markets equities"),
    ("VGK",  "유럽",          "region", "European stocks markets"),
    ("EWJ",  "일본",          "region", "Japan stocks Nikkei"),
    ("FXI",  "중국",          "region", "China stocks market"),
    ("EWY",  "한국",          "region", "South Korea stocks KOSPI"),
    ("INDA", "인도",          "region", "India stocks market"),
    # 테마
    ("SMH",  "반도체",        "theme", "semiconductor industry chips"),
    ("IGV",  "소프트웨어",    "theme", "software stocks"),
    ("IBB",  "바이오",        "theme", "biotech stocks"),
    ("ITA",  "방산/항공",     "theme", "defense aerospace stocks"),
    ("ICLN", "클린에너지",    "theme", "clean energy solar stocks"),
    ("GDX",  "금광",          "theme", "gold price gold miners"),
    ("URA",  "우라늄/원전",   "theme", "uranium nuclear energy stocks"),
    ("JETS", "항공/여행",     "theme", "airline travel stocks"),
    ("KWEB", "중국 인터넷",   "theme", "China internet tech stocks"),
    ("BOTZ", "로봇/AI",       "theme", "AI robotics stocks"),
]

BENCHMARK = "ACWI"  # 상대강도 기준
HIST_DAYS = 130     # 차트용 일봉 보관 일수 (약 6개월)
NEWS_PER_TICKER = 5
API = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=1y&interval=1d"
NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
TRANSLATE = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={q}"
OUT = Path(__file__).parent / "docs" / "data.json"


def http_get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_quotes(ticker: str, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        try:
            raw = json.loads(http_get(API.format(t=ticker)))
            result = raw["chart"]["result"][0]
            ts = result["timestamp"]
            q = result["indicators"]["quote"][0]
            adj = result["indicators"].get("adjclose", [{}])[0].get("adjclose", q["close"])
            rows = [
                (t, a, o, h, l, c, v)
                for t, a, o, h, l, c, v in zip(
                    ts, adj, q["open"], q["high"], q["low"], q["close"], q["volume"]
                )
                if a is not None and c is not None and v is not None
            ]
            return {
                "dates": [datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d") for t, *_ in rows],
                "adj": [r[1] for r in rows],
                "open": [r[2] for r in rows],
                "high": [r[3] for r in rows],
                "low": [r[4] for r in rows],
                "close": [r[5] for r in rows],
                "volume": [r[6] for r in rows],
            }
        except Exception as e:
            if attempt == retries - 1:
                print(f"  FAIL 시세 {ticker}: {e}")
                return None
            time.sleep(2 * (attempt + 1))


def fetch_news(query: str) -> list[dict]:
    """Google News RSS(미국판)에서 최근 7일 글로벌 뉴스 헤드라인 수집 (최신순)."""
    try:
        url = NEWS_RSS.format(q=urllib.parse.quote(f"{query} when:7d"))
        root = ET.fromstring(http_get(url))
        items = []
        for item in root.iter("item"):
            title = item.findtext("title") or ""
            src = item.findtext("source") or ""
            # 구글뉴스 제목 뒤의 " - 매체명" 꼬리 제거 (매체는 별도 표시)
            if src and title.endswith(f" - {src}"):
                title = title[: -len(f" - {src}")]
            link = item.findtext("link") or ""
            pub = item.findtext("pubDate") or ""
            try:
                dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z")
            except ValueError:
                dt = datetime.min
            items.append({"t": title, "u": link, "s": src, "d": dt.strftime("%m-%d"), "_dt": dt})
        items.sort(key=lambda x: x["_dt"], reverse=True)
        for it in items:
            del it["_dt"]
        return items[:NEWS_PER_TICKER]
    except Exception as e:
        print(f"  FAIL 뉴스 '{query}': {e}")
        return []


def translate_news(items: list[dict]) -> list[dict]:
    """헤드라인을 한국어로 번역. 원문은 ot 필드에 보존, 실패 시 원문 유지."""
    if not items:
        return items
    try:
        joined = "\n".join(it["t"] for it in items)
        raw = json.loads(http_get(TRANSLATE.format(q=urllib.parse.quote(joined))))
        full = "".join(seg[0] for seg in raw[0] if seg[0])
        lines = [ln.strip() for ln in full.split("\n")]
        if len(lines) != len(items):
            raise ValueError("번역 라인 수 불일치")
        for it, ko in zip(items, lines):
            it["ot"] = it["t"]
            it["t"] = ko
    except Exception as e:
        print(f"  FAIL 번역: {e} (원문 유지)")
    return items


def pct(series: list[float], days: int) -> float | None:
    if len(series) <= days:
        return None
    base = series[-1 - days]
    return round((series[-1] / base - 1) * 100, 2) if base else None


def ytd_pct(dates: list[str], close: list[float]) -> float | None:
    year = dates[-1][:4]
    prev = [c for d, c in zip(dates, close) if d[:4] < year]
    base = prev[-1] if prev else close[0]
    return round((close[-1] / base - 1) * 100, 2) if base else None


def build_metrics(data: dict) -> dict:
    adj, volume, dates = data["adj"], data["volume"], data["dates"]
    # 거래대금(가격×거래량) 5일/20일 평균 비율 → 자금 유입 프록시
    dollar = [c * v for c, v in zip(adj, volume)]
    vol_ratio = None
    if len(dollar) >= 20:
        avg5 = sum(dollar[-5:]) / 5
        avg20 = sum(dollar[-20:]) / 20
        vol_ratio = round(avg5 / avg20, 3) if avg20 else None
    high52 = max(adj)
    n = HIST_DAYS
    return {
        "price": round(adj[-1], 2),
        "r1d": pct(adj, 1),
        "r1w": pct(adj, 5),
        "r1m": pct(adj, 21),
        "r3m": pct(adj, 63),
        "ytd": ytd_pct(dates, adj),
        "vol_ratio": vol_ratio,
        "from_high": round((adj[-1] / high52 - 1) * 100, 2),
        "spark": [round(c, 2) for c in adj[-21:]],
        "hist": [round(c, 2) for c in adj[-n:]],       # 트렌드 차트용 (수정종가)
        "candles": {                                   # 일봉 차트용
            "o": [round(x, 2) for x in data["open"][-n:]],
            "h": [round(x, 2) for x in data["high"][-n:]],
            "l": [round(x, 2) for x in data["low"][-n:]],
            "c": [round(x, 2) for x in data["close"][-n:]],
            "v": volume[-n:],
        },
        "last_date": dates[-1],
    }


def main():
    print(f"{len(TICKERS)}개 ETF 시세 수집 중...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        quotes = list(ex.map(lambda t: (t, fetch_quotes(t[0])), TICKERS))
        print("섹터 뉴스 수집 중...")
        news = list(ex.map(lambda t: fetch_news(t[3]), TICKERS))
        print("뉴스 한국어 번역 중...")
        news = list(ex.map(translate_news, news))

    etfs, failed = [], []
    bench = None
    bench_dates = None
    for ((ticker, name, group, _), data), news_items in zip(quotes, news):
        if data is None:
            failed.append(ticker)
            continue
        m = build_metrics(data)
        m.update({"ticker": ticker, "name": name, "group": group, "news": news_items})
        etfs.append(m)
        if ticker == BENCHMARK:
            bench = m
            bench_dates = data["dates"][-HIST_DAYS:]

    # 벤치마크 대비 상대강도
    if bench:
        for e in etfs:
            for k in ("r1d", "r1w", "r1m", "r3m"):
                e["rel_" + k] = (
                    round(e[k] - bench[k], 2)
                    if e[k] is not None and bench[k] is not None
                    else None
                )

    if len(etfs) < len(TICKERS) * 0.8:
        # 대량 실패 시 기존 data.json을 덮어쓰지 않고 종료
        raise SystemExit(f"수집 실패가 너무 많음 (성공 {len(etfs)}/{len(TICKERS)}, 실패: {failed})")

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "benchmark": BENCHMARK,
        "dates": bench_dates,  # 차트 x축 라벨 (전 종목 공통, 미국 거래일 기준)
        "etfs": etfs,
    }
    payload = json.dumps(out, ensure_ascii=False)
    OUT.write_text(payload, encoding="utf-8")
    # file:// 로 index.html을 직접 열어도 동작하도록 스크립트 형태로도 저장
    OUT.with_name("data.js").write_text(
        "window.__ETF_DATA__ = " + payload + ";", encoding="utf-8"
    )
    size_kb = OUT.stat().st_size // 1024
    print(f"완료: {len(etfs)}개 저장 → {OUT} (+data.js, {size_kb}KB)" + (f" (실패: {failed})" if failed else ""))


if __name__ == "__main__":
    main()
