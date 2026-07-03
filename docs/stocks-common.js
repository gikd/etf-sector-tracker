/* megacap.html · perspective.html 공용 — 통화 포맷 / 스파크라인 / 일봉 캔들 / 뉴스 / 모달 제어.
   (index.html 은 지표·차트 규격이 달라 자체 구현을 유지한다.)
   각 페이지는 renderModal() 과 byTicker 를 정의하고, 모달 상태(modalTicker/modalWin)는 여기서 공유. */

const CCY = {
  USD: { s: "$", d: 2 }, KRW: { s: "₩", d: 0 }, EUR: { s: "€", d: 2 },
  GBp: { s: "", d: 1, suf: "p" }, JPY: { s: "¥", d: 0 }, HKD: { s: "HK$", d: 2 },
  CNY: { s: "CN¥", d: 2 }, TWD: { s: "NT$", d: 1 }, SAR: { s: "﷼", d: 2 },
};
const WINDOWS = [{ d: 21, l: "1개월" }, { d: 63, l: "3개월" }, { d: 126, l: "6개월" }];

const fmt = v => v == null ? "–" : (v > 0 ? "+" : "") + v.toFixed(2) + "%";
const cls = v => v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "";
function fmtPx(v, ccy) {
  const c = CCY[ccy] || { s: "", d: 2 };
  return c.s + v.toLocaleString(undefined, { minimumFractionDigits: c.d, maximumFractionDigits: c.d }) + (c.suf || "");
}

function spark(values) {
  const min = Math.min(...values), max = Math.max(...values), range = max - min || 1;
  const pts = values.map((v, i) =>
    `${(i / (values.length - 1) * 100).toFixed(1)},${(34 - (v - min) / range * 30 - 2).toFixed(1)}`).join(" ");
  const up = values[values.length - 1] >= values[0];
  return `<svg viewBox="0 0 100 34" preserveAspectRatio="none"><polyline points="${pts}" fill="none" stroke="${up ? "var(--up)" : "var(--down)"}" stroke-width="1.6"/></svg>`;
}

/* 일봉 캔들 + 거래량 (색은 CSS 변수 → 테마 추종) */
function candleSVG(s, win) {
  const c = s.candles; if (!c) return "";
  const n = Math.min(win, c.c.length);
  const o = c.o.slice(-n), h = c.h.slice(-n), l = c.l.slice(-n), cl = c.c.slice(-n), v = c.v.slice(-n);
  const dates = s.dates.slice(-n);
  const W = 880, PH = 280, VH = 60, B = 24, T = 10, L = 6, R = 58;
  const H = T + PH + 8 + VH + B, pw = W - L - R;
  let pmin = Math.min(...l), pmax = Math.max(...h);
  const pad = (pmax - pmin) * 0.05 || 1; pmin -= pad; pmax += pad;
  const vmax = Math.max(...v, 1);
  const X = i => L + (i + 0.5) / n * pw, Y = p => T + (pmax - p) / (pmax - pmin) * PH;
  const cw = Math.max(1.5, pw / n * 0.62);
  const span = pmax - pmin;
  const step = [0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 5000, 50000].find(x => span / x <= 7) || 100000;
  let grid = "";
  for (let g = Math.ceil(pmin / step) * step; g <= pmax; g += step)
    grid += `<line x1="${L}" x2="${L + pw}" y1="${Y(g)}" y2="${Y(g)}" stroke="var(--chart-grid)"/><text x="${W - R + 6}" y="${Y(g) + 4}" fill="var(--chart-axis)" font-size="11">${g >= 1000 ? (g / 1000).toFixed(0) + "k" : g.toFixed(step < 1 ? 1 : 0)}</text>`;
  let xl = "";
  for (let k = 0; k <= 4; k++) { const i = Math.round(k / 4 * (n - 1));
    xl += `<text x="${X(i)}" y="${H - 6}" fill="var(--chart-axis)" font-size="11" text-anchor="${k === 0 ? "start" : k === 4 ? "end" : "middle"}">${dates[i]?.slice(5)}</text>`; }
  let body = "";
  for (let i = 0; i < n; i++) {
    const up = cl[i] >= o[i], col = up ? "var(--up)" : "var(--down)", x = X(i), yo = Y(o[i]), yc = Y(cl[i]);
    body += `<line x1="${x}" x2="${x}" y1="${Y(h[i])}" y2="${Y(l[i])}" stroke="${col}" stroke-width="1"/><rect x="${x - cw / 2}" y="${Math.min(yo, yc)}" width="${cw}" height="${Math.max(1, Math.abs(yo - yc))}" fill="${col}"/><rect x="${x - cw / 2}" y="${T + PH + 8 + (1 - v[i] / vmax) * VH}" width="${cw}" height="${v[i] / vmax * VH}" fill="${col}" opacity="0.45"/>`;
  }
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;display:block">${grid}${xl}<text x="${L}" y="${T + PH + 22}" fill="var(--chart-axis)" font-size="10.5">거래량</text>${body}</svg>`;
}

/* 관련 뉴스 블록 */
function newsHTML(s) {
  return `<div class="news"><h4>관련 뉴스 (최근 7일)</h4>
    <ul>${s.news && s.news.length ? s.news.map(nw => `<li><a href="${nw.u}" target="_blank" rel="noopener" title="${(nw.ot || "").replace(/"/g, "&quot;")}">${nw.t}</a>${nw.ot ? `<div class="orig">${nw.ot}</div>` : ""}<span class="src">${nw.s} · ${nw.d}</span></li>`).join("") : `<li style="color:var(--muted)">최근 뉴스가 없습니다.</li>`}</ul>
  </div>`;
}

/* 모달 제어 — renderModal()·byTicker 는 각 페이지가 정의(상태는 여기서 공유) */
let modalTicker = null, modalWin = 63;
function openModal(t) { modalTicker = t; modalWin = 63; renderModal(); document.getElementById("modal-bg").classList.add("open"); document.body.style.overflow = "hidden"; }
function closeModal() { document.getElementById("modal-bg").classList.remove("open"); document.body.style.overflow = ""; }
function setModalWin(d) { modalWin = d; renderModal(); }
document.getElementById("modal-bg").addEventListener("click", e => { if (e.target.id === "modal-bg") closeModal(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });
