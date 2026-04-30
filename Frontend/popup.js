// toggle handling
const toggle = document.getElementById("alwaysOnToggle");

chrome.storage.local.get(["alwaysOn"], (data) => {
    toggle.checked = data.alwaysOn || false;
});

toggle.addEventListener("change", () => {
    chrome.storage.local.set({ alwaysOn: toggle.checked });
});

// manual scan button
document.getElementById("scanBtn").addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    chrome.tabs.sendMessage(tab.id, { action: "scan" });

    window.close();
});