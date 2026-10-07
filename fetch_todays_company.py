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

# 묘수 라이브 '회차' 데이터베이스 ID (REST API는 DB id — data source id 아님)
DB_ID = "9fd6618e-b67f-40b4-95e8-057ee3fcde6f"
TOKEN = os.environ.get("NOTION_TOKEN", "")
API = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": "Bearer " + TOKEN,
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# 괄호 안 내용에서 티커 후보 파싱 (영문 티커 또는 KR/JP 숫자 티커)
PARENS_RE = re.compile(r"\(([^)]{1,40})\)")
def parse_ticker(parens_content):
    for tok in re.split(r"[^A-Za-z0-9.\-]+", parens_content):
        # 영문 티커만 인정(KR/JP 숫자 티커는 300 명단이 .KS/.T 접미사라 매칭 불가 + 연도 오탐 방지)
        if re.fullmatch(r"[A-Z]{1,6}(?:[.\-][A-Z0-9]{1,4})?", tok) and not tok.isdigit():
            return tok
    return None


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


def _clean_name(s):
    s = s.lstrip(":：").strip()
    s = re.split(r"[(（·,]", s)[0].strip()
    return s

def _is_stats(t):
    return (t.startswith("트래커") or t.startswith(";") or t.startswith("；")
            or "상대강도" in t or "종가" in t
            or re.match(r"^\d{1,2}월", t) is not None)

def extract(page_blocks, name_map=None):
    """'오늘의 기업' 섹션들을 (ticker, name, blurb)로. 포맷 변주 대응."""
    name_map = name_map or {}
    found = []
    blocks = page_blocks
    for i, b in enumerate(blocks):
        if not b.get("type", "").startswith("heading"):
            continue
        if rich_text(b).strip() != "오늘의 기업":
            continue
        # 헤더 다음 ~8개 텍스트 블록(이미지·빈블록·'출처' 제외)
        texts = []
        for nb in blocks[i + 1:]:
            if nb["type"] in ("paragraph", "heading_1", "heading_2", "heading_3"):
                t = rich_text(nb).strip()
                if t and t != "출처":
                    texts.append(t)
            if len(texts) >= 8:
                break
        if not texts:
            continue
        # 회사 라인 = 괄호 티커가 있거나 이름맵에 걸리는 첫 줄
        ticker, name, comp_idx = None, "", -1
        for j, t in enumerate(texts):
            for m in PARENS_RE.finditer(t):
                tk = parse_ticker(m.group(1))
                if tk:
                    ticker = tk
                    name = t[: m.start()].strip().rstrip("(（").strip() or _clean_name(t)
                    comp_idx = j
                    break
            if ticker:
                break
            nm = _clean_name(t)
            if nm and nm in name_map:
                ticker, name, comp_idx = name_map[nm], nm, j
                break
        if not ticker:
            continue
        # 요약 = 회사 라인 이후 첫 산문 문장(통계·사견·날짜 줄 제외)
        blurb = ""
        for t in texts[comp_idx + 1:]:
            if len(t) >= 12 and not _is_stats(t):
                blurb = t
                break
        if not blurb:
            after = texts[comp_idx].split("·", 1)
            if len(after) > 1 and len(after[1].strip()) >= 12:
                blurb = after[1].strip()
        found.append({"ticker": ticker, "name": name or ticker, "blurb": blurb})
    return found


def main():
    if not TOKEN:
        raise SystemExit("NOTION_TOKEN 환경변수가 필요합니다.")
    valid, name_map = None, {}
    if UNIVERSE.exists():
        uni = json.loads(UNIVERSE.read_text())
        valid = {m["ticker"] for m in uni.get("members", [])}
        for m in uni.get("members", []):
            nm = re.split(r"[(（]", m["name"])[0].strip()   # '알파벳(구글)' → '알파벳'
            if nm:
                name_map.setdefault(nm, m["ticker"])

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
        for e in extract(blocks, name_map):
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
