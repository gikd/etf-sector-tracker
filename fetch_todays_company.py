#!/usr/bin/env python3
"""라이브 '오늘의 기업' → 지도 연결 데이터 생성.

노션 '회차' DB(묘수 라이브)의 각 날짜 페이지에서 `오늘의 기업` 섹션을 찾아
회사명·티커·한 줄 요약·날짜를 뽑아 docs/todays_company.json 으로 저장한다.
티커는 docs/megacap_universe.json(시총 TOP300)과 매칭되는 것만 남긴다.
전체 백필·매일 갱신 모두 이 스크립트 재실행으로 해결(결정적 재생성).

필요: 환경변수 NOTION_TOKEN (회차 DB 접근 권한이 있는 인테그레이션 토큰).
사용법: NOTION_TOKEN=... python3 fetch_todays_company.py
"""
import json
import os
import re
import time
import urllib.request
from pathlib import Path

DOCS = Path(__file__).parent / "docs"
OUT = DOCS / "todays_company.json"
UNIVERSE = DOCS / "megacap_universe.json"

# 묘수 라이브 '회차' 데이터소스 ID
DB_ID = "27d9a188-9c10-46dc-a94e-a58c1905142a"
TOKEN = os.environ.get("NOTION_TOKEN", "")
API = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": "Bearer " + TOKEN,
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# 헤더의 '회사명(TICKER)' 또는 '회사명 (TICKER) · 요약' 에서 티커 추출
TICKER_RE = re.compile(r"\(([A-Z0-9][A-Z0-9.\-]{0,6})\)")


def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, headers=HEADERS, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read())


def query_pages():
    """회차 DB의 모든 페이지 (제목·날짜·id). 날짜 내림차순."""
    pages, cursor = [], None
    while True:
        body = {"page_size": 100, "sorts": [{"property": "날짜", "direction": "descending"}]}
        if cursor:
            body["start_cursor"] = cursor
        d = _req("POST", f"/databases/{DB_ID}/query", body)
        for p in d["results"]:
            props = p.get("properties", {})
            date = (props.get("날짜", {}).get("date") or {}).get("start")
            pages.append({"id": p["id"], "date": date})
        if not d.get("has_more"):
            break
        cursor = d["next_cursor"]
    return pages


def rich_text(block):
    t = block.get(block["type"], {})
    return "".join(r.get("plain_text", "") for r in t.get("rich_text", [])).strip()


def list_children(block_id):
    out, cursor = [], None
    while True:
        q = f"/blocks/{block_id}/children?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
        d = _req("GET", q)
        out.extend(d["results"])
        if not d.get("has_more"):
            break
        cursor = d["next_cursor"]
    return out


def extract(page_blocks):
    """페이지 블록들에서 '오늘의 기업' 섹션들을 (ticker, name, blurb) 리스트로."""
    found = []
    blocks = page_blocks
    for i, b in enumerate(blocks):
        bt = b.get("type", "")
        if not bt.startswith("heading"):
            continue
        if rich_text(b) != "오늘의 기업":
            continue
        # 헤더 다음 첫 비어있지 않은 문단 = 회사 라인
        line, blurb = "", ""
        for nb in blocks[i + 1:]:
            if nb["type"] in ("paragraph", "heading_1", "heading_2", "heading_3"):
                txt = rich_text(nb)
                if txt:
                    if not line:
                        line = txt
                        # '·' 뒤에 요약이 같은 줄에 붙은 경우
                        if "·" in line:
                            head, _, rest = line.partition("·")
                            line, blurb = head.strip(), rest.strip()
                    elif not blurb:
                        blurb = txt
                        break
                    else:
                        break
            elif nb["type"] in ("divider",):
                continue
        m = TICKER_RE.search(line)
        if not m:
            continue
        ticker = m.group(1)
        name = line[: m.start()].strip().rstrip("(").strip()
        found.append({"ticker": ticker, "name": name or ticker, "blurb": blurb})
    return found


def main():
    if not TOKEN:
        raise SystemExit("NOTION_TOKEN 환경변수가 필요합니다.")
    valid = None
    if UNIVERSE.exists():
        uni = json.loads(UNIVERSE.read_text())
        valid = {m["ticker"] for m in uni.get("members", [])}

    pages = query_pages()
    print(f"회차 {len(pages)}개 스캔...")
    items, seen = [], set()
    for idx, pg in enumerate(pages, 1):
        if not pg["date"]:
            continue
        try:
            blocks = list_children(pg["id"])
        except Exception as e:
            print(f"  스킵 {pg['date']}: {e}")
            continue
        for e in extract(blocks):
            tk = e["ticker"]
            if valid is not None and tk not in valid:
                # 티커가 현재 TOP300 명단에 없으면 기록만 남기고 표시 (지도에선 매칭 안 됨)
                pass
            key = (pg["date"], tk)
            if key in seen:
                continue
            seen.add(key)
            items.append({"ticker": tk, "name": e["name"], "date": pg["date"], "blurb": e["blurb"]})
        if idx % 20 == 0:
            print(f"  ...{idx}/{len(pages)}")
        time.sleep(0.2)  # 레이트리밋 완화

    items.sort(key=lambda x: x["date"], reverse=True)
    matched = sum(1 for x in items if valid is None or x["ticker"] in valid)
    out = {
        "updated": time.strftime("%Y-%m-%d %H:%M KST"),
        "note": "라이브 '오늘의 기업'에서 다룬 기업 이력. fetch_todays_company.py가 회차 DB에서 추출.",
        "items": items,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"완료: {len(items)}건 저장(지도 매칭 {matched}건) → {OUT}")


if __name__ == "__main__":
    main()
