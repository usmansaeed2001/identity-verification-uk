// Demo-only helpers. Event delegation, so they keep working after htmx swaps the page.
(function () {
  // Show the captured photo locally. It is never uploaded: the inputs have no name attribute.
  document.addEventListener("change", function (event) {
    var input = event.target;
    if (!input.matches || !input.matches("input[type=file][data-preview]")) return;
    var img = document.getElementById(input.dataset.preview);
    var file = input.files && input.files[0];
    if (!img || !file) return;
    if (img.src) URL.revokeObjectURL(img.src);
    img.src = URL.createObjectURL(file);
    img.hidden = false;
  });

  // Group share codes as "W12 3AB C45" while typing.
  document.addEventListener("input", function (event) {
    var input = event.target;
    if (input.id !== "share_code") return;
    var raw = input.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 9);
    input.value = raw.replace(/(.{3})(?=.)/g, "$1 ");
  });

  // Start page: show the chosen scenario's description and hide scenarios that don't fit the route.
  function syncScenario() {
    var select = document.getElementById("scenario");
    if (!select) return;
    var route = (document.querySelector("input[name=route]:checked") || {}).value;
    Array.prototype.forEach.call(select.options, function (option) {
      var fits = option.dataset.routes.split(",").indexOf(route) !== -1;
      option.disabled = !fits;
      if (!fits && option.selected) select.value = "all_pass";
    });
    document.querySelectorAll("#scenario-notes li").forEach(function (li) {
      li.hidden = li.dataset.key !== select.value;
    });
  }
  // Real mode: hide the mock scenario and allow the share code route only.
  function syncMode() {
    var live = document.getElementById("mode-live");
    if (!live) return;
    var isLive = live.checked;
    document.querySelectorAll("[data-mock-only]").forEach(function (el) { el.hidden = isLive; });
    document.querySelectorAll("[data-mode-hint]").forEach(function (el) {
      el.hidden = el.dataset.modeHint !== (isLive ? "live" : "mock");
    });
    var british = document.getElementById("route-british");
    if (british) {
      british.disabled = isLive;
      if (isLive && british.checked) document.getElementById("route-share").checked = true;
    }
  }
  function syncStart() { syncMode(); syncScenario(); }
  document.addEventListener("change", function (event) {
    if (event.target.id === "scenario" || event.target.name === "route" || event.target.name === "mode") syncStart();
  });
  document.addEventListener("DOMContentLoaded", syncStart);
  document.addEventListener("htmx:load", syncStart);
})();
