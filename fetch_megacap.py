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
NEWS_KEEP = 2
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
# 산업적으로 의미 있는 사건만 통과(주가 등락·실적 코멘터리·투자의견은 산업 사건이 아니다)
INDUSTRY_RE = re.compile(
    # 제품·기술
    r"unveil|launch|debut|introduc(e|es|ing)|next-?gen|breakthrough|mass production|"
    r"begins production|rolls? out|tape-?out|prototype|"
    # 설비·증설·자본투입
    r"\bfab\b|foundry|gigafactory|\bplant\b|factory|expands?|"
    r"(production|manufacturing|chip|memory|fab) capacity|capacity (expansion|increase|boost)|"
    r"data ?cent(er|re)|invests? \$|investment of \$|"
    # M&A·지분·구조
    r"acqui(re|res|red|sition)|merger|\bmerges?\b|takeover|buyout|\bstake\b|joint venture|"
    r"spin-?off|divest|delist|new (business )?(division|unit)|establishes|"
    r"sets up (a |the )?(new )?(unit|division|plant|factory|joint venture|subsidiary|business)|"
    # 계약·수주·제휴
    r"\bcontract\b|supply (deal|agreement|contract)|wins (deal|order|contract|bid)|awarded|"
    r"partners? with|partnership|teams? up with|agreement with|"
    # 규제·법·정책
    r"antitrust|lawsuit|\bsues\b|\bsued\b|settlement|investigation|\bprobe\b|\bfined\b|regulator|"
    r"\bbans?\b|banned|sanction|tariff|export control|subsidy|approval|approves?|approved|\bfda\b|"
    # 공급망·생산·보안
    r"shortage|supply chain|production (cut|halt|delay|boost|increase)|recall|outage|disrupt|"
    r"data breach|\bbreach\b|"
    # 조직·인사
    r"steps down|resigns?|\bappoints?\b|names new|\blayoffs?\b|job cuts|"
    r"restructuring|bankruptcy", re.I)
# 순수 노이즈(리스티클·매수의견 클릭베이트): 어느 출처든 제거
HARD_JUNK_RE = re.compile(
    r"\b\d+\s+(reasons|things|stocks|top|best|no-brainer|magnificent|high-yield|analysts)|"
    r"should you (buy|sell)|\bis\b.{0,30}\ba (buy|sell|good stock)\b|better buy|best (ai )?stock|"
    r"cramer|motley fool|zacks|insider (buying|selling|sells|buys|bought|sold)|"
    r"1 (magnificent|no-brainer|top|growth|incredible|ai) stock|here's why.{0,40}(buy|sell)|"
    r"trending stock|facts to know|rationale for (adding|buying)|what to know before|"
    r"beyond why|here is what to know|is a trending|"
    # 애널리스트·투자의견·밸류에이션(사용자 관심 밖)
    r"price target|\bpt\b (raised|lowered|to|of)|"
    r"(raises|lowers|cuts|boosts|lifts) (its |their )?(price[ -]?target|pt)|"
    r"initiates coverage|reiterates|maintains (a )?(buy|hold|sell|neutral|overweight|underweight)|"
    r"\b(upgrade|downgrade)[sd]?\b|\branalyst|outperform|underperform|overweight|underweight|"
    r"valuation|undervalued|overvalued|\bp/e\b|"
    # 시장색·주가 등락 기사
    r"what to watch|stocks? to watch|top (gainers|losers)|movers|52-?week|premarket|after-?hours|"
    r"shares? (rise|rises|fell|fall|falls|jump|jumps|slip|slips|surge|surges|tumble|tumbles|drop|drops|"
    r"climb|climbs|sink|sinks|soar|soars|gain|gains|plunge|plunges|rally|rallies)|"
    r"stock (rises|falls|jumps|surges|slips|drops|soars|sinks|plunges|climbs|hits|moves|forecast|analysis)|"
    r"buyback|repurchase|dividend|stock split|"
    # 로펌 소송모집 스팸(PR와이어로 대량 유입)
    r"shareholder alert|class action|securities fraud|lead plaintiff|deadline reminder|"
    r"investors? (have opportunity|who lost|with losses|encouraged)|law offices|"
    r"rosen law|pomerantz|bragar|levi & korsinsky|schall law|glancy prongay|"
    # 오피니언·백과사전·가정형
    r"if you'?d invested|had you invested|a bargain|worth buying|margin expansion|"
    r"\bbritannica\b|encyclopedia|"
    r"^(will|is|are|should|can|could|why)\b.{0,90}\?", re.I)


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


