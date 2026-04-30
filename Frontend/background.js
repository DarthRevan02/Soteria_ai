chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === "complete" && tab.url) {

        chrome.storage.local.get(["alwaysOn"], (data) => {
            if (!data.alwaysOn) return;

            const url = tab.url;

            const isInternshala =
                /^https?:\/\/(www\.)?internshala\.com\/internship\/detail/.test(url);

            if (isInternshala) {
                chrome.tabs.sendMessage(tabId, { action: "scan" });
            }
        });
    }
});