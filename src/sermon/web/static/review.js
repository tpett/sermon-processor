const wave = document.querySelector('[data-role="waveform"]');
const overviewCanvas = document.querySelector('[data-role="overview-canvas"]');
const detailPane = document.querySelector('[data-role="detail"]');
const detailCanvas = document.querySelector('[data-role="detail-canvas"]');
const marker = wave && wave.querySelector('[data-role="waveform-playhead"]');
const readout = document.querySelector('.waveform [data-field="playhead"]');

const duration = wave ? Number(wave.dataset.durationSeconds) : 0;
const fetched = new Map();

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

function paint(canvas, held, fromSeconds, throughSeconds) {
  if (!canvas || !held) return;
  const context = canvas.getContext("2d");
  const middle = canvas.height / 2;
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#4a5056";
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

async function draws() {
  const all = sources();
  const overview = coarsest(all);
  if (overview) paint(overviewCanvas, await peaks(overview), 0, duration);
  if (!detailPane) return;
  const from = Number(detailPane.dataset.windowStartSeconds);
  const seconds = Number(detailPane.dataset.windowSeconds);
  const source = finest(all) || overview;
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

function movesPlayhead(seconds) {
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

function seeks(seconds) {
  movesPlayhead(seconds);
  document.dispatchEvent(new CustomEvent("waveform:seek", { detail: { seconds } }));
}

const windowMarker = document.querySelector('[data-role="detail-window"]');

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
  draws();
}

if (wave) {
  wave.addEventListener("click", (event) => {
    if (event.target.closest("a")) return;
    const seconds = secondsAt(event, wave, 0, duration);
    seeks(seconds);
    recentres(seconds);
  });
}

if (detailPane) {
  detailPane.addEventListener("click", (event) => {
    if (event.target.closest("a")) return;
    seeks(
      secondsAt(
        event,
        detailPane,
        Number(detailPane.dataset.windowStartSeconds),
        Number(detailPane.dataset.windowSeconds)
      )
    );
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

document.addEventListener("preview:started", (event) => {
  const { boundary, seconds } = event.detail;
  if (wave) wave.dataset.auditioning = boundary;
  marks.forEach((mark) => {
    if (mark.dataset.boundary === boundary) mark.dataset.auditioning = "true";
    else delete mark.dataset.auditioning;
  });
  if (Number.isFinite(Number(seconds))) recentres(Number(seconds));
});

document.addEventListener("preview:ended", () => {
  if (wave) delete wave.dataset.auditioning;
  marks.forEach((mark) => delete mark.dataset.auditioning);
});

draws();
