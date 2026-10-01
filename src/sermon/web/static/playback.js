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
  let queued = [];
  let auditioning = null;

  function length() {
    return Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : declaredLength;
  }

  function precise(seconds) {
    const whole = Math.max(0, seconds);
    const hours = Math.floor(whole / 3600);
    const minutes = Math.floor((whole % 3600) / 60);
    const rest = (whole % 60).toFixed(2).padStart(5, "0");
    return `${hours}:${String(minutes).padStart(2, "0")}:${rest}`;
  }

  function showPosition(seconds) {
    if (marker) {
      const span = length();
      marker.dataset.seconds = String(seconds);
      marker.style.left = span ? `${(100 * seconds) / span}%` : "0%";
    }
    if (readout) {
      readout.textContent = precise(seconds);
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

  const boundaries = {};
  document.querySelectorAll('[data-role^="preview-"][data-at]').forEach(function (control) {
    boundaries[control.dataset.kind] = Number(control.dataset.at);
  });

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

  function playWindow(boundary, start, end, rest) {
    queued = rest || [];
    stopAt = end;
    seekTo(start);
    if (boundary !== auditioning) {
      endAudition();
    }
    if (boundary !== null) {
      auditioning = boundary;
      announce("preview:started", {
        boundary,
        seconds: boundaries[boundary],
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
    const next = queued.shift();
    if (next) {
      playWindow(next[2], next[0], next[1], queued);
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
    const started = audio.play();
    if (started && started.catch) {
      started.catch(function () {});
    }
  });

  document.addEventListener("waveform:seek", function (event) {
    const asked = event.detail || {};
    stopAt = null;
    queued = [];
    endAudition();
    seekTo(Number(asked.seconds) || 0);
    if (asked.play) {
      const started = audio.play();
      if (started && started.catch) {
        started.catch(function () {});
      }
    }
  });

  const controls = '[data-role^="preview-"][data-kind], [data-role="start-at-block"]';
  document.querySelectorAll(controls).forEach(function (control) {
    control.addEventListener("click", function () {
      const data = control.dataset;
      if (data.kind === "cut") {
        playWindow("punch-in", Number(data.inStart), Number(data.inEnd), [
          [Number(data.outStart), Number(data.outEnd), "punch-out"],
        ]);
        return;
      }
      if (data.kind === "seek") {
        playWindow(null, Number(data.start), null, []);
        return;
      }
      playWindow(data.kind, Number(data.start), Number(data.end), []);
    });
  });

  const track = document.querySelector('[data-role="playback-track"]');
  if (track) {
    track.addEventListener("click", function (event) {
      const box = track.getBoundingClientRect();
      if (!box.width) {
        return;
      }
      stopAt = null;
      queued = [];
      endAudition();
      seekTo(((event.clientX - box.left) / box.width) * length());
    });
  }

  showPosition(Number(marker && marker.dataset.seconds) || 0);
})();
