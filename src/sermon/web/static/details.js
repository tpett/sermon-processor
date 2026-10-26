const panel = document.querySelector('[data-role="recording-details"]');

if (panel) {
  const close = () => {
    panel.open = false;
    panel.querySelector("summary").focus();
  };

  panel.addEventListener("click", (event) => {
    if (event.target.closest('[data-role="close-details"]') || event.target.classList.contains("scrim")) close();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && panel.open) close();
  });
}
