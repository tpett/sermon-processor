(function () {
  "use strict";

  const SILENCE = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";
  const audio = document.querySelector('[data-role="preview-audio"]');
  const controls = document.querySelectorAll(
    '[data-role="preview-cut"], [data-role="preview-punch-in"], [data-role="preview-punch-out"], [data-role="hear-join"]'
  );
  if (!controls.length) {
    return;
  }

  const clip = new Audio();
  let primed = false;
  let session = null;

  function announce(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail }));
  }

  function sourceAt(pieces, elapsed) {
    let left = elapsed;
    for (const [from, to] of pieces) {
      if (left <= to - from) {
        return from + left;
      }
      left -= to - from;
    }
    return pieces.length ? pieces[pieces.length - 1][1] : elapsed;
  }

  function boundaryOf(seam) {
    if (seam === "opening") {
      return "punch-in";
    }
    return seam === "ending" ? "punch-out" : null;
  }

  function endBoundary(mine) {
    if (mine.boundary) {
      const ended = mine.boundary;
      mine.boundary = null;
      announce("preview:ended", { boundary: ended });
    }
  }

  function stop(syncsPreview = true) {
    if (!session) {
      return;
    }
    const mine = session;
    session = null;
    if (syncsPreview && audio && mine.clock) {
      audio.currentTime = mine.clock();
    }
    clip.pause();
    window.cancelAnimationFrame(mine.frame);
    mine.urls.forEach(function (url) {
      URL.revokeObjectURL(url);
    });
    mine.controls.forEach(function (control) {
      delete control.dataset.playing;
    });
    endBoundary(mine);
  }

  async function fetchSeam(mine, wanted) {
    const response = await fetch(wanted.url, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`${wanted.url}: ${response.status}`);
    }
    const pieces = JSON.parse(response.headers.get("X-Kept-Pieces") || "[]");
    const blob = await response.blob();
    if (session !== mine) {
      throw new Error("stopped");
    }
    const src = URL.createObjectURL(blob);
    mine.urls.push(src);
    return { ...wanted, pieces, src };
  }

  function playSeam(mine, seam) {
    return new Promise(function (resolve, reject) {
      const clock = function () {
        return sourceAt(seam.pieces, clip.currentTime);
      };
      mine.clock = clock;
      const boundary = boundaryOf(seam.seam);
      const last = seam.pieces[seam.pieces.length - 1];
      clip.onended = function () {
        if (clip.currentSrc !== seam.src) {
          return;
        }
        window.cancelAnimationFrame(mine.frame);
        endBoundary(mine);
        announce("seam:position", { seconds: clock() });
        resolve();
      };
      clip.onerror = function () {
        reject(new Error("the seam would not play"));
      };
      function tick() {
        if (session !== mine) {
          return;
        }
        announce("seam:position", { seconds: clock() });
        mine.frame = window.requestAnimationFrame(tick);
      }
      clip.src = seam.src;
      mine.boundary = boundary;
      if (boundary) {
        announce("preview:started", {
          boundary,
          seconds: seam.at,
          from: seam.pieces[0][0],
          to: last[1],
          clock,
        });
      }
      clip.play().then(tick, reject);
    });
  }

  async function hear(wanted, pressed) {
    stop();
    if (audio && !audio.paused) {
      audio.pause();
    }
    const mine = { urls: [], controls: pressed, frame: 0, boundary: null, clock: null };
    session = mine;
    pressed.forEach(function (control) {
      delete control.dataset.failed;
      control.dataset.playing = "true";
    });
    const loading = wanted.map(function (one) {
      return fetchSeam(mine, one);
    });
    loading.forEach(function (pending) {
      pending.catch(function () {});
    });
    try {
      for (const pending of loading) {
        const seam = await pending;
        if (session !== mine) {
          return;
        }
        await playSeam(mine, seam);
        if (session !== mine) {
          return;
        }
      }
      stop();
    } catch (failure) {
      if (session === mine) {
        pressed.forEach(function (control) {
          control.dataset.failed = "true";
        });
        stop();
      }
    }
  }

  function seamsOf(control) {
    if (control.dataset.role === "preview-cut") {
      return Array.from(document.querySelectorAll('[data-row="seam"][data-clip]')).map(describes);
    }
    const card = control.closest('[data-row="seam"][data-clip]');
    if (card) {
      return [describes(card)];
    }
    return [{ url: control.dataset.url, seam: "join", at: null }];
  }

  function describes(card) {
    return {
      url: card.dataset.clip,
      seam: card.dataset.seam,
      at: Number(card.dataset.beforeSeconds),
    };
  }

  controls.forEach(function (control) {
    control.addEventListener("click", function () {
      if (control.dataset.playing === "true") {
        stop();
        return;
      }
      if (!primed) {
        primed = true;
        clip.src = SILENCE;
        const unlocked = clip.play();
        if (unlocked && unlocked.catch) {
          unlocked.catch(function () {});
        }
      }
      hear(seamsOf(control), [control]);
    });
  });

  document.addEventListener("waveform:transport", function (event) {
    if (!session) {
      return;
    }
    event.stopImmediatePropagation();
    if (clip.paused) {
      clip.play();
    } else {
      clip.pause();
    }
  });

  document.addEventListener("waveform:seek", function () {
    stop(false);
  });
  if (audio) {
    audio.addEventListener("play", function () {
      stop(false);
    });
  }
})();
