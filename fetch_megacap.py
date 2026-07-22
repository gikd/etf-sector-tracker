#!/usr/bin/env python3
"""[매일] 글로벌 메가캡 시세·모멘텀·뉴스 갱신 + 선행 PER 계산.

명단(TOP300)은 fetch_universe.py가 주 1회 만든 docs/megacap_universe.json 사용.
이 스크립트는 매일: 시세·일봉 캔들·한국어 뉴스 갱신, 명단의 EPS로 올해/내년 PER 계산.
docs/megacap.json 생성.
"""
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

HIST_DAYS = 130
API = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=1y&interval=1d"
NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
TRANSLATE = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={q}"
DOCS = Path(__file__).parent / "docs"
UNIVERSE = DOCS / "megacap_universe.json"
OUT = DOCS / "megacap.json"

# ── 뉴스 선별(중도): 대형 언론·공식 릴리스는 채택 / 애그리게이터·SEO는 차단 /
#    그 외(중간 출처)는 실적·M&A·소송 등 중대 이벤트일 때만 구제. 정크 헤드라인·근접중복 제거. 종목당 NEWS_KEEP개. ──
NEWS_KEEP = 3
ALLOW_SRC = [
    "bloomberg", "reuters", "wall street journal", "wsj", "financial times", "cnbc",
    "yahoo finance", "barron", "marketwatch", "the information", "nikkei", "associated press",
    "ap news", "apnews", "axios", "economist", "fortune", "forbes", "business insider",
    "seeking alpha", "globe and mail", "financial post", "the guardian", "new york times",
    "nytimes", "washington post", "cnn", "quartz", "techcrunch", "the verge", "ars technica",
    "wired", "tom's hardware", "the register", "semianalysis",
    "pr newswire", "prnewswire", "business wire", "businesswire", "globe newswire", "globenewswire",
    "yonhap", "연합", "한국경제", "hankyung", "매일경제", "mk.co", "조선", "chosun", "전자신문",
    "etnews", "서울경제", "sedaily", "아시아경제", "asiae", "이데일리", "edaily", "머니투데이",
    "mt.co", "중앙", "joongang", "파이낸셜뉴스", "news1", "뉴스1", "헤럴드", "heraldcorp",
    "디지털데일리", "ddaily", "zdnet", "지디넷", "블로터", "bloter", "더구루", "theguru",
]
BLOCK_SRC = [
    "marketbeat", "ad-hoc-news", "tradingview", "marketscreener", "gurufocus", "guru focus",
    "moomoo", "openpr", "stock titan", "stocktitan", "kalkine", "traders union",
    "tradersunion", "investing.com", "indexbox", "simplywall", "simply wall", "barchart",
    "quiver", "scanx", "biggo", "tikr", "tipranks", "zacks", "insider monkey", "benzinga", "24/7 wall",
    "defense world", "defenseworld", "americanbankingnews", "cerbat", "wkrb", "ledger gazette",
    "etf daily", "modern readers", "mayfield recorder", "invezz", "fintel", "stocknews",
    "wallmine", "stockstory", "the markets daily", "motley fool",
]
BLOCK_WORD = ["msn"]  # 단어경계 매칭 — 'MSNBC'(정상 매체)를 MSN 애그리게이터로 오차단하지 않게
_BLOCK_WORD_RE = re.compile(r"\b(" + "|".join(BLOCK_WORD) + r")\b", re.I)
MATERIAL_RE = re.compile(
    r"earnings|quarterly (results|profit|revenue)|q[1-4] (results|earnings)|"
    r"beats?\s+(estimates|expectations|forecasts?|the street|views)|"
    r"misses?\s+(estimates|expectations|forecasts?|views)|"
    r"guidance|acqui|buyout|takeover|merger|\bmerges?\b|\bstake\b|invests? \$|investment of \$|"
    r"lawsuit|\bsues\b|\bsued\b|settlement|antitrust|investigation|\bfined\b|\bcontract\b|awarded|"
    r"wins (deal|order|contract|bid|approval)|partners? with|recall|approval|approved|\bfda\b|"
    r"bankruptcy|\blayoffs?\b|job cuts|steps down|resign|\bappoints?\b|names new|buyback|repurchase|"
    r"dividend|stock split|\bipo\b|spin-?off|delist|data breach|\bbreach\b|outage|sanction|tariff|"
    r"export control", re.I)
