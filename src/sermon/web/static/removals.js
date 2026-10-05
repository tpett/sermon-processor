(function () {
  "use strict";

  const panel = document.querySelector('[data-role="removed-spans"]');
  if (!panel) {
    return;
  }
  const form = panel.querySelector('form[data-role="removal"]');
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

  let hearing = null;
  panel.querySelectorAll('[data-role="hear-join"]').forEach(function (control) {
    control.addEventListener("click", function () {
      const preview = document.querySelector('[data-role="preview-audio"]');
      if (preview && !preview.paused) {
        preview.pause();
      }
      if (hearing) {
        hearing.pause();
      }
      hearing = new Audio(control.dataset.url);
      control.dataset.playing = "true";
      hearing.addEventListener("ended", function () {
        delete control.dataset.playing;
      });
      const started = hearing.play();
      if (started && started.catch) {
        started.catch(function () {
          delete control.dataset.playing;
        });
      }
    });
  });
})();
