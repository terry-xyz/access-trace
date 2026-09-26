const form = document.getElementById("contact-form");
const submit = document.getElementById("submit");

form.addEventListener("submit", (event) => event.preventDefault());
submit.addEventListener("click", (event) => event.preventDefault());
submit.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") event.preventDefault();
});