# 순수 노이즈(리스티클·매수의견 클릭베이트): 어느 출처든 제거
HARD_JUNK_RE = re.compile(
    r"\b\d+\s+(reasons|things|stocks|top|best|no-brainer|magnificent|high-yield|analysts)|"
    r"should you (buy|sell)|\bis\b.{0,30}\ba (buy|sell|good stock)\b|better buy|best (ai )?stock|"
    r"cramer|motley fool|zacks|insider (buying|selling|sells|buys|bought|sold)|"
    r"1 (magnificent|no-brainer|top|growth|incredible|ai) stock|here's why.{0,40}(buy|sell)|"
    r"trending stock|facts to know|rationale for (adding|buying)|what to know before|"
    r"beyond why|here is what to know|is a trending", re.I)
# 브로커 기계뉴스(목표주가·투자의견): 중대 이벤트와 겹칠 수 있어 material 이면 살린다(curate_news 참조)
SOFT_JUNK_RE = re.compile(
    r"price target|\bpt\b (raised|lowered|to|of)|"
    r"(raises|lowers|cuts|boosts|lifts) (its |their )?(price[ -]?target|pt)|"
    r"initiates coverage|reiterates|maintains (a )?(buy|hold|sell|neutral|overweight|underweight)", re.I)


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


def _src_tier(src):
    s = (src or "").lower()
    if any(k in s for k in BLOCK_SRC) or _BLOCK_WORD_RE.search(s):
        return "block"
    if any(k in s for k in ALLOW_SRC):
        return "allow"
    return "mid"


def _norm_tokens(t):
    return set(re.sub(r"[^a-z0-9가-힣]+", " ", (t or "").lower()).split())


def curate_news(items):
    """중도 선별(items 의 t 는 번역 전 영문 헤드라인 전제):
    차단 출처 제거 · 순수 정크(HARD) 제거 · 브로커 기계뉴스(SOFT)는 중대 이벤트 아닐 때만 제거 ·
    중간 출처는 중대 이벤트만 구제 · 근접 중복 제거."""
    kept, seen_tok, seen_str = [], [], set()
    for it in items:
        title = it.get("t", "")
        tier = _src_tier(it.get("s", ""))
        if tier == "block":
            continue
        if HARD_JUNK_RE.search(title):
            continue
        material = bool(MATERIAL_RE.search(title))
        if SOFT_JUNK_RE.search(title) and not material:
            continue
        if tier == "mid" and not material:
            continue
        toks = _norm_tokens(title)
        if toks:
            if any(len(toks & p) / len(toks | p) >= 0.7 for p in seen_tok):
                continue  # 근접 중복(자카드 ≥ 0.7)
            seen_tok.append(toks)
        else:  # 비라틴/기호만 제목 → 글자·숫자가 없으면(공백·기호만) 드롭, 있으면(CJK 등) 전체문자열로 중복 처리
            if not re.sub(r"[\W_]+", "", title):  # 모든 스크립트의 글자/숫자만 남긴 게 비면 드롭
                continue
            norm = re.sub(r"\s+", " ", title.strip().lower())
            if norm in seen_str:
                continue
            seen_str.add(norm)
        kept.append(it)
    return kept


def fetch_news(query):
    """영문 글로벌 뉴스(최근 7일) — 글로벌 회사이므로 외국 뉴스 우선. 중도 선별 후 상위 NEWS_KEEP개."""
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
        return curate_news(items)[:NEWS_KEEP]
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
    size_kb = OUT.stat().st_size // 1024
    print(f"완료: {len(stocks)}개 저장 → {OUT} ({size_kb}KB)" + (f" (실패: {failed})" if failed else ""))


if __name__ == "__main__":
    main()
