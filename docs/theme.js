/* 테마 토글 — .theme-cream(새) ↔ .theme-dark(기존), localStorage 영속 (3 페이지 공용)
   <head> 의 인라인 스니펫이 페인트 전에 클래스를 먼저 박아 FOUC 를 막는다.
   각 페이지는 차트 재그리기를 위해 window.__rerender 를 정의해 둔다(선택). */
(function () {
  var KEY = "etf-theme";
  function current() {
    return document.documentElement.classList.contains("theme-dark") ? "theme-dark" : "theme-cream";
  }
  function label(t) { return t === "theme-dark" ? "◐ 페이퍼" : "☾ 다크"; }  // 누르면 갈 곳
  function apply(t) {
    document.documentElement.className = t;
    try { localStorage.setItem(KEY, t); } catch (e) {}
    var b = document.getElementById("theme-toggle-btn");
    if (b) b.textContent = label(t);
    if (typeof window.__rerender === "function") window.__rerender();
  }
  function init() {
    var nav = document.querySelector(".nav");
    if (nav && !document.getElementById("theme-toggle-btn")) {
      var b = document.createElement("button");
      b.id = "theme-toggle-btn";
      b.className = "theme-toggle";
      b.type = "button";
      b.setAttribute("aria-label", "테마 전환");
      b.textContent = label(current());
      b.onclick = function () { apply(current() === "theme-dark" ? "theme-cream" : "theme-dark"); };
      nav.appendChild(b);
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
