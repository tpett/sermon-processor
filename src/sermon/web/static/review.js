const wave = document.querySelector('[data-role="waveform"]');
const overviewCanvas = document.querySelector('[data-role="overview-canvas"]');
const detailPane = document.querySelector('[data-role="detail"]');
const detailCanvas = document.querySelector('[data-role="detail-canvas"]');
const marker = wave && wave.querySelector('[data-role="waveform-playhead"]');
const readout = document.querySelector('.waveform [data-field="playhead"]');
const detailMarker = detailPane && detailPane.querySelector('[data-role="detail-playhead"]');
const region = detailPane && detailPane.querySelector('[data-role="cut-region"]');
const ticks = document.querySelector('[data-role="detail-ticks"]');

const duration = wave ? Number(wave.dataset.durationSeconds) : 0;
const fetched = new Map();

const token = (name) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#8a8378";

function sources() {
  return [...document.querySelectorAll('[data-row="peak-source"]')].map((row) => ({
    resolution: row.dataset.peakResolution,
    url: row.dataset.peakUrl,
    hz: Number(row.dataset.peakHz),
    secondsPerBin: Number(row.dataset.peakSecondsPerBin),
  }));
}

function decode(encoded) {
  const binary = atob(encoded);
  const values = new Int8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    values[index] = binary.charCodeAt(index) << 24 >> 24;
  }
  return values;
}

async function peaks(source) {
  if (!fetched.has(source.resolution)) {
    fetched.set(
      source.resolution,
      fetch(source.url)
        .then((response) => (response.ok ? response.json() : null))
        .then((held) =>
          held && {
            lows: decode(held.min),
            highs: decode(held.max),
            secondsPerBin: held.seconds_per_bin,
            fullScale: held.full_scale || 127,
          }
        )
        .catch(() => null)
    );
  }
  return fetched.get(source.resolution);
}

function cutRange() {
  if (!region) return null;
  return [Number(region.dataset.fromSeconds), Number(region.dataset.toSeconds)];
}

function paint(canvas, held, fromSeconds, throughSeconds) {
  if (!canvas || !held) return;
  const context = canvas.getContext("2d");
  const middle = canvas.height / 2;
  const cool = token("--wave");
  const hot = token("--wave-hot");
  const kept = cutRange();
  context.clearRect(0, 0, canvas.width, canvas.height);
  const first = Math.max(0, Math.floor(fromSeconds / held.secondsPerBin));
  const last = Math.min(held.lows.length, Math.ceil(throughSeconds / held.secondsPerBin));
  const bins = Math.max(last - first, 1);
  for (let column = 0; column < canvas.width; column += 1) {
    const start = first + Math.floor((column * bins) / canvas.width);
    const finish = Math.max(start + 1, first + Math.floor(((column + 1) * bins) / canvas.width));
    let low = 0;
    let high = 0;
    for (let bin = start; bin < finish && bin < held.lows.length; bin += 1) {
      low = Math.min(low, held.lows[bin]);
      high = Math.max(high, held.highs[bin]);
    }
    const at = fromSeconds + ((throughSeconds - fromSeconds) * column) / canvas.width;
    context.fillStyle = kept && at >= kept[0] && at <= kept[1] ? hot : cool;
    const top = middle - (high / held.fullScale) * middle;
    const bottom = middle - (low / held.fullScale) * middle;
    context.fillRect(column, top, 1, Math.max(bottom - top, 1));
  }
}

function coarsest(all) {
  return all.reduce((held, one) => (!held || one.hz < held.hz ? one : held), null);
}

function finest(all) {
  return all.reduce((held, one) => (!held || one.hz > held.hz ? one : held), null);
}

function marksTicks(fromSeconds, windowSeconds) {
  if (!ticks) return;
  const places = 6;
  ticks.textContent = "";
  for (let step = 0; step < places; step += 1) {
    const at = fromSeconds + (windowSeconds * step) / places;
    const tick = document.createElement("li");
    tick.style.left = `${(100 * step) / places}%`;
    tick.textContent =
      windowSeconds <= 10 ? formatsPrecise(at) : formatsPrecise(at).slice(0, -3);
    ticks.appendChild(tick);
  }
}

