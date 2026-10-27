(function () {
  "use strict";

  const panel = document.querySelector('[data-role="removed-spans"]');
  const form = panel && panel.querySelector('form[data-role="removal"]');
  const pending = document.querySelector('[data-role="removal-pending-mark"]');

  function playheadNow() {
    const detail = document.querySelector('[data-role="detail-playhead"]');
    if (detail && Number.isFinite(Number(detail.dataset.playheadSeconds))) {
      return Number(detail.dataset.playheadSeconds);
    }
    const audio = document.querySelector('[data-role="preview-audio"]');
    return audio ? audio.currentTime : null;
  }

  function marksPending(seconds) {
    if (!pending) {
      return;
    }
    pending.hidden = false;
    pending.dataset.fromSeconds = String(seconds);
    document.dispatchEvent(new CustomEvent("removal:pending", { detail: { seconds } }));
  }

  if (form) {
    const start = form.querySelector('[data-field="mark-start-control"]');
    const from = form.querySelector('input[name="from"]');
    if (start && from) {
      start.addEventListener("click", function (event) {
        const seconds = playheadNow();
        if (seconds === null) {
          return;
        }
        event.preventDefault();
        from.value = formatsTimecode(seconds);
        marksPending(seconds);
      });
    }
  }

})();
