document.querySelectorAll(".flash").forEach((el) => {
  setTimeout(() => {
    el.style.transition = "opacity .4s ease";
    el.style.opacity = "0";
  }, 4200);
});
