(function () {
  "use strict";

  // Fallback guard for touch devices: block horizontal gesture drift
  // that can trigger browser back/forward navigation on edge swipes.
  var startX = 0;
  var startY = 0;
  var hasStart = false;

  document.addEventListener(
    "touchstart",
    function (event) {
      if (!event.touches || event.touches.length !== 1) {
        hasStart = false;
        return;
      }

      startX = event.touches[0].clientX;
      startY = event.touches[0].clientY;
      hasStart = true;
    },
    { passive: true }
  );

  document.addEventListener(
    "touchmove",
    function (event) {
      if (!hasStart || !event.touches || event.touches.length !== 1) {
        return;
      }

      var currentX = event.touches[0].clientX;
      var currentY = event.touches[0].clientY;
      var deltaX = currentX - startX;
      var deltaY = currentY - startY;

      // Prevent only predominantly horizontal swipes.
      if (Math.abs(deltaX) > Math.abs(deltaY) + 6) {
        event.preventDefault();
      }
    },
    { passive: false }
  );
})();
