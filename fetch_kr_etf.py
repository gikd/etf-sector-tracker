#!/usr/bin/env python3
"""[매일] 한국 상장 ETF 테마별 시세 수집 → docs/kr_etf.json.

핵심 태제 트래킹 페이지의 '한국 ETF 보기' 토글에서 사용. 종목(megacap)과 같은 형태로
저장해 같은 카드/모달 코드를 재사용한다(단 PER·뉴스 없음, ETF 플래그).
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

# (티커, ETF명, 테마)  — 테마는 태제/섹터 매칭 키
KR_ETFS = [
    ("091160.KS", "KODEX 반도체", "반도체"),
    ("396500.KS", "TIGER Fn반도체TOP10", "반도체"),
    ("139260.KS", "TIGER 200 IT", "반도체"),
    ("305720.KS", "KODEX 2차전지산업", "2차전지"),
    ("305540.KS", "TIGER 2차전지테마", "2차전지"),
    ("364980.KS", "TIGER 2차전지소재Fn", "2차전지"),
    ("091180.KS", "KODEX 자동차", "자동차"),
    ("091170.KS", "KODEX 은행", "금융"),
    ("091220.KS", "TIGER 은행", "금융"),
    ("266420.KS", "KODEX 헬스케어", "바이오"),
    ("244580.KS", "KODEX 바이오", "바이오"),
    ("449450.KS", "PLUS K방산", "방산"),
    ("463250.KS", "SOL K방산", "방산"),
    ("466920.KS", "SOL 조선TOP3플러스", "조선"),
    ("365040.KS", "KODEX 인터넷", "인터넷"),
    ("157500.KS", "TIGER 인터넷TOP10", "인터넷"),
    ("442320.KS", "HANARO 원자력iSelect", "원자력"),
    ("445290.KS", "KODEX K-로봇액티브", "로봇"),
    ("069500.KS", "KODEX 200", "시장"),
    ("229200.KS", "KODEX 코스닥150", "시장"),
    ("360750.KS", "TIGER 미국S&P500", "미국"),
    ("133690.KS", "TIGER 미국나스닥100", "미국"),
]

HIST_DAYS = 130
API = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=1y&interval=1d"
OUT = Path(__file__).parent / "docs" / "kr_etf.json"


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def pct(s, days):
    if len(s) <= days:
        return None
    base = s[-1 - days]
    return round((s[-1] / base - 1) * 100, 2) if base else None


def ytd_pct(dates, close):
    year = dates[-1][:4]
    prev = [c for d, c in zip(dates, close) if d[:4] < year]
    base = prev[-1] if prev else close[0]
    return round((close[-1] / base - 1) * 100, 2) if base else None


def fetch(row, retries=3):
    sym, name, theme = row
    for attempt in range(retries):
        try:
            raw = json.loads(http_get(API.format(t=sym)))
            res = raw["chart"]["result"][0]
            meta = res["meta"]
            ts = res["timestamp"]
            q = res["indicators"]["quote"][0]
            adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose", q["close"])
            rows = [
                (t, a, o, h, l, c, v)
                for t, a, o, h, l, c, v in zip(ts, adj, q["open"], q["high"], q["low"], q["close"], q["volume"])
                if a is not None and c is not None and v is not None
            ]
            if len(rows) < 30:
                return None
            dates = [datetime.fromtimestamp(r[0], tz=timezone.utc).strftime("%Y-%m-%d") for r in rows]
            close = [r[1] for r in rows]
            high = max(close)
            n = HIST_DAYS
            return {
                "ticker": sym, "name": name, "theme": theme, "is_etf": True,
                "price": round(close[-1], 2), "ccy": meta.get("currency", "KRW"),
                "r1d": pct(close, 1), "r1w": pct(close, 5), "r1m": pct(close, 21),
                "r3m": pct(close, 63), "ytd": ytd_pct(dates, close),
                "from_high": round((close[-1] / high - 1) * 100, 2),
                "spark": [round(c, 2) for c in close[-21:]],
                "dates": dates[-n:],
                "candles": {
                    "o": [round(r[2], 2) for r in rows[-n:]],
                    "h": [round(r[3], 2) for r in rows[-n:]],
                    "l": [round(r[4], 2) for r in rows[-n:]],
                    "c": [round(r[5], 2) for r in rows[-n:]],
                    "v": [r[6] for r in rows[-n:]],
                },
            }
        except Exception as e:
            if attempt == retries - 1:
                print(f"  FAIL {sym}: {e}")
                return None
            time.sleep(1.5 * (attempt + 1))


def main():
    print(f"한국 ETF {len(KR_ETFS)}개 시세 수집 중...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(fetch, KR_ETFS))
    etfs = [r for r in results if r is not None]
    failed = [k[0] for k, r in zip(KR_ETFS, results) if r is None]
    out = {"updated": datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"), "etfs": etfs}
    payload = json.dumps(out, ensure_ascii=False)
    OUT.write_text(payload, encoding="utf-8")
    print(f"완료: {len(etfs)}개 저장 → {OUT}" + (f" (실패: {failed})" if failed else ""))


if __name__ == "__main__":
    main()
