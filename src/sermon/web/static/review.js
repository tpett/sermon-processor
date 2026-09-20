const data = JSON.parse(document.getElementById("recording-data").textContent);
const overview = document.getElementById("overview");
const detail = document.getElementById("detail");

function draw(canvas, peaks) {
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const mid = canvas.height / 2;
  peaks.forEach((peak, index) => {
    const x = (index / Math.max(peaks.length - 1, 1)) * canvas.width;
    const h = peak * mid;
    ctx.fillRect(x, mid - h, 1, h * 2);
  });
}

if (overview && data.peaks) {
  draw(overview, data.peaks);
  draw(detail, data.peaks);
}
