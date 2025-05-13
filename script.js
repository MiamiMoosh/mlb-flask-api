document.addEventListener("DOMContentLoaded", function () {
    const baseUrl = "https://swishanalytics.com/optimus/mlb/batter-vs-pitcher-stats?date=";
    let currentDate = new Date();
    
    function formatDate(date) {
        return date.toISOString().split("T")[0]; // YYYY-MM-DD format
    }

    function updateDateDisplay() {
        document.getElementById("currentDate").textContent = formatDate(currentDate);
    }

    function fetchStats(date) {
        const url = baseUrl + date;
        fetch(url)
            .then(response => response.text())
            .then(html => {
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, "text/html");
                const tableRows = doc.querySelectorAll("table tbody tr");
                
                const tbody = document.querySelector("#statsTable tbody");
                tbody.innerHTML = ""; // Clear previous data
                
                tableRows.forEach(row => {
                    const cells = row.querySelectorAll("td");
                    const batter = cells[0].textContent.trim();
                    const pitcher = cells[1].textContent.trim();
                    const stats = cells[2].textContent.trim();

                    if (shouldDisplayPlayer(batter, pitcher)) {
                        const tr = document.createElement("tr");
                        tr.innerHTML = `<td>${batter}</td><td>${pitcher}</td><td>${stats}</td>`;
                        tbody.appendChild(tr);
                    }
                });
            })
            .catch(error => console.error("Error fetching stats:", error));
    }

    function shouldDisplayPlayer(batter, pitcher) {
        const storedPlayers = JSON.parse(getCookie("trackedPlayers") || "[]");
        return storedPlayers.includes(batter) || storedPlayers.includes(pitcher);
    }

    function getCookie(name) {
        const cookies = document.cookie.split("; ");
        for (let cookie of cookies) {
            const [key, value] = cookie.split("=");
            if (key === name) return decodeURIComponent(value);
        }
        return null;
    }

    function setCookie(name, value, days) {
        const expires = new Date();
        expires.setDate(expires.getDate() + days);
        document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires.toUTCString()}; path=/`;
    }

    function updateTrackedPlayers() {
        const storedPlayers = JSON.parse(getCookie("trackedPlayers") || "[]");
        const list = document.getElementById("trackedPlayers");
        list.innerHTML = "";
        storedPlayers.forEach(player => {
            const li = document.createElement("li");
            li.textContent = player;
            list.appendChild(li);
        });
    }

    document.getElementById("prevDay").addEventListener("click", function () {
        currentDate.setDate(currentDate.getDate() - 1);
        updateDateDisplay();
        fetchStats(formatDate(currentDate));
    });

    document.getElementById("nextDay").addEventListener("click", function () {
        currentDate.setDate(currentDate.getDate() + 1);
        updateDateDisplay();
        fetchStats(formatDate(currentDate));
    });

    updateDateDisplay();
    fetchStats(formatDate(currentDate));
    updateTrackedPlayers();
});