async function draws() {
  const all = sources();
  const overview = coarsest(all);
  if (overview) paint(overviewCanvas, await peaks(overview), 0, duration);
  if (!detailPane) return;
  const from = Number(detailPane.dataset.windowStartSeconds);
  const seconds = Number(detailPane.dataset.windowSeconds);
  const source = finest(all) || overview;
  marksTicks(from, seconds);
  if (source) paint(detailCanvas, await peaks(source), from, from + seconds);
}

function formatsPrecise(seconds) {
  const whole = Math.max(seconds, 0);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const rest = whole % 60;
  return `${hours}:${String(minutes).padStart(2, "0")}:${rest.toFixed(2).padStart(5, "0")}`;
}

const marks = wave ? [...wave.querySelectorAll('[data-role="boundary-mark"]')] : [];

function nearestMark(seconds) {
  return marks.reduce(
    (held, one) =>
      !held || Math.abs(one.dataset.atSeconds - seconds) < Math.abs(held.dataset.atSeconds - seconds)
        ? one
        : held,
    null
  );
}

function acrossWindow(seconds) {
  const from = Number(detailPane.dataset.windowStartSeconds);
  const span = Number(detailPane.dataset.windowSeconds);
  return Math.min(Math.max((100 * (seconds - from)) / span, 0), 100);
}

function windowPosition(seconds) {
  const from = Number(detailPane.dataset.windowStartSeconds);
  const span = Number(detailPane.dataset.windowSeconds);
  return (100 * (seconds - from)) / span;
}

function movesPlayhead(seconds) {
  if (detailMarker && detailPane) {
    detailMarker.style.left = `${acrossWindow(seconds)}%`;
    detailMarker.dataset.playheadSeconds = String(seconds);
  }
  if (marker && duration > 0) {
    marker.style.left = `${Math.min(Math.max((100 * seconds) / duration, 0), 100)}%`;
    marker.dataset.playheadSeconds = String(seconds);
    const mark = nearestMark(seconds);
    if (mark) {
      const offset = seconds - Number(mark.dataset.atSeconds);
      marker.dataset.againstBoundary = mark.dataset.boundary;
      marker.dataset.playheadOffsetSeconds = offset.toFixed(2);
      marker.dataset.playheadOffset = `${offset >= 0 ? "+" : ""}${offset.toFixed(2)} s`;
    }
  }
  if (readout) readout.textContent = formatsPrecise(seconds);
}

function secondsAt(event, element, fromSeconds, windowSeconds) {
  const box = element.getBoundingClientRect();
  const across = Math.min(Math.max((event.clientX - box.left) / box.width, 0), 1);
  return fromSeconds + across * windowSeconds;
}

function seeks(seconds, play) {
  movesPlayhead(seconds);
  document.dispatchEvent(
    new CustomEvent("waveform:seek", { detail: { seconds, play: play === true } })
  );
}

function operates(event) {
  return event.target.closest(
    "a, button, form, input, [data-role^='handle-'], [data-role='scrub-handle']"
  );
}

const windowMarker = document.querySelector('[data-role="detail-window"]');

function settles() {
  if (!detailPane) return;
  const from = Number(detailPane.dataset.windowStartSeconds);
  const span = Number(detailPane.dataset.windowSeconds);
  if (region) {
    const opens = acrossWindow(Number(region.dataset.fromSeconds));
    region.style.left = `${opens}%`;
    region.style.width = `${acrossWindow(Number(region.dataset.toSeconds)) - opens}%`;
  }
  detailPane.querySelectorAll('[data-role^="handle-"]').forEach((handle) => {
    const at = Number(handle.dataset.atSeconds);
    handle.hidden = at < from || at > from + span;
    handle.style.left = `${acrossWindow(at)}%`;
  });
  packsWords();
}

