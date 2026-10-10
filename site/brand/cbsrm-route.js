(function () {
  "use strict";
  var route = document.querySelector('meta[name="cbsrm-route"]');
  if (!route) return;
  var target = new URL(route.content, location.href);
  var theme = new URLSearchParams(location.search).get("theme");
  if (theme === "dark" || theme === "light") target.searchParams.set("theme", theme);
  var fragment = new URLSearchParams(location.hash.slice(1));
  var lang = fragment.get("lang");
  if (lang && /^(en|ne|hi|ja|es|fr|de)$/.test(lang)) {
    var destination = new URLSearchParams(target.hash.slice(1));
    destination.set("lang", lang);
    target.hash = destination.toString();
  }
  location.replace(target.href);
}());
