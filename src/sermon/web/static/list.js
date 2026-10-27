const menus = () => document.querySelectorAll("details.downloads[open]");

document.addEventListener("click", (event) => {
  for (const menu of menus()) {
    if (!menu.contains(event.target)) menu.open = false;
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  for (const menu of menus()) {
    menu.open = false;
    menu.querySelector("summary").focus();
  }
});