function recentres(seconds, at) {
  if (!detailPane) return;
  const span = Number(detailPane.dataset.windowSeconds);
  const lands = typeof at === "number" ? at : 0.5;
  const from = Math.max(0, Math.min(seconds - span * lands, duration - span));
  detailPane.dataset.windowStartSeconds = String(from);
  detailPane.dataset.windowCentreSeconds = String(seconds);
  if (windowMarker && duration > 0) {
    windowMarker.style.left = `${(100 * from) / duration}%`;
    windowMarker.dataset.windowStartSeconds = String(from);
    windowMarker.dataset.windowCentreSeconds = String(seconds);
  }
  settles();
  draws();
  fetchesWords();
}

if (wave) {
  wave.addEventListener("click", (event) => {
    if (operates(event)) return;
    const seconds = secondsAt(event, wave, 0, duration);
    seeks(seconds, true);
    recentres(seconds);
  });
}

if (detailPane) {
  detailPane.addEventListener("click", (event) => {
    if (operates(event)) return;
    seeks(
      secondsAt(
        event,
        detailPane,
        Number(detailPane.dataset.windowStartSeconds),
        Number(detailPane.dataset.windowSeconds)
      ),
      true
    );
  });
}

function showsBoundary(handle, seconds) {
  handle.style.left = `${acrossWindow(seconds)}%`;
  const shown = document.querySelector(`[data-field="${handle.dataset.boundary}"]`);
  if (shown) shown.textContent = formatsPrecise(seconds);
  if (!region) return;
  const from = handle.dataset.boundary === "punch-in" ? seconds : Number(region.dataset.fromSeconds);
  const to = handle.dataset.boundary === "punch-out" ? seconds : Number(region.dataset.toSeconds);
  region.style.left = `${acrossWindow(from)}%`;
  region.style.width = `${acrossWindow(to) - acrossWindow(from)}%`;
}

const MOVES_A_BOUNDARY = /\/(boundaries|span)\//;

function liveView() {
  if (!detailPane) return [];
  const from = Number(detailPane.dataset.windowStartSeconds);
  const span = Number(detailPane.dataset.windowSeconds);
  const at = detailMarker ? Number(detailMarker.dataset.playheadSeconds) : NaN;
  const carried = [];
  if (detailPane.dataset.windowStep) carried.push(["zoom", detailPane.dataset.windowStep]);
  if (Number.isFinite(from) && Number.isFinite(span)) {
    carried.push(["centre", (from + span / 2).toFixed(2)]);
  }
  if (Number.isFinite(at)) carried.push(["playhead", at.toFixed(2)]);
  return carried;
}

function carriesTheView(action) {
  const asked = new URL(action, window.location.href);
  liveView().forEach(([name, value]) => asked.searchParams.set(name, value));
  return asked.toString();
}

function movesABoundary(form) {
  return MOVES_A_BOUNDARY.test(new URL(form.action, window.location.href).pathname);
}

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !movesABoundary(form)) return;
  form.action = carriesTheView(form.action);
});

function places(handle, seconds) {
  const form = document.createElement("form");
  form.method = "post";
  form.action = carriesTheView(handle.dataset.url);
  form.innerHTML =
    '<input type="hidden" name="do" value="set">' +
    `<input type="hidden" name="timecode" value="${seconds.toFixed(2)}">`;
  document.body.appendChild(form);
  form.submit();
}

if (detailPane) {
  detailPane.querySelectorAll('[data-role^="handle-"]').forEach((handle) => {
    let dragged = null;
    handle.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
      handle.dataset.dragging = "true";
      dragged = Number(handle.dataset.atSeconds);
    });
    handle.addEventListener("pointermove", (event) => {
      if (handle.dataset.dragging !== "true") return;
      dragged = secondsAt(
        event,
        detailPane,
        Number(detailPane.dataset.windowStartSeconds),
        Number(detailPane.dataset.windowSeconds)
      );
      showsBoundary(handle, dragged);
    });
    handle.addEventListener("pointerup", (event) => {
      if (handle.dataset.dragging !== "true") return;
      delete handle.dataset.dragging;
      handle.releasePointerCapture(event.pointerId);
      if (Math.abs(dragged - Number(handle.dataset.atSeconds)) < 0.01) return;
      places(handle, dragged);
    });
  });
}

