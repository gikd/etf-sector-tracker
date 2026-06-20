#!/usr/bin/env python3
"""[매일] 글로벌 메가캡 시세·모멘텀 갱신.

명단(어떤 종목이 TOP100인지)은 fetch_universe.py가 주 1회 만든
docs/megacap_universe.json 을 읽어 사용. 이 스크립트는 시세만 일단위로 갱신.
docs/megacap.json / megacap.js 생성.
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HIST_DAYS = 100
API = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=1y&interval=1d"
DOCS = Path(__file__).parent / "docs"
UNIVERSE = DOCS / "megacap_universe.json"
OUT = DOCS / "megacap.json"


def load_members():
    """주간 명단을 읽음. 없으면 후보군 전체로 폴백."""
    if UNIVERSE.exists():
        u = json.loads(UNIVERSE.read_text(encoding="utf-8"))
        return u["members"], u.get("updated")
    print("  경고: megacap_universe.json 없음 → 후보군 전체 사용 (먼저 fetch_universe.py 실행 권장)")
    from fetch_universe import CANDIDATES
    return [{"name": n, "ticker": t, "sector": s} for n, t, s in CANDIDATES], None


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


def fetch(sym, retries=3):
    for attempt in range(retries):
        try:
            raw = json.loads(http_get(API.format(t=sym)))
            res = raw["chart"]["result"][0]
            meta = res["meta"]
            ts = res["timestamp"]
            q = res["indicators"]["quote"][0]
            adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose", q["close"])
            rows = [(t, a) for t, a in zip(ts, adj) if a is not None]
            if len(rows) < 30:
                return None
            dates = [datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d") for t, _ in rows]
            close = [a for _, a in rows]
            high = max(close)
            return {
                "price": round(close[-1], 2),
                "ccy": meta.get("currency", "USD"),
                "r1w": pct(close, 5),
                "r1m": pct(close, 21),
                "r3m": pct(close, 63),
                "ytd": ytd_pct(dates, close),
                "from_high": round((close[-1] / high - 1) * 100, 2),
                "spark": [round(c, 2) for c in close[-HIST_DAYS:]],
            }
        except Exception as e:
            if attempt == retries - 1:
                print(f"  FAIL {sym}: {e}")
                return None
            time.sleep(1.5 * (attempt + 1))


def main():
    members, universe_updated = load_members()
    print(f"메가캡 {len(members)}개 시세 수집 중... (명단 기준 {universe_updated or '폴백'})")
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda m: fetch(m["ticker"]), members))

    stocks, failed = [], []
    for m, d in zip(members, results):
        if d is None:
            failed.append(m["ticker"])
            continue
        item = {"name": m["name"], "ticker": m["ticker"], "sector": m["sector"], **d}
        if m.get("mcap_b") is not None:
            item["mcap_b"] = m["mcap_b"]
        if m.get("rank") is not None:
            item["rank"] = m["rank"]
        stocks.append(item)

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "universe_updated": universe_updated,
        "count": len(stocks),
        "stocks": stocks,
    }
    payload = json.dumps(out, ensure_ascii=False)
    OUT.write_text(payload, encoding="utf-8")
    OUT.with_name("megacap.js").write_text("window.__MEGACAP__ = " + payload + ";", encoding="utf-8")
    print(f"완료: {len(stocks)}개 저장 → {OUT}" + (f" (실패: {failed})" if failed else ""))


if __name__ == "__main__":
    main()
