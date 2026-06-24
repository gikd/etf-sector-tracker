#!/usr/bin/env python3
"""[주 1회] 글로벌 시총 TOP 100 명단 산정.

후보군(~140) 시가총액을 Yahoo(crumb 인증)로 받아 USD로 환산·랭킹 → 상위 100개를
docs/megacap_universe.json 에 저장. 시세가 아닌 '명단'만 갱신(주간).
실패 시 기존 명단을 덮어쓰지 않음. 사용법: python3 fetch_universe.py
"""
import http.cookiejar
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TOP_N = 100
OUT = Path(__file__).parent / "docs" / "megacap_universe.json"

# 후보군 (한글명, Yahoo심볼, 섹터) — 이 중 시총 상위 100개가 명단이 됨
CANDIDATES = [
    # AI·반도체
    ("엔비디아", "NVDA", "AI·반도체"), ("브로드컴", "AVGO", "AI·반도체"), ("TSMC", "TSM", "AI·반도체"),
    ("ASML", "ASML", "AI·반도체"), ("AMD", "AMD", "AI·반도체"), ("퀄컴", "QCOM", "AI·반도체"),
    ("텍사스인스트루먼트", "TXN", "AI·반도체"), ("삼성전자", "005930.KS", "AI·반도체"),
    ("SK하이닉스", "000660.KS", "AI·반도체"), ("마이크론", "MU", "AI·반도체"), ("ARM", "ARM", "AI·반도체"),
    ("어플라이드머티어리얼즈", "AMAT", "AI·반도체"), ("인텔", "INTC", "AI·반도체"), ("램리서치", "LRCX", "AI·반도체"),
    ("KLA", "KLAC", "AI·반도체"), ("마벨", "MRVL", "AI·반도체"), ("아나로그디바이스", "ADI", "AI·반도체"),
    ("NXP", "NXPI", "AI·반도체"), ("인피니언", "IFX.DE", "AI·반도체"),
    # 빅테크 플랫폼
    ("애플", "AAPL", "빅테크 플랫폼"), ("마이크로소프트", "MSFT", "빅테크 플랫폼"),
    ("알파벳(구글)", "GOOGL", "빅테크 플랫폼"), ("아마존", "AMZN", "빅테크 플랫폼"), ("메타(페이스북)", "META", "빅테크 플랫폼"),
    # 소프트웨어·클라우드
    ("오라클", "ORCL", "소프트웨어·클라우드"), ("SAP", "SAP", "소프트웨어·클라우드"), ("세일즈포스", "CRM", "소프트웨어·클라우드"),
    ("팔란티어", "PLTR", "소프트웨어·클라우드"), ("어도비", "ADBE", "소프트웨어·클라우드"), ("서비스나우", "NOW", "소프트웨어·클라우드"),
    ("인튜이트", "INTU", "소프트웨어·클라우드"), ("IBM", "IBM", "소프트웨어·클라우드"), ("시스코", "CSCO", "소프트웨어·클라우드"),
    ("액센츄어", "ACN", "소프트웨어·클라우드"), ("팔로알토", "PANW", "소프트웨어·클라우드"), ("크라우드스트라이크", "CRWD", "소프트웨어·클라우드"),
    # 인터넷·이커머스
    ("텐센트", "TCEHY", "인터넷·이커머스"), ("알리바바", "BABA", "인터넷·이커머스"), ("핀둬둬", "PDD", "인터넷·이커머스"),
    ("부킹홀딩스", "BKNG", "인터넷·이커머스"), ("우버", "UBER", "인터넷·이커머스"), ("쇼피파이", "SHOP", "인터넷·이커머스"),
    ("메르카도리브레", "MELI", "인터넷·이커머스"), ("씨(Sea)", "SE", "인터넷·이커머스"), ("에어비앤비", "ABNB", "인터넷·이커머스"),
    ("넷이즈", "NTES", "인터넷·이커머스"),
    # 금융
    ("버크셔해서웨이", "BRK-B", "금융"), ("JP모건", "JPM", "금융"), ("비자", "V", "금융"), ("마스터카드", "MA", "금융"),
    ("뱅크오브아메리카", "BAC", "금융"), ("웰스파고", "WFC", "금융"), ("모건스탠리", "MS", "금융"), ("골드만삭스", "GS", "금융"),
    ("블랙록", "BLK", "금융"), ("아메리칸익스프레스", "AXP", "금융"), ("씨티그룹", "C", "금융"),
    ("S&P글로벌", "SPGI", "금융"), ("찰스슈왑", "SCHW", "금융"), ("HSBC", "HSBC", "금융"), ("미쓰비시UFJ", "MUFG", "금융"),
    # 헬스케어·제약
    ("일라이릴리", "LLY", "헬스케어·제약"), ("노보노디스크", "NVO", "헬스케어·제약"), ("J&J", "JNJ", "헬스케어·제약"),
    ("애브비", "ABBV", "헬스케어·제약"), ("머크", "MRK", "헬스케어·제약"), ("유나이티드헬스", "UNH", "헬스케어·제약"),
    ("아스트라제네카", "AZN", "헬스케어·제약"), ("노바티스", "NVS", "헬스케어·제약"), ("로슈", "RHHBY", "헬스케어·제약"),
    ("애보트", "ABT", "헬스케어·제약"), ("써모피셔", "TMO", "헬스케어·제약"), ("인튜이티브서지컬", "ISRG", "헬스케어·제약"),
    ("암젠", "AMGN", "헬스케어·제약"), ("화이자", "PFE", "헬스케어·제약"), ("다나허", "DHR", "헬스케어·제약"),
    ("사노피", "SNY", "헬스케어·제약"), ("GSK", "GSK", "헬스케어·제약"), ("메드트로닉", "MDT", "헬스케어·제약"),
    # 소비재·명품
    ("월마트", "WMT", "소비재·명품"), ("코스트코", "COST", "소비재·명품"), ("P&G", "PG", "소비재·명품"),
    ("코카콜라", "KO", "소비재·명품"), ("펩시코", "PEP", "소비재·명품"), ("맥도날드", "MCD", "소비재·명품"),
    ("홈디포", "HD", "소비재·명품"), ("필립모리스", "PM", "소비재·명품"), ("LVMH", "MC.PA", "소비재·명품"),
    ("에르메스", "RMS.PA", "소비재·명품"), ("네슬레", "NSRGY", "소비재·명품"), ("로레알", "OR.PA", "소비재·명품"),
    ("디아지오", "DEO", "소비재·명품"), ("유니레버", "UL", "소비재·명품"), ("나이키", "NKE", "소비재·명품"),
    ("인디텍스(자라)", "ITX.MC", "소비재·명품"),
    # 에너지
    ("사우디아람코", "2222.SR", "에너지"), ("엑슨모빌", "XOM", "에너지"), ("셰브론", "CVX", "에너지"),
    ("쉘", "SHEL", "에너지"), ("토탈에너지", "TTE", "에너지"), ("코노코필립스", "COP", "에너지"), ("BP", "BP", "에너지"),
    # 산업·소재·방산
    ("GE에어로스페이스", "GE", "산업·소재·방산"), ("캐터필러", "CAT", "산업·소재·방산"), ("RTX", "RTX", "산업·소재·방산"),
    ("허니웰", "HON", "산업·소재·방산"), ("보잉", "BA", "산업·소재·방산"), ("록히드마틴", "LMT", "산업·소재·방산"),
    ("린데", "LIN", "산업·소재·방산"), ("지멘스", "SIE.DE", "산업·소재·방산"), ("디어", "DE", "산업·소재·방산"),
    ("유니온퍼시픽", "UNP", "산업·소재·방산"), ("슈나이더일렉트릭", "SU.PA", "산업·소재·방산"), ("에어버스", "AIR.PA", "산업·소재·방산"),
    # 통신·미디어
    ("넷플릭스", "NFLX", "통신·미디어"), ("디즈니", "DIS", "통신·미디어"), ("T모바일", "TMUS", "통신·미디어"),
    ("컴캐스트", "CMCSA", "통신·미디어"), ("버라이즌", "VZ", "통신·미디어"), ("AT&T", "T", "통신·미디어"),
    ("스포티파이", "SPOT", "통신·미디어"), ("차터커뮤니케이션", "CHTR", "통신·미디어"),
    # 자동차
    ("테슬라", "TSLA", "자동차"), ("도요타", "TM", "자동차"), ("BYD", "1211.HK", "자동차"), ("페라리", "RACE", "자동차"),
    ("메르세데스벤츠", "MBG.DE", "자동차"), ("폭스바겐", "VOW3.DE", "자동차"), ("현대차", "005380.KS", "자동차"),
    ("기아", "000270.KS", "자동차"), ("포르쉐", "P911.DE", "자동차"), ("GM", "GM", "자동차"), ("혼다", "HMC", "자동차"),
]