document.querySelectorAll('[data-role="evidence-seek"]').forEach((link) => {
  link.addEventListener("click", (event) => {
    const marker = link.closest('[data-evidence-seconds]');
    if (!marker) return;
    event.preventDefault();
    const seconds = Number(marker.dataset.evidenceSeconds);
    seeks(seconds);
    recentres(seconds);
  });
});

document.addEventListener("audio:timeupdate", (event) => {
  const seconds = Number(event.detail.seconds);
  movesPlayhead(seconds);
  keepsInView(seconds);
  speaking(seconds);
});

let following = 0;

let spokenLine = null;

function follows() {
  const audio = document.querySelector("audio");
  if (audio && !audio.paused) {
    const seconds = audio.currentTime;
    movesPlayhead(seconds);
    keepsInView(seconds);
    const line = speaking(seconds);
    // Only chase the transcript when the line actually changes, so a reader
    // scrolling it by hand is not fought sixty times a second.
    if (line && line !== spokenLine) {
      spokenLine = line;
      scrolls(line);
    }
  }
  following = requestAnimationFrame(follows);
}

document.addEventListener("preview:started", (event) => {
  const { boundary, seconds } = event.detail;
  if (!following) following = requestAnimationFrame(follows);
  if (wave) wave.dataset.auditioning = boundary;
  marks.forEach((mark) => {
    if (mark.dataset.boundary === boundary) mark.dataset.auditioning = "true";
    else delete mark.dataset.auditioning;
  });
  if (Number.isFinite(Number(seconds))) recentres(Number(seconds));
});

document.addEventListener("preview:ended", () => {
  cancelAnimationFrame(following);
  following = 0;
  if (wave) delete wave.dataset.auditioning;
  marks.forEach((mark) => delete mark.dataset.auditioning);
});

draws();

const scheme = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)");
if (scheme && scheme.addEventListener) scheme.addEventListener("change", draws);

const words = document.querySelector(".waveform .words");
const LANES = [8, 25, 42];

function packsWords() {
  if (!words) return;
  const across = words.getBoundingClientRect().width;
  if (!across) return;
  const filled = LANES.map(() => -Infinity);
  [...words.children].forEach((word) => {
    // data-word-left is the server's placement for the window it rendered. Once
    // the window has moved under us it is a different stretch of the recording,
    // so the position has to come from the word's own timecode.
    const position = detailPane
      ? windowPosition(Number(word.dataset.wordAtSeconds))
      : Number(word.dataset.wordLeft);
    if (position < 0 || position > 100) {
      word.hidden = true;
      return;
    }
    word.hidden = false;
    word.style.left = `${position}%`;
    const left = (position / 100) * across;
    const lane = filled.findIndex((edge) => left >= edge);
    if (lane < 0) {
      word.hidden = true;
      return;
    }
    word.style.top = `${LANES[lane]}px`;
    filled[lane] = left + word.getBoundingClientRect().width + 5;
  });
}

const listen = document.querySelector('[data-role="listen"]');
const recordingId = listen ? listen.dataset.recording : null;
let fetchedFor = null;

