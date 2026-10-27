(function () {
  "use strict";

  const section = document.querySelector('[data-role="listen"]');
  const audio = document.querySelector('[data-role="preview-audio"]');
  const marker = (section || document).querySelector('[data-role="playhead-marker"]');
  const readout = document.querySelector('[data-field="listen-playhead"]');
  if (!section || !audio) {
    return;
  }

  const recordingId = section.dataset.recording;
  const declaredLength = Number(audio.dataset.duration) || 0;
  let stopAt = null;
  let auditioning = null;

  function length() {
    return Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : declaredLength;
  }

  function showPosition(seconds) {
    if (marker) {
      const span = length();
      marker.dataset.seconds = String(seconds);
      marker.style.left = span ? `${(100 * seconds) / span}%` : "0%";
    }
    if (readout) {
      readout.textContent = formatsTimecode(seconds);
    }
    document.dispatchEvent(new CustomEvent("audio:timeupdate", { detail: { seconds } }));
  }

  function seekTo(seconds) {
    const span = length();
    const wanted = Math.max(0, span ? Math.min(seconds, span) : seconds);
    audio.currentTime = wanted;
    showPosition(wanted);
  }

  function reportPosition() {
    if (!recordingId || !window.fetch) {
      return;
    }
    fetch(`/api/recordings/${recordingId}/seek`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seconds: audio.currentTime }),
    }).catch(function () {});
  }

  function announce(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail }));
  }

  function endAudition() {
    if (auditioning === null) {
      return;
    }
    const ended = auditioning;
    auditioning = null;
    announce("preview:ended", { boundary: ended });
  }

  function playWindow(boundary, start, end) {
    stopAt = end;
    seekTo(start);
    if (boundary !== auditioning) {
      endAudition();
    }
    if (boundary !== null) {
      auditioning = boundary;
      announce("preview:started", {
        boundary,
        from: start,
        to: end,
      });
    }
    const started = audio.play();
    if (started && started.catch) {
      started.catch(function () {});
    }
  }

  audio.addEventListener("timeupdate", function () {
    showPosition(audio.currentTime);
    if (stopAt === null || audio.currentTime < stopAt) {
      return;
    }
    stopAt = null;
    audio.pause();
    endAudition();
    reportPosition();
  });

  audio.addEventListener("seeked", reportPosition);
  audio.addEventListener("pause", reportPosition);
  audio.addEventListener("play", function () {
    if (stopAt !== null && audio.currentTime >= stopAt) {
      stopAt = null;
    }
  });

  document.addEventListener("waveform:transport", function () {
    if (!audio.paused) {
      audio.pause();
      return;
    }
    const shown = Number(marker && marker.dataset.seconds);
    if (Number.isFinite(shown) && Math.abs(shown - audio.currentTime) > 0.05) {
      audio.currentTime = shown;
    }
    const started = audio.play();
    if (started && started.catch) {
      started.catch(function () {});
    }
  });

  const toggle = document.querySelector('[data-role="transport-toggle"]');
  if (toggle) {
    toggle.addEventListener("click", function () {
      document.dispatchEvent(new CustomEvent("waveform:transport"));
    });
    const reflectsTransport = function () {
      toggle.dataset.transport = audio.paused ? "paused" : "playing";
      toggle.setAttribute("aria-label", audio.paused ? "Play" : "Pause");
    };
    audio.addEventListener("play", reflectsTransport);
    audio.addEventListener("pause", reflectsTransport);
  }

  document.addEventListener("waveform:play-window", function (event) {
    const asked = event.detail || {};
    playWindow(null, Number(asked.start), Number(asked.end));
  });

  document.addEventListener("waveform:seek", function (event) {
    const asked = event.detail || {};
    stopAt = null;
    endAudition();
    seekTo(Number(asked.seconds) || 0);
    if (asked.play) {
      const started = audio.play();
      if (started && started.catch) {
        started.catch(function () {});
      }
    }
  });

  const controls = '[data-role="preview-cue-excerpt"], [data-role="start-at-block"]';
  document.querySelectorAll(controls).forEach(function (control) {
    control.addEventListener("click", function () {
      const data = control.dataset;
      if (data.kind === "seek") {
        playWindow(null, Number(data.start), null);
        return;
      }
      playWindow(data.kind, Number(data.start), Number(data.end));
    });
  });

  document.addEventListener("seam:position", function (event) {
    showPosition(event.detail.seconds);
  });

  const track = document.querySelector('[data-role="playback-track"]');
  if (track) {
    track.addEventListener("click", function (event) {
      const box = track.getBoundingClientRect();
      if (!box.width) {
        return;
      }
      stopAt = null;
      endAudition();
      seekTo(((event.clientX - box.left) / box.width) * length());
    });
  }

  showPosition(Number(marker && marker.dataset.seconds) || 0);
})();