def make_opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")]
    try:
        op.open("https://fc.yahoo.com/", timeout=15).read()
    except Exception:
        pass
    crumb = op.open("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=15).read().decode()
    if not crumb or "<" in crumb:
        raise RuntimeError("crumb 획득 실패")
    return op, crumb


def fx_rates(op, currencies):
    """{통화: 1 USD당 해당통화} 환율. USD는 1.0."""
    rates = {"USD": 1.0}
    for c in currencies:
        if c in rates or c == "GBp":
            continue
        base = "GBP" if c == "GBp" else c
        try:
            d = json.load(op.open(f"https://query1.finance.yahoo.com/v8/finance/chart/{base}=X?range=5d&interval=1d", timeout=12))
            rates[base] = d["chart"]["result"][0]["meta"]["regularMarketPrice"]
        except Exception as e:
            print(f"  FX 실패 {base}: {e}")
    return rates


def to_usd(mcap, ccy, fx):
    if not mcap:
        return 0
    if ccy == "GBp":  # 펜스 → 파운드 → USD
        return mcap / 100 / fx.get("GBP", 1)
    return mcap / fx.get(ccy, 1)


def main():
    op, crumb = make_opener()
    syms = [c[1] for c in CANDIDATES]
    quotes = {}
    # 50개씩 배치
    for i in range(0, len(syms), 50):
        batch = syms[i:i + 50]
        url = ("https://query1.finance.yahoo.com/v7/finance/quote?symbols="
               + urllib.parse.quote(",".join(batch)) + "&crumb=" + urllib.parse.quote(crumb))
        d = json.load(op.open(url, timeout=20))
        for r in d["quoteResponse"]["result"]:
            quotes[r["symbol"]] = {
                "mc": r.get("marketCap"), "ccy": r.get("currency", "USD"),
                "eps_now": r.get("epsCurrentYear"),   # 올해 EPS 추정 → 매일 주가로 PER 계산
                "eps_next": r.get("epsForward"),      # 내년(선행) EPS 추정
                "enname": r.get("longName") or r.get("shortName"),  # 영문명 → 글로벌 뉴스 검색용
            }

    fx = fx_rates(op, {q["ccy"] for q in quotes.values()})
    print(f"환율(USD당): " + ", ".join(f"{k}={v:.2f}" for k, v in fx.items() if k != "USD"))

    ranked = []
    for name, sym, sector in CANDIDATES:
        q = quotes.get(sym, {})
        usd = to_usd(q.get("mc"), q.get("ccy", "USD"), fx)
        if usd > 0:
            ranked.append({
                "name": name, "ticker": sym, "sector": sector,
                "mcap_b": round(usd / 1e9, 1),
                "eps_now": q.get("eps_now"), "eps_next": q.get("eps_next"),
                "enname": q.get("enname"),
            })
    ranked.sort(key=lambda x: x["mcap_b"], reverse=True)
    members = ranked[:TOP_N]
    for i, m in enumerate(members, 1):
        m["rank"] = i

    if len(members) < TOP_N * 0.8:
        raise SystemExit(f"시총 수집 부족({len(members)}/{TOP_N}) — 기존 명단 유지")

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "count": len(members),
        "members": members,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    cut = members[-1]
    print(f"완료: TOP {len(members)} 명단 저장 → {OUT}")
    print(f"  1위 {members[0]['name']} ${members[0]['mcap_b']:,}B / 컷 {cut['name']} ${cut['mcap_b']:,}B")


if __name__ == "__main__":
    main()
