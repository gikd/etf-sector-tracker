/* 차트 복사 — 상세 모달의 일봉 차트를 헤더(종목·가격)+워터마크와 함께 PNG 카드로 만들어
   클립보드에 복사한다(이미지 붙여넣기용). 클립보드 미지원/거부 시 다운로드로 폴백. 3 페이지 공용.
   차트 SVG의 색은 CSS 변수라, 독립 SVG로 빼면 var() 해석이 안 되므로 실제 색값으로 치환한다. */

// 현재 모달의 차트 + 헤더를 합성한 PNG Blob 을 만든다(Promise<Blob>).
function buildCardBlob() {
  return new Promise((resolve, reject) => {
    const modal = document.getElementById("modal");
    const svg = modal && modal.querySelector("svg");
    if (!svg) { reject(new Error("no chart")); return; }

    const cs = getComputedStyle(document.documentElement);
    const g = (n, d) => (cs.getPropertyValue(n).trim() || d);
    const C = {
      paper: g("--paper", "#ffffff"), ink: g("--ink", "#111111"), muted: g("--muted", "#888888"),
      line: g("--line", "rgba(0,0,0,.15)"), up: g("--up", "#2f7d57"), down: g("--down", "#b5482b"),
      grid: g("--chart-grid", "rgba(0,0,0,.12)"), gridZero: g("--chart-grid-zero", "rgba(0,0,0,.34)"),
      axis: g("--chart-axis", "#888888"),
    };

    const vb = svg.viewBox && svg.viewBox.baseVal;
    const cw = vb && vb.width ? vb.width : (svg.clientWidth || 880);
    const ch = vb && vb.height ? vb.height : (svg.clientHeight || 360);
    const clone = svg.cloneNode(true);
    clone.setAttribute("width", cw);
    clone.setAttribute("height", ch);
    let s = new XMLSerializer().serializeToString(clone)
      .replace(/var\(--up\)/g, C.up).replace(/var\(--down\)/g, C.down)
      .replace(/var\(--chart-grid-zero\)/g, C.gridZero).replace(/var\(--chart-grid\)/g, C.grid)
      .replace(/var\(--chart-axis\)/g, C.axis);
    if (!/xmlns=/.test(s)) s = s.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');

    const head = modal.querySelector(".modal-head");
    const h3 = head && head.querySelector("h3");
    const name = h3 && h3.childNodes[0] ? (h3.childNodes[0].textContent || "").trim() : "";
    const sub = h3 && h3.querySelector("span") ? h3.querySelector("span").textContent.trim() : "";
    const pxEl = head && head.querySelector(".px");
    const price = pxEl ? pxEl.textContent.trim() : "";
    const retEl = pxEl ? pxEl.nextElementSibling : null;
    const ret = retEl ? retEl.textContent.trim() : "";
    const retColor = retEl && retEl.classList.contains("pos") ? C.up
                   : retEl && retEl.classList.contains("neg") ? C.down : C.muted;

    const SCALE = 2, W = 920, pad = 32, headH = 86, footH = 30;
    const chartW = W - pad * 2, chartH = Math.round(chartW * ch / cw);
    const H = pad + headH + chartH + footH;
    const cv = document.createElement("canvas");
    cv.width = W * SCALE; cv.height = H * SCALE;
    const x = cv.getContext("2d");
    x.scale(SCALE, SCALE);
    x.fillStyle = C.paper; x.fillRect(0, 0, W, H);

    const F = (w, px) => `${w} ${px}px Pretendard, "Pretendard Variable", "Apple SD Gothic Neo", sans-serif`;
    x.textBaseline = "alphabetic";
    x.fillStyle = C.ink; x.font = F(800, 26); x.fillText(name, pad, pad + 24);
    x.fillStyle = C.muted; x.font = F(400, 13); x.fillText(sub, pad, pad + 45);
    x.fillStyle = C.ink; x.font = F(700, 22); x.fillText(price, pad, pad + 76);
    const pw = x.measureText(price).width;
    x.fillStyle = retColor; x.font = F(700, 16); x.fillText(ret, pad + pw + 12, pad + 76);
    x.strokeStyle = C.line; x.lineWidth = 1;
    x.beginPath(); x.moveTo(pad, pad + headH - 6); x.lineTo(W - pad, pad + headH - 6); x.stroke();

    const url = URL.createObjectURL(new Blob([s], { type: "image/svg+xml;charset=utf-8" }));
    const img = new Image();
    img.onload = () => {
      x.drawImage(img, pad, pad + headH, chartW, chartH);
      URL.revokeObjectURL(url);
      x.fillStyle = C.muted; x.font = F(400, 11);
      x.fillText(`gikd.github.io/etf-sector-tracker · ${new Date().toISOString().slice(0, 10)}`, pad, H - 12);
      cv.toBlob((b) => (b ? resolve(b) : reject(new Error("toBlob failed"))), "image/png");
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("img error")); };
    img.src = url;
  });
}

function flashCap(msg) {
  const b = document.querySelector("#modal .cap-btn");
  if (!b) return;
  if (b.dataset.label == null) b.dataset.label = b.textContent;
  b.textContent = msg;
  clearTimeout(b._t);
  b._t = setTimeout(() => { b.textContent = b.dataset.label; }, 1600);
}

function downloadCard(b) {
  const span = document.querySelector("#modal .modal-head h3 span");
  const tk = ((span ? span.textContent : "").split("·")[0] || "chart").trim().replace(/[^\w.-]/g, "") || "chart";
  const a = document.createElement("a");
  a.href = URL.createObjectURL(b);
  a.download = `${tk}_${new Date().toISOString().slice(0, 10)}.png`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1500);
}

// 클립보드 복사(이미지). 미지원/거부 시 다운로드 폴백.
function captureChart() {
  const modal = document.getElementById("modal");
  if (!modal || !modal.querySelector("svg")) { alert("복사할 차트가 없습니다."); return; }

  const canClip = !!(navigator.clipboard && window.ClipboardItem && window.isSecureContext);
  if (canClip) {
    // Safari 호환: ClipboardItem 에 Promise<Blob> 를 동기적으로 전달(클릭 제스처 유지)
    navigator.clipboard.write([new ClipboardItem({ "image/png": buildCardBlob() })])
      .then(() => flashCap("복사됨 ✓"))
      .catch(() => buildCardBlob().then((b) => { downloadCard(b); flashCap("저장됨 ↓"); }).catch(() => flashCap("실패")));
    return;
  }
  buildCardBlob().then((b) => { downloadCard(b); flashCap("저장됨 ↓"); }).catch(() => flashCap("실패"));
}
window.captureChart = captureChart;
