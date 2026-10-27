// The cut light: which side of a boundary the audio is on, right now.
//
// Driven by requestAnimationFrame rather than the audio element's "timeupdate",
// because timeupdate fires about four times a second. A light that can be 250 ms
// late is worse than no light at all here -- the reviewer is judging whether a
// word starts before or after the cut, and 250 ms is most of a syllable. rAF
// reads currentTime directly at frame rate, so the state changes within ~16 ms
// of the instant.
//
// The server renders the same state for the stored playhead, so the light is
// correct on load and without JavaScript. This file only makes it live.
(function () {
  "use strict";

  const light = document.querySelector('[data-role="cut-light"]');
  if (!light) {
    return;
  }

  const audio = document.querySelector('[data-role="preview-audio"]');
  const lamp = light.querySelector('[data-role="cut-lamp"]');
  const fields = {};
  light.querySelectorAll("[data-field]").forEach(function (node) {
    fields[node.dataset.field] = node;
  });

  const tolerance = Number(light.dataset.tolerance) || 0.05;
  let boundary = light.dataset.boundary;
  let at = Number(light.dataset.at);
  let discards = light.dataset.discards;
  let keeps = light.dataset.keeps;
  let running = false;
  let clock = null;
  let frame = null;

  function signed(seconds) {
    if (Math.abs(seconds) < 0.005) {
      return "0.00 s";
    }
    // U+2212, matching formats_signed() on the server.
    const sign = seconds > 0 ? "+" : "−";
    return sign + Math.abs(seconds).toFixed(2) + " s";
  }

  function sideFor(state) {
    if (state === "at") {
      return "on the cut";
    }
    return state + " the cut" === keeps ? "kept" : "discarded";
  }

  function show(seconds) {
    const offset = seconds - at;
    let state;
    if (Math.abs(offset) <= tolerance) {
      state = "at";
    } else if (offset < 0) {
      state = "before";
    } else {
      state = "after";
    }
    const side = sideFor(state);

    // Re-flash the lamp only on a real crossing, not every frame.
    if (light.dataset.state !== state) {
      light.dataset.state = state;
      if (state === "at" && lamp) {
        lamp.classList.remove("struck");
        // Force a reflow so the animation restarts on a second audition.
        void lamp.offsetWidth;
        lamp.classList.add("struck");
      }
    }
    light.dataset.side = side;
    if (fields["cut-light-offset"]) {
      fields["cut-light-offset"].textContent = signed(offset);
    }
    if (fields["cut-light-state"]) {
      fields["cut-light-state"].textContent = state;
    }
    if (fields["cut-light-side"]) {
      fields["cut-light-side"].textContent = side;
    }
  }

  function tick() {
    if (!running || !audio) {
      return;
    }
    show(clock ? clock() : audio.currentTime);
    frame = window.requestAnimationFrame(tick);
  }

  function start() {
    if (running || !audio || !window.requestAnimationFrame) {
      return;
    }
    running = true;
    tick();
  }

  function stop() {
    running = false;
    if (frame !== null) {
      window.cancelAnimationFrame(frame);
      frame = null;
    }
  }

  function retarget(detail) {
    if (!detail || typeof detail.seconds !== "number") {
      return;
    }
    boundary = detail.boundary || boundary;
    at = detail.seconds;
    // A punch-in opens the published audio, so what precedes it goes; a
    // punch-out closes it, so what precedes it is what was kept.
    if (boundary === "punch-out") {
      discards = "after the cut";
      keeps = "before the cut";
    } else {
      discards = "before the cut";
      keeps = "after the cut";
    }
    light.dataset.boundary = boundary;
    light.dataset.at = String(at);
    light.dataset.discards = discards;
    light.dataset.keeps = keeps;
    if (fields["cut-light-boundary"]) {
      fields["cut-light-boundary"].textContent = boundary;
    }
    if (fields["cut-light-at"]) {
      fields["cut-light-at"].textContent = formatsTimecode(at);
    }
    if (fields["cut-light-discards"]) {
      fields["cut-light-discards"].textContent = discards + " is discarded";
    }
    if (fields["cut-light-keeps"]) {
      fields["cut-light-keeps"].textContent = keeps + " is kept";
    }
  }

  // A seam clip is not the preview file, so its event hands over a clock that
  // maps the clip's position back to a time in the recording.
  document.addEventListener("preview:started", function (event) {
    clock = event.detail && typeof event.detail.clock === "function" ? event.detail.clock : null;
    light.dataset.auditioning = "yes";
    retarget(event.detail);
    start();
  });

  document.addEventListener("preview:ended", function () {
    delete light.dataset.auditioning;
    stop();
    if (clock) {
      show(clock());
      clock = null;
    } else if (audio) {
      show(audio.currentTime);
    }
  });

  // Outside an audition the light still follows the playhead, so scrubbing
  // toward a boundary shows the approach. timeupdate's coarseness is fine here:
  // nothing is being judged against an instant.
  document.addEventListener("audio:timeupdate", function (event) {
    if (!running && event.detail && typeof event.detail.seconds === "number") {
      show(event.detail.seconds);
    }
  });

  if (audio) {
    audio.addEventListener("play", start);
    audio.addEventListener("pause", function () {
      stop();
      show(audio.currentTime);
    });
  }
})();
