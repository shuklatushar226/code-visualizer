// Tiny preferences UI. Stores `backend` in chrome.storage.local; content
// scripts read it at startup.

const input = document.getElementById("backend");
const status = document.getElementById("status");

chrome.storage.local.get(["backend"], ({ backend }) => {
  input.value = backend ?? "http://localhost:8000";
});

document.getElementById("save").addEventListener("click", async () => {
  await chrome.storage.local.set({ backend: input.value.trim() });
  status.textContent = "Saved.";
  setTimeout(() => (status.textContent = ""), 1200);
});
