(function () {
  "use strict";
  // Presentation preference travels with the URL. No browser or session data is stored.
  var root = document.documentElement;
  var params = new URLSearchParams(location.search);
  var theme = params.get("theme") === "light" ? "light" : "dark";
  root.setAttribute("data-theme", theme);
  function apply(choice, updateAddress) {
    theme = choice === "light" ? "light" : "dark";
    root.setAttribute("data-theme", theme);
    document.querySelectorAll("[data-theme-choice]").forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.getAttribute("data-theme-choice") === theme));
    });
    if (updateAddress) {
      var url = new URL(location.href);
      url.searchParams.set("theme", theme);
      history.replaceState(null, "", url.pathname + url.search + url.hash);
    }
  }
  function mount() {
    var group = document.querySelector(".theme-switch");
    if (!group) {
      var host = document.querySelector(".nav-actions") || document.querySelector(".rt-mast__right") || document.querySelector("header");
      if (!host) return;
      group = document.createElement("div");
      group.className = "theme-switch";
      group.setAttribute("role", "group");
      group.setAttribute("aria-label", "Color theme");
      var labels = {ne:["उज्यालो","गाढा"],hi:["हल्का","गहरा"],ja:["ライト","ダーク"],es:["Claro","Oscuro"],fr:["Clair","Sombre"],de:["Hell","Dunkel"]}[root.lang] || ["Light","Dark"];
      ["light", "dark"].forEach(function (choice, index) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "theme-choice";
        button.setAttribute("data-theme-choice", choice);
        button.textContent = labels[index];
        group.appendChild(button);
      });
      host.appendChild(group);
    }
    group.addEventListener("click", function (event) {
      var button = event.target.closest("button[data-theme-choice]");
      if (button) apply(button.getAttribute("data-theme-choice"), true);
    });
    apply(theme, false);
    function translateTheme() {
      var labels = {ne:["उज्यालो","गाढा"],hi:["हल्का","गहरा"],ja:["ライト","ダーク"],es:["Claro","Oscuro"],fr:["Clair","Sombre"],de:["Hell","Dunkel"]}[root.lang] || ["Light","Dark"];
      group.querySelectorAll("[data-theme-choice]").forEach(function (button) {
        button.textContent = labels[button.getAttribute("data-theme-choice") === "light" ? 0 : 1];
      });
    }
    new MutationObserver(translateTheme).observe(root, {attributes:true,attributeFilter:["lang"]});
    translateTheme();
    // Only product pages inherit presentation. Never rewrite identity-provider or API links.
    document.addEventListener("click", function (event) {
      var link = event.target.closest("a[href]");
      if (!link || link.hasAttribute("download")) return;
      var raw = link.getAttribute("href");
      if (!raw || raw.charAt(0) === "#") return;
      var url;
      try { url = new URL(link.href); } catch (_) { return; }
      var productOrigins = [location.origin,"https://cbsrm.wavervanir.com","https://app.cbsrm.wavervanir.com","https://mfi.cbsrm.wavervanir.com"];
      if (productOrigins.indexOf(url.origin) < 0 || !/^(https?:)$/.test(url.protocol)) return;
      if (url.pathname.indexOf("/auth/") === 0 || url.pathname.indexOf("/institutions/") === 0 || link.target === "_blank") return;
      if (url.pathname === "/" || url.pathname.indexOf("/app/") === 0 || /\.html$/.test(url.pathname)) {
        url.searchParams.set("theme", theme);
        link.href = url.href;
      }
    }, true);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
}());
