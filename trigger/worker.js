// Cloudflare Worker — ETF 트래커 + 추세 워치리스트 데이터 갱신 '외부 트리거'
//
// 왜 필요한가:
//   GitHub Actions 의 schedule(cron) 은 공개/무료 저장소에서 예약 실행의 상당수(관측상 ~70%)를
//   '드롭'한다. 특히 미국장 개장 시각대가 가장 심해서 개장 직후 데이터가 1~2시간 늦게 잡힌다.
//   반면 workflow_dispatch(on-demand) 트리거는 이 쓰로틀의 영향을 받지 않고 수초 내 실행된다.
//   그래서 '정확한 개장/마감 시각'에 이 워커가 대상 워크플로를 깨운다.
//
// 동작:
//   wrangler.toml 의 cron 시각마다 scheduled() 가 호출되고, 발사된 cron 표현식(event.cron)으로
//   대상 저장소를 라우팅해 GitHub API 로 workflow_dispatch 한다.
//   휴장/중복 발사는 무해하다 — 각 워크플로는 데이터가 실제로 바뀐 경우에만 커밋한다(diff 가드).

const OWNER = "gikd";
const REF = "main";

const TARGETS = {
  etf: { repo: "etf-sector-tracker", workflow: "update.yml" },
  trend: { repo: "trend", workflow: "scan.yml" },
};

// cron 표현식 → 대상. 여기 없는 크론은 etf(기존 동작)로 간다.
const CRON_ROUTES = {
  "0 7 * * 1-5": "trend", // 16:00 KST 장 마감 스캔
};

async function dispatch(env, target) {
  const { repo, workflow } = TARGETS[target] || TARGETS.etf;
  const url = `https://api.github.com/repos/${OWNER}/${repo}/actions/workflows/${workflow}/dispatches`;
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
  // cron 시각마다 호출 — 해당 크론에 매핑된 워크플로 즉시 실행 요청
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env, CRON_ROUTES[event.cron] || "etf"));
  },

  // 수동 트리거: ?key=<TRIGGER_KEY> 가 일치할 때만 발사한다. ?repo=trend 로 대상 선택(기본 etf).
  // 키 없음/불일치(favicon 등 잡요청 포함)는 무시(403). cron 자동 갱신은 이 경로를 쓰지 않음.
  async fetch(request, env) {
    const params = new URL(request.url).searchParams;
    const key = params.get("key");
    if (!env.TRIGGER_KEY || key !== env.TRIGGER_KEY) {
      return new Response("forbidden — 올바른 ?key= 가 필요합니다.\n", { status: 403 });
    }
    const target = params.get("repo") || "etf";
    if (!TARGETS[target]) {
      return new Response(`unknown repo — ${Object.keys(TARGETS).join(", ")} 중 하나.\n`, { status: 400 });
    }
    const res = await dispatch(env, target);
    const ok = res.status === 204;
    const body = ok
      ? `dispatched ✓ — ${TARGETS[target].repo}/${TARGETS[target].workflow} 실행을 요청했습니다.\n`
      : `failed: ${res.status}\n${await res.text()}\n`;
    return new Response(body, { status: ok ? 200 : 502 });
  },
};
