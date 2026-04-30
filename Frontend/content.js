function getPageData() {
    // const text = document.body.innerText.slice(0, 5000);
    const text = document.body.innerText;

    const links = Array.from(document.querySelectorAll("a"))
        .map(a => a.href)
        .filter(l => l.startsWith("http"))
        .slice(0, 20);

    const domain = window.location.hostname;

    return { text, links, domain };
}

async function analyzePage() {
    try {
        const data = getPageData();
        console.log("Page data:", data);

        // const response = await fetch("http://localhost:8000/analyze", {
        //     method: "POST",
        //     headers: {
        //         "Content-Type": "application/json"
        //     },
        //     body: JSON.stringify(data)
        // });

        // const result = await response.json();
        const result = {
            decision: "OKAY",
            score: 20,
            reasons: ["High working hours and low pay", "Multiple roles offered at once"],
            keywords: ["payment", "no interview"]
        }
        showWarning(result);

    } catch (err) {
        console.error("Error:", err);
    }
}

function showWarning(result) {

    const div = document.createElement("div");

    //animation
    div.style.transform = "translateY(-20px)";
    div.style.opacity = "0";
    div.style.transition = "all 0.3s ease";
    
    div.style.position = "fixed";
    div.style.top = "20px";
    div.style.right = "20px";
    div.style.zIndex = "9999";
    div.style.padding = "14px";
    div.style.borderRadius = "10px";
    div.style.fontSize = "14px";
    div.style.maxWidth = "300px";
    div.style.boxShadow = "0 4px 15px rgba(0,0,0,0.3)";
    div.style.color = "white";

    // 🎨 background color based on result
    if (result.decision === "BLOCK") {
        div.style.background = "#ff3b3b";
    } else if (result.decision === "WARN") {
        div.style.background = "#ff9800";
    } else {
        div.style.background = "#4CAF50";
    }

    // ❌ Close button
    const closeBtn = document.createElement("span");
    closeBtn.innerHTML = "✖";
    closeBtn.style.position = "absolute";
    closeBtn.style.top = "8px";
    closeBtn.style.right = "10px";
    closeBtn.style.cursor = "pointer";
    closeBtn.style.fontWeight = "bold";
    closeBtn.style.fontSize = "16px";

    closeBtn.onclick = () => div.remove();

    // 📦 Content
    const content = document.createElement("div");

    if (result.decision === "BLOCK") {
        content.innerHTML = `
            <strong>❌ Scam Detected</strong><br/>
            Score: ${result.score}%<br/>
            ${formatReasons(result.reasons)}
        `;
    } else if (result.decision === "WARN") {
        content.innerHTML = `
            <strong>⚠️ Suspicious</strong><br/>
            Score: ${result.score}%<br/>
            ${formatReasons(result.reasons)}
        `;
    } else {
        content.innerHTML = `
            <strong>✅ Safe</strong><br/>
            Score: ${result.score}%
        `;
    }

    div.appendChild(closeBtn);
    div.appendChild(content);
    document.body.appendChild(div);
    
    // Animate the warning box
    setTimeout(() => {
        div.style.transform = "translateY(0)";
        div.style.opacity = "1";
    }, 10);
}
function formatReasons(reasons) {
    return `
        <ul style="
            padding-left: 18px;
            margin: 6px 0 0 0;
        ">
            ${reasons.map(r => `<li style="margin-bottom:4px;">${r}</li>`).join("")}
        </ul>
    `;
}

function highlightKeywords(keywords) {
    let html = document.body.innerHTML;

    keywords.forEach(word => {
        const regex = new RegExp(word, "gi");
        html = html.replace(
            regex,
            match => `<span style="background:red;color:white;">${match}</span>`
        );
    });

    document.body.innerHTML = html;
}