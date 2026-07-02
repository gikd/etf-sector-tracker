#!/usr/bin/env python3
"""[매일] 글로벌 메가캡 시세·모멘텀·뉴스 갱신 + 선행 PER 계산.

명단(TOP300)은 fetch_universe.py가 주 1회 만든 docs/megacap_universe.json 사용.
이 스크립트는 매일: 시세·일봉 캔들·한국어 뉴스 갱신, 명단의 EPS로 올해/내년 PER 계산.
docs/megacap.json / megacap.js 생성.
"""
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

HIST_DAYS = 130
NEWS_PER = 5
API = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=1y&interval=1d"
NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
TRANSLATE = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={q}"
DOCS = Path(__file__).parent / "docs"
UNIVERSE = DOCS / "megacap_universe.json"
OUT = DOCS / "megacap.json"


def load_members():
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
                "price": round(close[-1], 2),
                "ccy": meta.get("currency", "USD"),
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
                print(f"  FAIL 시세 {sym}: {e}")
                return None
            time.sleep(1.5 * (attempt + 1))


def news_query(member):
    """글로벌 뉴스 검색어 — 영문명 우선(콤마 앞), 없으면 티커(거래소 접미사 제거)."""
    en = member.get("enname")
    if en:
        return en.split(",")[0].strip()
    return member["ticker"].split(".")[0]


def fetch_news(query):
    """영문 글로벌 뉴스(최근 7일) — 글로벌 회사이므로 외국 뉴스 우선."""
    q = query.strip()
    try:
        url = NEWS_RSS.format(q=urllib.parse.quote(f"{q} when:7d"))
        root = ET.fromstring(http_get(url))
        items = []
        for it in root.iter("item"):
            title = it.findtext("title") or ""
            src = it.findtext("source") or ""
            if src and title.endswith(f" - {src}"):
                title = title[: -len(f" - {src}")]
            pub = it.findtext("pubDate") or ""
            try:
                dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z")
            except ValueError:
                dt = datetime.min
            items.append({"t": title, "u": it.findtext("link") or "", "s": src, "d": dt.strftime("%m-%d"), "_dt": dt})
        items.sort(key=lambda x: x["_dt"], reverse=True)
        for x in items:
            del x["_dt"]
        return items[:NEWS_PER]
    except Exception:
        return []


def translate_news(items):
    """영문 헤드라인을 한국어로 번역(원문은 ot 보존, 실패 시 영문 유지)."""
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
    except Exception:
        pass  # 실패 시 영문 원문 그대로
    return items


def fwd_pe(price, eps):
    return round(price / eps, 1) if price and eps and eps > 0 else None


def main():
    members, universe_updated = load_members()
    print(f"메가캡 {len(members)}개 시세·뉴스 수집 중... (명단 기준 {universe_updated or '폴백'})")
    with ThreadPoolExecutor(max_workers=6) as ex:
        quotes = list(ex.map(lambda m: fetch(m["ticker"]), members))
        news = list(ex.map(lambda m: fetch_news(news_query(m)), members))
        print("뉴스 한국어 번역 중...")
        news = list(ex.map(translate_news, news))

    stocks, failed = [], []
    for m, d, nw in zip(members, quotes, news):
        if d is None:
            failed.append(m["ticker"])
            continue
        item = {"name": m["name"], "ticker": m["ticker"], "sector": m["sector"], **d, "news": nw}
        if m.get("mcap_b") is not None:
            item["mcap_b"] = m["mcap_b"]
        if m.get("rank") is not None:
            item["rank"] = m["rank"]
        item["pe_now"] = fwd_pe(d["price"], m.get("eps_now"))
        item["pe_next"] = fwd_pe(d["price"], m.get("eps_next"))
        stocks.append(item)

    out = {
        "updated": datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"),
        "universe_updated": universe_updated,
        "count": len(stocks),
        "stocks": stocks,
    }
    payload = json.dumps(out, ensure_ascii=False)
    OUT.write_text(payload, encoding="utf-8")
    OUT.with_name("megacap.js").write_text("window.__MEGACAP__ = " + payload + ";", encoding="utf-8")
    size_kb = OUT.stat().st_size // 1024
    print(f"완료: {len(stocks)}개 저장 → {OUT} ({size_kb}KB)" + (f" (실패: {failed})" if failed else ""))


if __name__ == "__main__":
    main()
