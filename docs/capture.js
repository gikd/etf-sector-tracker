/* 차트 캡처 — 상세 모달의 일봉 차트를 헤더(종목·가격)와 함께 PNG 카드로 저장. 3 페이지 공용.
   차트는 SVG라 색이 CSS 변수(var(--up) 등)인데, 독립 SVG 로 빼면 var() 해석이 안 되므로
   직렬화 후 실제 색값으로 치환한다. 외부 리소스 없는 순수 도형/텍스트라 canvas 오염 없음. */
async function captureChart() {
  const modal = document.getElementById("modal");
  const svg = modal && modal.querySelector("svg");
  if (!svg) { alert("저장할 차트가 없습니다."); return; }

  const cs = getComputedStyle(document.documentElement);
  const g = (n, d) => (cs.getPropertyValue(n).trim() || d);
  const C = {
    paper: g("--paper", "#ffffff"), ink: g("--ink", "#111111"), muted: g("--muted", "#888888"),
    line: g("--line", "rgba(0,0,0,.15)"), up: g("--up", "#2f7d57"), down: g("--down", "#b5482b"),
    grid: g("--chart-grid", "rgba(0,0,0,.12)"), gridZero: g("--chart-grid-zero", "rgba(0,0,0,.34)"),
    axis: g("--chart-axis", "#888888"),
  };

  // SVG 직렬화 + 변수색 인라인
  const vb = svg.viewBox && svg.viewBox.baseVal;
  const cw = vb && vb.width ? vb.width : (svg.clientWidth || 880);
  const ch = vb && vb.height ? vb.height : (svg.clientHeight || 360);
  const clone = svg.cloneNode(true);
  clone.setAttribute("width", cw);
  clone.setAttribute("height", ch);
  let s = new XMLSerializer().serializeToString(clone);
  s = s.replace(/var\(--up\)/g, C.up)
       .replace(/var\(--down\)/g, C.down)
       .replace(/var\(--chart-grid-zero\)/g, C.gridZero)
       .replace(/var\(--chart-grid\)/g, C.grid)
       .replace(/var\(--chart-axis\)/g, C.axis);
  if (!/xmlns=/.test(s)) s = s.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');

  // 헤더 텍스트
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

  // 카드 캔버스
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

  const blob = new Blob([s], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const img = new Image();
  img.onload = () => {
    x.drawImage(img, pad, pad + headH, chartW, chartH);
    URL.revokeObjectURL(url);
    const today = new Date().toISOString().slice(0, 10);
    x.fillStyle = C.muted; x.font = F(400, 11);
    x.fillText(`gikd.github.io/etf-sector-tracker · ${today}`, pad, H - 12);
    const tk = (sub.split("·")[0] || "chart").trim().replace(/[^\w.-]/g, "") || "chart";
    cv.toBlob((b) => {
      if (!b) { alert("이미지 생성 실패"); return; }
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b);
      a.download = `${tk}_${today}.png`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1500);
    }, "image/png");
  };
  img.onerror = () => { URL.revokeObjectURL(url); alert("차트 렌더 실패"); };
  img.src = url;
}
window.captureChart = captureChart;
