// Copy buttons on the Library's approved bullets. The only script besides htmx; no inline JS (CSP).
// The portal is plain http over Tailscale, which is not a "secure context", so navigator.clipboard
// is usually missing; fall back to a hidden textarea + execCommand("copy").
function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
  return new Promise(function (resolve, reject) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "-1000px";
    document.body.appendChild(ta);
    ta.select();
    ta.setSelectionRange(0, text.length);
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    document.body.removeChild(ta);
    ok ? resolve() : reject();
  });
}

document.addEventListener("click", function (e) {
  var b = e.target.closest("button.copy");
  if (!b) return;
  copyText(b.getAttribute("data-text") || "").then(function () {
    b.textContent = "Copied";
    setTimeout(function () { b.textContent = "Copy"; }, 1200);
  }, function () { b.textContent = "Copy failed"; });
});
