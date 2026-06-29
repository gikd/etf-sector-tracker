// Cloudflare Worker — ETF 트래커 데이터 갱신 '외부 트리거'
//
// 왜 필요한가:
//   GitHub Actions 의 schedule(cron) 은 공개/무료 저장소에서 예약 실행의 상당수(관측상 ~70%)를
//   '드롭'한다. 특히 미국장 개장 시각대가 가장 심해서 개장 직후 데이터가 1~2시간 늦게 잡힌다.
//   반면 workflow_dispatch(on-demand) 트리거는 이 쓰로틀의 영향을 받지 않고 수초 내 실행된다.
//   그래서 '정확한 개장/마감 시각'에 이 워커가 update.yml 을 깨운다.
//
// 동작:
//   wrangler.toml 의 cron 시각마다 scheduled() 가 호출되고, GitHub API 로 update.yml 을 dispatch 한다.
//   휴장/중복 발사는 무해하다 — update.yml 은 데이터가 실제로 바뀐 경우에만 커밋한다(diff 가드).

const OWNER = "gikd";
const REPO = "etf-sector-tracker";
const WORKFLOW = "update.yml";
const REF = "main";

async function dispatch(env) {
  const url = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;
  return fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "etf-trigger-worker",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: REF }),
  });
}

export default {
  // cron 시각마다 호출 — update.yml 즉시 실행 요청
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env));
  },

  // 수동 테스트용: 워커 URL 을 브라우저로 열면 즉시 한 번 트리거하고 결과를 보여줌
  async fetch(request, env) {
    const res = await dispatch(env);
    const ok = res.status === 204;
    const body = ok
      ? "dispatched ✓ — update.yml 실행을 요청했습니다.\n"
      : `failed: ${res.status}\n${await res.text()}\n`;
    return new Response(body, { status: ok ? 200 : 502 });
  },
};