// The page is rendered with the words for one window. Once the playhead has
// carried the window somewhere else, the words for that stretch have to be
// asked for, the same way the peaks are.
async function fetchesWords() {
  if (!words || !detailPane || !recordingId || !window.fetch) return;
  const from = Number(detailPane.dataset.windowStartSeconds);
  const seconds = Number(detailPane.dataset.windowSeconds);
  const wanted = `${from.toFixed(2)}/${seconds}`;
  if (wanted === fetchedFor) return;
  fetchedFor = wanted;
  let payload;
  try {
    const answer = await fetch(
      `/api/recordings/${recordingId}/words?from=${from}&seconds=${seconds}`
    );
    if (!answer.ok) return;
    payload = await answer.json();
  } catch (ignored) {
    return;
  }
  if (`${from.toFixed(2)}/${seconds}` !== fetchedFor) return;
  const shape = words.firstElementChild;
  words.replaceChildren(
    ...payload.words.map((word) => {
      const line = shape ? shape.cloneNode(true) : document.createElement("li");
      line.dataset.row = "transcript-word";
      line.dataset.wordAt = word.at;
      line.dataset.wordAtSeconds = String(word.at_seconds);
      line.dataset.wordLeft = String(word.left);
      line.hidden = false;
      const label = line.querySelector('[data-field="word-text"]');
      if (label) label.textContent = word.text;
      const timecode = line.querySelector('input[name="timecode"]');
      if (timecode) timecode.value = word.at;
      return line;
    })
  );
  packsWords();
}

const utterances = [...document.querySelectorAll('[data-row="utterance"]')];

function speaking(seconds) {
  if (words) {
    let current = null;
    [...words.children].forEach((word) => {
      delete word.dataset.wordCurrent;
      if (Number(word.dataset.wordAtSeconds) <= seconds) current = word;
    });
    if (current) current.dataset.wordCurrent = "true";
  }
  if (!utterances.length) return null;
  let spoken = null;
  utterances.forEach((line) => {
    delete line.dataset.utteranceCurrent;
    if (Number(line.dataset.utteranceAtSeconds) <= seconds) spoken = line;
  });
  if (spoken) spoken.dataset.utteranceCurrent = "true";
  return spoken;
}

function scrolls(line) {
  const panel = line && line.parentElement;
  if (!panel) return;
  const top = line.offsetTop - panel.clientHeight / 2 + line.clientHeight / 2;
  panel.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
}

// Turn the page rather than sliding every frame: a window that scrolls
// continuously under a still playhead is hard to read a waveform on.
function keepsInView(seconds) {
  if (!detailPane) return;
  const position = windowPosition(seconds);
  if (position > 75 || position < 0) recentres(seconds, 0.25);
}

const detailLabel = document.querySelector('[data-role="detail-label"]');

// Zoom used to be a link, so choosing a scale reloaded the page: the audio
// stopped and the playhead went back to whatever the server had stored. The
// scale is a property of the view, not of the recording, so it is changed here
// and the audio is left alone.
function zoomsTo(chip) {
  if (!detailPane) return false;
  const seconds = Number(chip.dataset.zoomWindowSeconds);
  if (!Number.isFinite(seconds) || seconds <= 0) return false;
  const audio = document.querySelector("audio");
  const at =
    audio && Number.isFinite(audio.currentTime) && audio.currentTime > 0
      ? audio.currentTime
      : Number(detailPane.dataset.windowCentreSeconds);
  detailPane.dataset.windowSeconds = String(seconds);
  detailPane.dataset.windowStep = chip.dataset.zoomStep;
  document
    .querySelectorAll('[data-row="zoom-step"]')
    .forEach((one) => delete one.dataset.selected);
  chip.dataset.selected = "true";
  if (detailLabel) {
    const across =
      seconds >= 600
        ? `${Math.round(seconds / 60)} min`
        : `${Number(seconds.toFixed(1))} s`;
    detailLabel.textContent = `Detail — ${chip.dataset.zoomStep} · ${across} in view`;
  }
  recentres(at);
  return true;
}

document.querySelectorAll('[data-row="zoom-step"]').forEach((chip) => {
  const link = chip.querySelector("a");
  if (!link) return;
  link.addEventListener("click", (event) => {
    // Without a detail pane there is no window to rescale, so the link stands.
    if (zoomsTo(chip)) event.preventDefault();
  });
});

