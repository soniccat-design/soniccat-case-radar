(function () {
  var buttons = Array.prototype.slice.call(document.querySelectorAll("[data-filter]"));
  var cards = Array.prototype.slice.call(document.querySelectorAll("[data-category]"));
  var count = document.querySelector("[data-result-count]");
  var placeholder = document.body.getAttribute("data-placeholder") || "/static/placeholder.svg";

  Array.prototype.slice.call(document.querySelectorAll("img[data-fallback]")).forEach(function (img) {
    img.addEventListener("error", function () {
      if (img.getAttribute("src") !== placeholder) {
        img.setAttribute("src", placeholder);
      }
    });
  });

  function setFilter(category) {
    var visible = 0;
    cards.forEach(function (card) {
      var match = category === "all" || card.getAttribute("data-category") === category;
      card.hidden = !match;
      if (match) visible += 1;
    });
    buttons.forEach(function (button) {
      var active = button.getAttribute("data-filter") === category;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    if (count) count.textContent = visible + " 个案例";
  }

  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      setFilter(button.getAttribute("data-filter"));
    });
  });
})();
