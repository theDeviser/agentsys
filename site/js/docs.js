(function () {
  document.querySelectorAll(".code-copy").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var pre = btn.parentElement && btn.parentElement.querySelector("pre code");
      if (!pre) return;
      navigator.clipboard.writeText(pre.textContent || "").then(function () {
        btn.textContent = "Copied";
        setTimeout(function () { btn.textContent = "Copy"; }, 1500);
      });
    });
  });

  var input = document.getElementById("docs-search");
  var box = document.getElementById("docs-search-results");
  if (!input || !box) return;

  var index = [];
  fetch("search-index.json")
    .then(function (r) { return r.json(); })
    .then(function (data) { index = data; })
    .catch(function () {});

  function render(q) {
    var ql = q.trim().toLowerCase();
    if (!ql) {
      box.hidden = true;
      return;
    }
    var hits = index.filter(function (e) {
      return (e.title + " " + e.text).toLowerCase().indexOf(ql) >= 0;
    }).slice(0, 8);
    if (!hits.length) {
      box.innerHTML = '<div style="padding:10px 14px;color:var(--fg-dim)">No results</div>';
      box.hidden = false;
      return;
    }
    box.innerHTML = hits.map(function (h) {
      return '<a href="' + h.slug + '"><strong>' + h.title + '</strong></a>';
    }).join("");
    box.hidden = false;
  }

  input.addEventListener("input", function () { render(input.value); });
  input.addEventListener("focus", function () { render(input.value); });
  document.addEventListener("click", function (e) {
    if (!box.contains(e.target) && e.target !== input) box.hidden = true;
  });

  document.addEventListener("keydown", function (e) {
    var tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || e.target.isContentEditable) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        input.focus();
      }
      return;
    }
    if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      input.focus();
    }
    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
      e.preventDefault();
      input.focus();
    }
  });
})();
