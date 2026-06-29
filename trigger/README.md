# ETF 트래커 데이터 갱신 — 외부 트리거 (Cloudflare Worker)

GitHub Actions 의 `schedule(cron)` 은 공개 저장소에서 예약 실행을 자주 누락한다(특히 미국장 개장).
이 워커가 **정확한 개장/마감 시각**에 `update.yml` 을 `workflow_dispatch` 로 깨워서, 그 두 시점의 데이터가 항상 갱신되게 한다. on-demand dispatch 는 schedule 쓰로틀의 영향을 받지 않는다.

기존 GitHub cron 은 그대로 둔다 — 장중 신선도용 '무료 백업'으로 둔다(잡히면 좋고, 안 잡혀도 이 워커가 개장/마감을 보장).

## 발사 시각 (`wrangler.toml`)
| 시점 | 현지시각 | UTC cron |
|---|---|---|
| 한국장 개장 | 09:05 KST | `5 0 * * 1-5` |
| 한국장 마감 | 15:35 KST | `35 6 * * 1-5` |
| 미국장 개장 | 09:35 ET | `35 13,14 * * 1-5` (서머 13:35 / 윈터 14:35) |
| 미국장 마감 | 16:05 ET | `5 20,21 * * 1-5` (서머 20:05 / 윈터 21:05) |

미국은 서머/윈터 두 시각 모두 발사한다. 비해당 시각 발사는 무해 — `update.yml` 은 데이터가 실제로 바뀐 경우에만 커밋한다.

## 1회 설정 (약 10분)

### 1) GitHub 토큰 발급 (fine-grained, 이 저장소 전용)
1. https://github.com/settings/personal-access-tokens/new
2. **Resource owner**: `gikd` · **Repository access** → *Only select repositories* → `etf-sector-tracker`
3. **Permissions** → *Repository permissions* → **Actions: Read and write** (이거 하나면 됨)
4. Generate → 토큰 문자열 복사 (`github_pat_...`)

> 권한이 이 저장소의 Actions 실행 하나로 제한되므로, 새어도 피해 범위는 "ETF 데이터 새로고침"뿐.

### 2) 워커 배포
```bash
cd trigger
npx wrangler login                 # 브라우저 OAuth (Cloudflare 계정 — R2 쓰는 그 계정)
npx wrangler secret put GH_TOKEN     # GitHub fine-grained PAT 붙여넣기
npx wrangler secret put TRIGGER_KEY  # 수동 트리거 URL 잠금용 비밀키(아무 문자열)
npx wrangler deploy
```

### 3) 동작 확인
- cron 자동 갱신은 URL 과 무관하게 동작(개장/마감 4회). 아래는 수동 트리거용.
- **키 게이트**: 워커 URL 은 `?key=<TRIGGER_KEY>` 가 맞아야만 발사한다. 키 없으면 403(무시).
  - `https://etf-trigger.<계정>.workers.dev/?key=<TRIGGER_KEY>` → `dispatched ✓`
  - 키 없이/틀리게 열면 `403 forbidden` — 아무 일도 안 일어남(favicon 등 잡요청 차단).
- 발사 후 https://github.com/gikd/etf-sector-tracker/actions 에 `workflow_dispatch` 실행이 뜨면 성공.

## 대안: 배포 없이 (cron-job.org)
Cloudflare 가 번거로우면 https://cron-job.org (무료, 타임존 인식) 에 잡 4개를 만들어도 동일하다.
- URL: `https://api.github.com/repos/gikd/etf-sector-tracker/actions/workflows/update.yml/dispatches`
- Method `POST`, Body `{"ref":"main"}`
- Headers: `Authorization: Bearer <토큰>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, `User-Agent: etf-trigger`
- 스케줄: 잡별 타임존을 `America/New_York`(09:35·16:05) / `Asia/Seoul`(09:05·15:35) 로 두면 서머타임 자동 처리.