// The page has always said "the keyboard will move the punch-in". Nothing was
// listening. The spec calls the keyboard load-bearing because dragging cannot
// reach 50 ms at any zoom that still shows enough context to be oriented.
const focusState = document.querySelector('[data-field="focus-state"]');

// Focusing a boundary used to post and reload, which stopped the audio for the
// same reason zoom did. Which boundary the keyboard moves is a property of the
// view; the server reads it from the query string, so keeping that in step is
// all a reload needs.
function focuses(field) {
  const rows = [...document.querySelectorAll('[data-row="boundary"]')];
  if (!rows.length) return false;
  rows.forEach((row) => {
    const mine = row.dataset.boundary === field;
    row.dataset.focused = mine ? "true" : "false";
    const marker = row.querySelector('[data-field="boundary-focus"]');
    if (mine && !marker) {
      const said = document.createElement("span");
      said.className = "label";
      said.dataset.field = "boundary-focus";
      said.textContent = "the keyboard will move this boundary";
      row.querySelector('[data-field="boundary-at"]').after(said);
    } else if (!mine && marker) {
      marker.remove();
    }
  });
  if (focusState) focusState.textContent = `the keyboard will move the ${field}`;
  const here = new URL(window.location.href);
  here.searchParams.set("focus", field);
  window.history.replaceState({}, "", here);
  return true;
}

document.querySelectorAll('[data-field="focus-control"]').forEach((control) => {
  const row = control.closest('[data-row="boundary"]');
  if (!row) return;
  control.addEventListener("click", (event) => {
    if (focuses(row.dataset.boundary)) event.preventDefault();
  });
});

function typingIn(target) {
  if (!target || typeof target.closest !== "function") return false;
  return Boolean(target.closest("input, textarea, select")) || target.isContentEditable === true;
}

const NUDGE_KEYS = { ArrowLeft: "earlier", ArrowRight: "later" };

function nudges(direction, amount) {
  const focused = document.querySelector('[data-row="boundary"][data-focused="true"]');
  if (!focused) return false;
  const control = [...focused.querySelectorAll("[data-nudge]")].find(
    (one) => one.dataset.nudge === `${direction} ${amount}`
  );
  if (!control) return false;
  // The controls live in a collapsed <details>, so the button is not rendered
  // and clicking it is not guaranteed to submit. Submit its form instead.
  const form = control.closest("form");
  if (form) {
    form.action = carriesTheView(form.action);
    form.submit();
  } else control.click();
  return true;
}

document.addEventListener("keydown", (event) => {
  const direction = NUDGE_KEYS[event.key];
  if (!direction || event.metaKey || event.ctrlKey) return;
  if (typingIn(event.target)) return;
  const amount = event.shiftKey ? "1 s" : event.altKey ? "50 ms" : "0.1 s";
  if (nudges(direction, amount)) event.preventDefault();
});


document.querySelectorAll('[data-seeks="playhead"]').forEach((ruler) => {
  const wholeRecording = Boolean(wave && wave.contains(ruler));
  if (!wholeRecording && !detailPane) return;
  ruler.addEventListener("click", (event) => {
    if (operates(event)) return;
    event.stopPropagation();
    const seconds = wholeRecording
      ? secondsAt(event, ruler, 0, duration)
      : secondsAt(
          event,
          ruler,
          Number(detailPane.dataset.windowStartSeconds),
          Number(detailPane.dataset.windowSeconds)
        );
    seeks(seconds);
    if (wholeRecording) recentres(seconds);
  });
});

const scrubHandle = detailPane && detailPane.querySelector('[data-role="scrub-handle"]');

function playheadNow() {
  return detailMarker ? Number(detailMarker.dataset.playheadSeconds) : 0;
}

function scrubs(step) {
  const limit = duration > 0 ? duration : playheadNow() + step;
  const wanted = Math.min(Math.max(playheadNow() + step, 0), limit);
  seeks(wanted);
  keepsInView(wanted);
}

