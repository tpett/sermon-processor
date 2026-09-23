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
  return event.target.closest("a, button, form, input, [data-role^='handle-']");
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
}

function recentres(seconds) {
  if (!detailPane) return;
  const span = Number(detailPane.dataset.windowSeconds);
  const from = Math.max(0, Math.min(seconds - span / 2, duration - span));
  detailPane.dataset.windowStartSeconds = String(from);
  detailPane.dataset.windowCentreSeconds = String(seconds);
  if (windowMarker && duration > 0) {
    windowMarker.style.left = `${(100 * from) / duration}%`;
    windowMarker.dataset.windowStartSeconds = String(from);
    windowMarker.dataset.windowCentreSeconds = String(seconds);
  }
  settles();
  draws();
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

function places(handle, seconds) {
  const form = document.createElement("form");
  form.method = "post";
  form.action = handle.dataset.url;
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
  movesPlayhead(Number(event.detail.seconds));
});

let following = 0;

function follows() {
  const audio = document.querySelector("audio");
  if (audio && !audio.paused) movesPlayhead(audio.currentTime);
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
    word.hidden = false;
    const left = (Number(word.dataset.wordLeft) / 100) * across;
    const lane = filled.findIndex((edge) => left >= edge);
    if (lane < 0) {
      word.hidden = true;
      return;
    }
    word.style.top = `${LANES[lane]}px`;
    filled[lane] = left + word.getBoundingClientRect().width + 5;
  });
}

packsWords();
window.addEventListener("resize", packsWords);
settles();
