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

# 테마 → 그룹 → [(한글명, Yahoo심볼)]  (구글시트 참고, 분류/티커 정리)
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
    "반도체": {
        "설계·IDM (해외)": [
            ("엔비디아", "NVDA"), ("브로드컴", "AVGO"), ("AMD", "AMD"), ("인텔", "INTC"),
            ("퀄컴", "QCOM"), ("텍사스인스트루먼트", "TXN"), ("마벨", "MRVL"),
            ("아나로그디바이스", "ADI"), ("NXP", "NXPI"), ("온세미", "ON"),
            ("ST마이크로", "STM"), ("인피니언", "IFX.DE"), ("미디어텍", "2454.TW"),
            ("리얼텍", "2379.TW"), ("노바텍", "3034.TW"), ("퀄보", "QRVO"), ("스카이웍스", "SWKS"),
        ],
        "메모리·파운드리": [
            ("삼성전자", "005930.KS"), ("SK하이닉스", "000660.KS"), ("TSMC", "TSM"),
            ("마이크론", "MU"), ("웨스턴디지털", "WDC"), ("난야테크", "2408.TW"),
        ],
        "장비": [
            ("어플라이드머티어리얼즈", "AMAT"), ("ASML", "ASML"), ("램리서치", "LRCX"),
            ("KLA", "KLAC"), ("반도체3배(SOXL)", "SOXL"),
        ],
    },
    "2차전지": {
        "셀 (배터리)": [
            ("LG에너지솔루션", "373220.KS"), ("삼성SDI", "006400.KS"), ("SK이노베이션", "096770.KS"),
            ("CATL", "300750.SZ"), ("BYD", "1211.HK"), ("궈쉬안", "002074.SZ"),
            ("EVE에너지", "300014.SZ"), ("파나소닉", "6752.T"), ("GS유아사", "6674.T"),
        ],
        "소재·부품 (국내)": [
            ("LG화학", "051910.KS"), ("엘앤에프", "066970.KS"), ("에코프로비엠", "247540.KS"),
            ("에코프로", "086520.KS"), ("포스코퓨처엠", "003670.KS"), ("POSCO홀딩스", "005490.KS"),
            ("코스모신소재", "005070.KS"), ("대주전자재료", "078600.KS"), ("나노신소재", "121600.KS"),
            ("SKIET", "361610.KS"), ("솔브레인", "357780.KS"), ("더블유씨피", "393890.KS"),
            ("천보", "278280.KS"), ("후성", "093370.KS"), ("엔켐", "348370.KS"),
            ("솔루스첨단소재", "336370.KS"), ("윤성에프앤씨", "372170.KS"),
        ],
        "리튬·원자재 (해외)": [
            ("테슬라", "TSLA"), ("알버말", "ALB"), ("SQM", "SQM"), ("FMC", "FMC"),
            ("위미코어", "UMI.BR"), ("톈치리튬", "002466.SZ"), ("간펑리튬", "002460.SZ"),
        ],
        "中·日 소재": [
            ("화유코발트", "603799.SS"), ("뤄양몰리브덴", "603993.SS"), ("톈츠재료", "002709.SZ"),
            ("신줘방", "300037.SZ"), ("더팡나노", "300769.SZ"), ("당성과기", "300073.SZ"),
            ("산산", "600884.SS"), ("스미토모금속광산", "5713.T"),
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
