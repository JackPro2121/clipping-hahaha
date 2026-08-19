const EXPORT_FILENAME = "youtube_cookies.txt";

function cookieLine(c) {
  const domain = c.domain;
  const includeSubdomains = "TRUE";
  const path = c.path || "/";
  const secure = c.secure ? "TRUE" : "FALSE";
  const expiry = c.expirationDate ? Math.floor(c.expirationDate) : 0;
  return [domain, includeSubdomains, path, secure, expiry, c.name, c.value].join("\t");
}

document.getElementById("export").addEventListener("click", async () => {
  const status = document.getElementById("status");
  status.textContent = "Exporting...";
  try {
    const all = await chrome.cookies.getAll({});
    const keep = all.filter(
      (c) => c.domain.includes("youtube.com") || c.domain.includes("google.com")
    );
    if (keep.length === 0) {
      status.textContent = "No YouTube cookies found. Pehle youtube.com pe login karo.";
      status.style.color = "#c0392b";
      return;
    }
    const lines = [
      "# Netscape HTTP Cookie File",
      "# Exported by YouTube Cookies Exporter for yt-dlp",
      "# https://github.com/yt-dlp/yt-dlp/wiki/FAQ",
      "",
    ];
    for (const c of keep) lines.push(cookieLine(c));
    const blob = new Blob([lines.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    await chrome.downloads.download({ url: url, filename: EXPORT_FILENAME, saveAs: true });
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    status.textContent = `Done! ${keep.length} cookies exported. Save the file, phir mujhe us file ka path batao.`;
    status.style.color = "#0a7d32";
  } catch (err) {
    status.textContent = "Error: " + err.message;
    status.style.color = "#c0392b";
  }
});