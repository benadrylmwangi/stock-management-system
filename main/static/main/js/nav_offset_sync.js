(function () {
  "use strict";

  function syncNavOffset() {
    var navShell = document.querySelector(".nav-shell");
    if (!navShell) {
      return;
    }

    var navHeight = Math.ceil(
      navShell.getBoundingClientRect().height || navShell.offsetHeight || 0
    );

    if (navHeight > 0) {
      document.documentElement.style.setProperty("--nav-offset", navHeight + "px");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    syncNavOffset();

    var collapse = document.getElementById("navbarSupportedContent");
    if (collapse) {
      ["shown.bs.collapse", "hidden.bs.collapse"].forEach(function (eventName) {
        collapse.addEventListener(eventName, function () {
          // Wait one frame for collapse height animation updates.
          window.requestAnimationFrame(syncNavOffset);
        });
      });
    }
  });

  window.addEventListener("load", syncNavOffset);
  window.addEventListener("resize", syncNavOffset);
})();
