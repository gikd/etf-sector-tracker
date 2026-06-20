#!/usr/bin/env python3
"""글로벌 시총 TOP ~100 메가캡 — 섹터 분류 + 모멘텀 지표 수집.

목적: '큰돈도 쉽게 거래 가능한' 초대형주만 추려, 섹터별 강세와
잘 가는 종목(모멘텀)을 본다. 시총 랭킹은 수동 큐레이션(분기 단위로만 크게 변동),
시세·모멘텀은 매일 자동 갱신. docs/megacap.json / megacap.js 생성.
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

# (한글명, Yahoo심볼, 섹터, 저유동 플래그)  — 섹터는 직접 분류
LOWLIQ = "lowliq"
MEGACAP = [
    # ── AI·반도체 ──
    ("엔비디아", "NVDA", "AI·반도체"), ("브로드컴", "AVGO", "AI·반도체"),
    ("TSMC", "TSM", "AI·반도체"), ("ASML", "ASML", "AI·반도체"),
    ("AMD", "AMD", "AI·반도체"), ("퀄컴", "QCOM", "AI·반도체"),
    ("텍사스인스트루먼트", "TXN", "AI·반도체"), ("삼성전자", "005930.KS", "AI·반도체"),
    ("SK하이닉스", "000660.KS", "AI·반도체"), ("마이크론", "MU", "AI·반도체"),
    ("ARM", "ARM", "AI·반도체"), ("어플라이드머티어리얼즈", "AMAT", "AI·반도체"),
    # ── 빅테크 플랫폼 ──
    ("애플", "AAPL", "빅테크 플랫폼"), ("마이크로소프트", "MSFT", "빅테크 플랫폼"),
    ("알파벳(구글)", "GOOGL", "빅테크 플랫폼"), ("아마존", "AMZN", "빅테크 플랫폼"),
    ("메타(페이스북)", "META", "빅테크 플랫폼"),
    # ── 소프트웨어·클라우드 ──
    ("오라클", "ORCL", "소프트웨어·클라우드"), ("SAP", "SAP", "소프트웨어·클라우드"),
    ("세일즈포스", "CRM", "소프트웨어·클라우드"), ("팔란티어", "PLTR", "소프트웨어·클라우드"),
    ("어도비", "ADBE", "소프트웨어·클라우드"), ("서비스나우", "NOW", "소프트웨어·클라우드"),
    ("인튜이트", "INTU", "소프트웨어·클라우드"), ("IBM", "IBM", "소프트웨어·클라우드"),
    ("시스코", "CSCO", "소프트웨어·클라우드"), ("액센츄어", "ACN", "소프트웨어·클라우드"),
    # ── 인터넷·이커머스 ──
    ("텐센트", "TCEHY", "인터넷·이커머스"), ("알리바바", "BABA", "인터넷·이커머스"),
    ("핀둬둬", "PDD", "인터넷·이커머스"), ("부킹홀딩스", "BKNG", "인터넷·이커머스"),
    ("우버", "UBER", "인터넷·이커머스"), ("쇼피파이", "SHOP", "인터넷·이커머스"),
    ("메르카도리브레", "MELI", "인터넷·이커머스"), ("씨(Sea)", "SE", "인터넷·이커머스"),
    # ── 금융 ──
    ("버크셔해서웨이", "BRK-B", "금융"), ("JP모건", "JPM", "금융"), ("비자", "V", "금융"),
    ("마스터카드", "MA", "금융"), ("뱅크오브아메리카", "BAC", "금융"), ("웰스파고", "WFC", "금융"),
    ("모건스탠리", "MS", "금융"), ("골드만삭스", "GS", "금융"), ("블랙록", "BLK", "금융"),
    ("아메리칸익스프레스", "AXP", "금융"), ("씨티그룹", "C", "금융"),
    # ── 헬스케어·제약 ──
    ("일라이릴리", "LLY", "헬스케어·제약"), ("노보노디스크", "NVO", "헬스케어·제약"),
    ("J&J", "JNJ", "헬스케어·제약"), ("애브비", "ABBV", "헬스케어·제약"),
    ("머크", "MRK", "헬스케어·제약"), ("유나이티드헬스", "UNH", "헬스케어·제약"),
    ("아스트라제네카", "AZN", "헬스케어·제약"), ("노바티스", "NVS", "헬스케어·제약"),
    ("로슈", "RHHBY", "헬스케어·제약"), ("애보트", "ABT", "헬스케어·제약"),
    ("써모피셔", "TMO", "헬스케어·제약"), ("인튜이티브서지컬", "ISRG", "헬스케어·제약"),
    ("암젠", "AMGN", "헬스케어·제약"),
    # ── 소비재·명품 ──
    ("월마트", "WMT", "소비재·명품"), ("코스트코", "COST", "소비재·명품"),
    ("P&G", "PG", "소비재·명품"), ("코카콜라", "KO", "소비재·명품"),
    ("펩시코", "PEP", "소비재·명품"), ("맥도날드", "MCD", "소비재·명품"),
    ("홈디포", "HD", "소비재·명품"), ("필립모리스", "PM", "소비재·명품"),
    ("LVMH", "MC.PA", "소비재·명품"), ("에르메스", "RMS.PA", "소비재·명품"),
    ("네슬레", "NSRGY", "소비재·명품"),
    # ── 에너지 ──
    ("사우디아람코", "2222.SR", "에너지", LOWLIQ), ("엑슨모빌", "XOM", "에너지"),
    ("셰브론", "CVX", "에너지"), ("쉘", "SHEL", "에너지"),
    ("토탈에너지", "TTE", "에너지"), ("코노코필립스", "COP", "에너지"),
    # ── 산업·소재·방산 ──
    ("GE에어로스페이스", "GE", "산업·소재·방산"), ("캐터필러", "CAT", "산업·소재·방산"),
    ("RTX", "RTX", "산업·소재·방산"), ("허니웰", "HON", "산업·소재·방산"),
    ("보잉", "BA", "산업·소재·방산"), ("록히드마틴", "LMT", "산업·소재·방산"),
    ("린데", "LIN", "산업·소재·방산"), ("지멘스", "SIE.DE", "산업·소재·방산"),
    # ── 통신·미디어 ──
    ("넷플릭스", "NFLX", "통신·미디어"), ("디즈니", "DIS", "통신·미디어"),
    ("T모바일", "TMUS", "통신·미디어"), ("컴캐스트", "CMCSA", "통신·미디어"),
    ("버라이즌", "VZ", "통신·미디어"), ("AT&T", "T", "통신·미디어"),
    ("스포티파이", "SPOT", "통신·미디어"),
    # ── 자동차 ──
    ("테슬라", "TSLA", "자동차"), ("도요타", "TM", "자동차"), ("BYD", "1211.HK", "자동차"),
    ("페라리", "RACE", "자동차"), ("메르세데스벤츠", "MBG.DE", "자동차"),
    ("폭스바겐", "VOW3.DE", "자동차"), ("현대차", "005380.KS", "자동차"),
]

HIST_DAYS = 100
API = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=1y&interval=1d"
OUT = Path(__file__).parent / "docs" / "megacap.json"


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
    print(f"메가캡 {len(MEGACAP)}개 시세 수집 중...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda r: fetch(r[1]), MEGACAP))

    stocks, failed = [], []
    for row, d in zip(MEGACAP, results):
        name, sym, sector = row[0], row[1], row[2]
        if d is None:
            failed.append(sym)
            continue
        item = {"name": name, "ticker": sym, "sector": sector, **d}
        if len(row) > 3 and row[3] == LOWLIQ:
            item["lowliq"] = True
        stocks.append(item)

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "count": len(stocks),
        "stocks": stocks,
    }
    payload = json.dumps(out, ensure_ascii=False)
    OUT.write_text(payload, encoding="utf-8")
    OUT.with_name("megacap.js").write_text("window.__MEGACAP__ = " + payload + ";", encoding="utf-8")
    print(f"완료: {len(stocks)}개 저장 → {OUT}" + (f" (실패: {failed})" if failed else ""))


if __name__ == "__main__":
    main()
