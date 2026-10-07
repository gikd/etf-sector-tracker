#!/bin/zsh
# 라이브 '오늘의 기업' → 메가캡 지도 데이터 매일 갱신
# 라이브 발행(평일 09:06) 이후 실행. 토큰은 ~/weekly-review/.env.local 에서 읽는다(값 노출 없음).
# com.myosu.todayscompany LaunchAgent 가 평일 09:30 에 호출.
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin"
REPO="$HOME/etf-sector-tracker"
ENVF="$HOME/weekly-review/.env.local"
cd "$REPO"

ts() { date "+%Y-%m-%d %H:%M:%S"; }
echo "[$(ts)] todays_company 갱신 시작"

if [ ! -f "$ENVF" ] || ! grep -q '^NOTION_TOKEN=' "$ENVF"; then
  echo "[$(ts)] NOTION_TOKEN 없음($ENVF) — 중단"; exit 1
fi

# 원격 최신화(일일 데이터 푸시와 충돌 방지)
git pull --rebase --autostash origin main >/dev/null 2>&1 || { echo "[$(ts)] pull 실패"; exit 1; }

NOTION_TOKEN="$(grep -m1 '^NOTION_TOKEN=' "$ENVF" | cut -d= -f2-)" python3 fetch_todays_company.py

if git diff --quiet -- docs/todays_company.json; then
  echo "[$(ts)] 변경 없음 — 커밋 생략"; exit 0
fi

git add docs/todays_company.json
git commit -q -m "data: 오늘의 기업 자동 갱신 ($(date +%F))" \
  -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git push -q origin main && echo "[$(ts)] 푸시 완료" || { echo "[$(ts)] 푸시 실패"; exit 1; }