# 산업 변화 '유형' 분류 — 위에서부터 먼저 맞는 유형을 채택(뉴스 항목의 k 필드)
KIND_PATTERNS = [
    ("M&A·지분", re.compile(r"acqui(re|res|red|sition)|merger|\bmerges?\b|takeover|buyout|\bstake\b|"
                            r"joint venture|spin-?off|divest", re.I)),
    ("규제·소송", re.compile(r"antitrust|lawsuit|\bsues\b|\bsued\b|settlement|investigation|\bprobe\b|"
                            r"\bfined\b|regulator|\bbans?\b|banned|sanction|tariff|export control|"
                            r"subsidy|approval|approves?|approved|\bfda\b", re.I)),
    ("증설·투자", re.compile(r"\bfab\b|foundry|gigafactory|\bplant\b|factory|data ?cent(er|re)|"
                            r"invests? \$|investment of \$|(production|manufacturing|chip|memory|fab) capacity|"
                            r"capacity (expansion|increase|boost)|expands?", re.I)),
    ("계약·제휴", re.compile(r"\bcontract\b|supply (deal|agreement|contract)|wins (deal|order|contract|bid)|"
                            r"awarded|partners? with|partnership|teams? up with|agreement with", re.I)),
    ("신제품·기술", re.compile(r"unveil|launch|debut|introduc(e|es|ing)|next-?gen|breakthrough|"
                             r"mass production|begins production|rolls? out|tape-?out|prototype", re.I)),
    ("공급망·생산", re.compile(r"shortage|supply chain|production (cut|halt|delay|boost|increase)|recall|"
                             r"outage|disrupt|data breach|\bbreach\b", re.I)),
    ("조직·인사", re.compile(r"steps down|resigns?|\bappoints?\b|names new|\blayoffs?\b|job cuts|"
                            r"restructuring|bankruptcy|new (business )?(division|unit)|establishes|"
                            r"sets up (a |the )?(new )?(unit|division|plant|factory|joint venture|subsidiary|business)", re.I)),
]


def _news_kind(title):
    for label, pat in KIND_PATTERNS:
        if pat.search(title or ""):
            return label
    return "기타"


def curate_news(items):
    """산업 이벤트 선별(items 의 t 는 번역 전 영문 헤드라인 전제):
    차단 출처 제거 · 정크/애널리스트/시장색 기사 제거 · **모든 출처에 산업 이벤트를 요구** ·
    근접 중복 제거. (주가 등락·투자의견·실적 코멘터리는 산업 사건이 아니므로 제외)"""
    kept, reps, seen_str = [], [], set()   # reps: [(토큰집합, 대표항목)] — 근접 클러스터
    for it in items:
        title = it.get("t", "")
        if _src_tier(it.get("s", "")) == "block":
            continue
        if HARD_JUNK_RE.search(title):
            continue
        if not INDUSTRY_RE.search(title):
            continue
        toks = _norm_tokens(title)
        if toks:
            hit = next((ri for rt, ri in reps if rt and len(toks & rt) / len(toks | rt) >= 0.6), None)
            if hit is not None:                 # 같은 사건의 다른 매체 보도 → 대표의 교차보도수 +1
                hit["dc"] = hit.get("dc", 1) + 1
                continue
        else:  # 비라틴/기호만 제목 → 글자·숫자가 없으면 드롭, 있으면(CJK 등) 전체문자열로 중복 처리
            if not re.sub(r"[\W_]+", "", title):
                continue
            norm = re.sub(r"\s+", " ", title.strip().lower())
            if norm in seen_str:
                continue
            seen_str.add(norm)
        it["k"] = _news_kind(title)   # 산업 변화 유형(영문 헤드라인 기준 — 번역 전에 분류)
        it["dc"] = 1                  # 교차보도 수(같은 사건을 다룬 매체 수)
        kept.append(it)
        reps.append((toks, it))
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
        # 종목당 '가장 크게 다뤄진(교차보도 많은)' 뉴스 우선으로 NEWS_KEEP개 (동점은 최신 유지)
        return sorted(curate_news(items), key=lambda x: -x.get("dc", 1))[:NEWS_KEEP]
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
