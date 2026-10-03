function formatsTimecode(seconds) {
  const centis = Math.round(Math.max(Number(seconds) || 0, 0) * 100);
  const hours = Math.floor(centis / 360000);
  const minutes = Math.floor((centis % 360000) / 6000);
  const rest = ((centis % 6000) / 100).toFixed(2).padStart(5, "0");
  return `${hours}:${String(minutes).padStart(2, "0")}:${rest}`;
}