if (scrubHandle && detailPane) {
  scrubHandle.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    scrubHandle.setPointerCapture(event.pointerId);
    scrubHandle.dataset.dragging = "true";
  });
  scrubHandle.addEventListener("pointermove", (event) => {
    if (scrubHandle.dataset.dragging !== "true") return;
    seeks(
      secondsAt(
        event,
        detailPane,
        Number(detailPane.dataset.windowStartSeconds),
        Number(detailPane.dataset.windowSeconds)
      )
    );
  });
  scrubHandle.addEventListener("pointerup", (event) => {
    if (scrubHandle.dataset.dragging !== "true") return;
    delete scrubHandle.dataset.dragging;
    scrubHandle.releasePointerCapture(event.pointerId);
  });
}

function zoomsBy(direction) {
  const chips = [...document.querySelectorAll('[data-row="zoom-step"]')];
  if (!chips.length) return false;
  const held = chips.findIndex((chip) => chip.dataset.selected === "true");
  const at = Math.min(Math.max((held < 0 ? 0 : held) + direction, 0), chips.length - 1);
  return chips[at].dataset.selected === "true" ? false : zoomsTo(chips[at]);
}

function zoomsToFit() {
  const chips = [...document.querySelectorAll('[data-row="zoom-step"]')];
  if (!chips.length || chips[0].dataset.selected === "true") return false;
  return zoomsTo(chips[0]);
}

const ZOOM_CHORDS = { 1: 1, 3: -1 };
const ZOOM_KEYS = { "=": 1, "+": 1, 1: 1, "-": -1, _: -1, 3: -1 };
const FIT_KEYS = new Set(["\\"]);
const SHIFTED_FIT_KEYS = new Set(["Z"]);
const SCRUB_KEYS = { ",": -1, ".": 1, "<": -1, ">": 1 };

window.addEventListener(
  "keydown",
  (event) => {
    if (!event.metaKey && !event.ctrlKey) return;
    if (event.altKey || event.shiftKey) return;
    const zoom = ZOOM_CHORDS[event.key];
    if (zoom === undefined) return;
    event.preventDefault();
    event.stopPropagation();
    zoomsBy(zoom);
  },
  true
);

document.addEventListener("keydown", (event) => {
  if (typingIn(event.target) || event.metaKey || event.ctrlKey) return;
  if (FIT_KEYS.has(event.key) || (event.shiftKey && SHIFTED_FIT_KEYS.has(event.key))) {
    if (zoomsToFit()) event.preventDefault();
    return;
  }
  const zoom = ZOOM_KEYS[event.key];
  if (zoom !== undefined) {
    if (zoomsBy(zoom)) event.preventDefault();
    return;
  }
  const direction = SCRUB_KEYS[event.key];
  if (direction === undefined) return;
  const step = event.shiftKey ? 1 : event.altKey ? 0.05 : 0.1;
  scrubs(direction * step);
  event.preventDefault();
});

document.querySelectorAll('[data-row="punch-point"] [data-field="punch-control"]').forEach(
  (control) => {
    const form = control.closest("form");
    if (!form || !detailMarker) return;
    control.addEventListener("click", () => {
      const asked = form.querySelector('input[name="do"]');
      const timecode = document.createElement("input");
      timecode.type = "hidden";
      timecode.name = "timecode";
      timecode.value = playheadNow().toFixed(2);
      if (asked) asked.value = "set";
      form.appendChild(timecode);
    });
  }
);

const TRANSPORT_KEYS = new Set([" ", "Spacebar"]);

document.addEventListener("keydown", (event) => {
  if (!TRANSPORT_KEYS.has(event.key)) return;
  if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
  if (typingIn(event.target) || !document.querySelector("audio")) return;
  event.preventDefault();
  document.dispatchEvent(new CustomEvent("waveform:transport"));
});

packsWords();
window.addEventListener("resize", packsWords);
settles();
