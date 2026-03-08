const ENDPOINT = "https://cafe-visits.fly.dev/cafes";

const button = document.querySelector("#pick-cafe");
const result = document.querySelector("#result");
let isFetchingCafe = false;

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchCafe() {
  const response = await fetch(ENDPOINT);

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

function renderCafe(cafe) {
  result.innerHTML = `
    <h2>${cafe.name}</h2>
    <p id="cafe-address">${cafe.address}</p>
    <button id="copy-address" class="copy-address" type="button">Copy address</button>
  `;
  result.classList.remove("is-refreshing");
}

function renderLoading() {
  result.classList.add("is-refreshing");
  result.innerHTML =
    "<h2>Steeping your next spot...</h2><p>Looking for a cozy corner with study energy.</p>";
}

function renderError() {
  result.classList.remove("is-refreshing");
  result.innerHTML =
    "<h2>Not this pour</h2><p>Our cafe list is taking a short break. Try again in a few seconds.</p>";
}

async function copyAddress() {
  const addressElement = document.querySelector("#cafe-address");
  const copyButton = document.querySelector("#copy-address");

  if (!addressElement || !copyButton) {
    return;
  }

  const address = addressElement.textContent?.trim();
  if (!address) {
    return;
  }

  const originalLabel = copyButton.textContent;

  try {
    await navigator.clipboard.writeText(address);
    copyButton.textContent = "Copied!";
  } catch (error) {
    copyButton.textContent = "Copy failed";
    console.error(error);
  }

  setTimeout(() => {
    copyButton.textContent = originalLabel;
  }, 1600);
}

result.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) {
    return;
  }
  if (target.id === "copy-address") {
    copyAddress();
  }
});

button.addEventListener("click", async () => {
  if (isFetchingCafe) {
    return;
  }

  isFetchingCafe = true;
  button.disabled = true;
  renderLoading();
  try {
    await wait(2000);
    const cafe = await fetchCafe();
    renderCafe(cafe);
  } catch (error) {
    renderError();
    console.error(error);
  } finally {
    isFetchingCafe = false;
    button.disabled = false;
  }
});
