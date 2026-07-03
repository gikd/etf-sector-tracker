#!/usr/bin/env python3
"""[매일] 한국 상장 ETF 시세 수집 → docs/kr_etf.json.

명단은 네이버 금융 ETF 전종목(약 1,100+)에서 거래대금 상위 TOP_N 을 자동 선정
(+ 태제가 참조하는 ETF 는 거래대금과 무관하게 항상 포함). 종목(megacap)과 같은 형태로
저장해 핵심 태제 트래킹의 카드/모달 코드를 재사용한다(PER·뉴스 없음, is_etf 플래그).
네이버 실패 시 하드코딩 폴백 명단 사용.
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

TOP_N = 400
HIST_DAYS = 130
API = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=1y&interval=1d"
NAVER_ETF = "https://finance.naver.com/api/sise/etfItemList.nhn"
DOCS = Path(__file__).parent / "docs"
OUT = DOCS / "kr_etf.json"
THESES = DOCS / "theses.json"

# 네이버 실패 시 최소 폴백 (거래대금 상위 대표)
FALLBACK = [
    ("069500.KS", "KODEX 200"), ("360750.KS", "TIGER 미국S&P500"),
    ("133690.KS", "TIGER 미국나스닥100"), ("091160.KS", "KODEX 반도체"),
    ("305720.KS", "KODEX 2차전지산업"), ("365040.KS", "KODEX 인터넷"),
    ("449450.KS", "PLUS K방산"), ("229200.KS", "KODEX 코스닥150"),
]

# ETF명 → 테마(표시용 서브라벨). 구체적인 키워드를 앞에 둔다.
THEME_KW = [
    ("반도체", "반도체"), ("2차전지", "2차전지"), ("배터리", "2차전지"),
    ("방산", "방산"), ("우주", "방산"), ("조선", "조선"), ("원자력", "원자력"),
    ("바이오", "바이오"), ("헬스케어", "바이오"), ("제약", "바이오"),
    ("인터넷", "인터넷"), ("게임", "게임"), ("엔터", "엔터"), ("미디어", "미디어"),
    ("로봇", "로봇"), ("인공지능", "AI"), ("AI", "AI"),
    ("자동차", "자동차"), ("은행", "금융"), ("증권", "금융"), ("보험", "금융"), ("금융", "금융"),
    ("나스닥", "미국"), ("S&P", "미국"), ("필라델피아", "미국"), ("미국", "미국"),
    ("차이나", "중국"), ("중국", "중국"), ("항셍", "중국"), ("일본", "일본"), ("인도", "인도"),
    ("베트남", "베트남"), ("유럽", "유럽"), ("선진국", "해외"), ("신흥국", "해외"),
    ("리츠", "리츠"), ("부동산", "리츠"),
    ("고배당", "배당"), ("배당", "배당"),
    ("국고채", "채권"), ("국채", "채권"), ("회사채", "채권"), ("채권", "채권"), ("금리", "채권"),
    ("골드", "원자재"), ("원유", "원자재"), ("구리", "원자재"), ("원자재", "원자재"),
    ("코스닥", "시장"), ("코스피", "시장"), ("KRX", "시장"),
    ("성장", "팩터"), ("가치", "팩터"), ("모멘텀", "팩터"), ("퀄리티", "팩터"), ("로우볼", "팩터"),
    ("배당성장", "배당"), ("TOP", "테마"),
]


def theme_for(name):
    for kw, th in THEME_KW:
        if kw in name:
            return th
    return ""


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def thesis_kr_tickers():
    """태제가 참조하는 KR ETF 티커 — 항상 명단에 포함(거래대금 낮아도 카드가 떠야 함)."""
    try:
        d = json.loads(THESES.read_text(encoding="utf-8"))
        s = set()
        for w in d.get("weeks", []):
            for t in w.get("theses", []):
                s.update(t.get("kr", []))
        return {c.split(".")[0] for c in s}
    except Exception:
        return set()


def get_universe():
    """네이버 ETF 전종목 → 거래대금 상위 TOP_N + 태제 참조분. [(sym.KS, name, theme, 거래대금)]."""
    try:
        req = urllib.request.Request(
            NAVER_ETF, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/sise/etf.naver"})
        raw = urllib.request.urlopen(req, timeout=20).read()
        items = json.loads(raw.decode("euc-kr", "replace")).get("result", {}).get("etfItemList", [])
        items = [x for x in items if x.get("itemcode")]
        if not items:
            raise ValueError("빈 목록")
        code_map = {x["itemcode"]: x for x in items}
        items.sort(key=lambda x: (x.get("amonut") or 0), reverse=True)
        picked = {x["itemcode"]: x for x in items[:TOP_N]}
        for code in thesis_kr_tickers():          # 태제 참조 ETF 강제 포함
            if code not in picked and code in code_map:
                picked[code] = code_map[code]
        print(f"네이버 ETF {len(items)}개 중 거래대금 상위 {TOP_N} + 태제참조 → 명단 {len(picked)}개")
        return [(f'{c}.KS', x["itemname"], theme_for(x["itemname"]), (x.get("amonut") or 0)) for c, x in picked.items()]
    except Exception as e:
        print(f"  네이버 목록 실패({e}) → 폴백 명단 {len(FALLBACK)}개 사용")
        return [(sym, name, theme_for(name), 0) for sym, name in FALLBACK]


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
    sym, name, theme, amt = row
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
                "amt": amt,  # 거래대금(백만원, 네이버) — 관련 ETF 랭킹용
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
    universe = get_universe()
    print(f"한국 ETF {len(universe)}개 시세 수집 중...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(fetch, universe))
    etfs = [r for r in results if r is not None]
    etfs.sort(key=lambda e: e["ticker"])
    failed = len(universe) - len(etfs)
    out = {"updated": datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"),
           "count": len(etfs), "etfs": etfs}
    payload = json.dumps(out, ensure_ascii=False)
    OUT.write_text(payload, encoding="utf-8")
    size_kb = OUT.stat().st_size // 1024
    print(f"완료: {len(etfs)}개 저장 → {OUT} ({size_kb}KB)" + (f", 실패 {failed}개" if failed else ""))


if __name__ == "__main__":
    main()
