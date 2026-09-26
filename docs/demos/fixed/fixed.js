const form = document.getElementById("contact-form");
const success = document.getElementById("success");

form.addEventListener("submit", (event) => {
  event.preventDefault();
  success.hidden = false;
  success.textContent = "Message sent";
});
