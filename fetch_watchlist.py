#!/usr/bin/env python3
"""구글시트 참고용 종목 워치리스트 — 글로벌 개별 종목 일봉 시세 보드 (트라이얼).

방산 테마(해외+국내)부터. docs/watchlist.json / watchlist.js 생성.
표준 라이브러리만 사용. 사용법: python3 fetch_watchlist.py
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

# 테마 → 그룹 → [(한글명, Yahoo심볼)]
WATCHLIST = {
    "방산": {
        "해외": [
            ("록히드마틴", "LMT"), ("보잉", "BA"), ("레이시온(RTX)", "RTX"),
            ("노스롭그루먼", "NOC"), ("제너럴다이내믹스", "GD"), ("헌팅턴잉걸스", "HII"),
            ("텍스트론", "TXT"), ("라인메탈", "RHM.DE"), ("에어버스", "AIR.PA"),
            ("BAE시스템즈", "BA.L"), ("탈레스", "HO.PA"), ("레오나르도", "LDO.MI"),
        ],
        "국내 대형": [
            ("한화에어로스페이스", "012450.KS"), ("LIG넥스원", "079550.KS"),
            ("한국항공우주(KAI)", "047810.KS"), ("한화시스템", "272210.KS"),
            ("현대로템", "064350.KS"), ("웨이브일렉트로", "095270.KS"),
        ],
        "국내 소형": [
            ("쎄트렉아이", "099320.KS"), ("빅텍", "065450.KS"), ("대양전기공업", "108380.KS"),
            ("이엠코리아", "095190.KS"), ("켄코아에어로스페이스", "274090.KS"),
            ("SNT다이내믹스", "003570.KS"), ("아이쓰리시스템", "214430.KS"),
            ("풍산", "103140.KS"), ("파이버프로", "368770.KS"),
        ],
    },
}

HIST_DAYS = 100
API = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=6mo&interval=1d"
OUT = Path(__file__).parent / "docs" / "watchlist.json"


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def pct(s, days):
    if len(s) <= days:
        return None
    base = s[-1 - days]
    return round((s[-1] / base - 1) * 100, 2) if base else None


def fetch(sym, retries=3):
    for attempt in range(retries):
        try:
            raw = json.loads(http_get(API.format(t=sym)))
            res = raw["chart"]["result"][0]
            meta = res["meta"]
            q = res["indicators"]["quote"][0]
            adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose", q["close"])
            close = [c for c in adj if c is not None]
            if len(close) < 5:
                return None
            return {
                "price": round(close[-1], 2),
                "ccy": meta.get("currency", "USD"),
                "r1d": pct(close, 1),
                "r1w": pct(close, 5),
                "r1m": pct(close, 21),
                "spark": [round(c, 2) for c in close[-HIST_DAYS:]],
            }
        except Exception as e:
            if attempt == retries - 1:
                print(f"  FAIL {sym}: {e}")
                return None
            time.sleep(1.5 * (attempt + 1))


def main():
    jobs = [(theme, grp, nm, sym)
            for theme, groups in WATCHLIST.items()
            for grp, names in groups.items()
            for nm, sym in names]
    print(f"종목 {len(jobs)}개 시세 수집 중...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        data = list(ex.map(lambda j: fetch(j[3]), jobs))

    themes, failed = {}, []
    for (theme, grp, nm, sym), d in zip(jobs, data):
        if d is None:
            failed.append(sym)
            continue
        themes.setdefault(theme, {}).setdefault(grp, []).append(
            {"name": nm, "ticker": sym, **d}
        )
    # 각 그룹 내 당일 등락순 정렬
    for groups in themes.values():
        for arr in groups.values():
            arr.sort(key=lambda x: x["r1d"] if x["r1d"] is not None else -999, reverse=True)

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "themes": themes,
    }
    payload = json.dumps(out, ensure_ascii=False)
    OUT.write_text(payload, encoding="utf-8")
    OUT.with_name("watchlist.js").write_text("window.__WATCHLIST__ = " + payload + ";", encoding="utf-8")
    ok = sum(len(a) for g in themes.values() for a in g.values())
    print(f"완료: {ok}개 저장 → {OUT}" + (f" (실패: {failed})" if failed else ""))


if __name__ == "__main__":
    main()
