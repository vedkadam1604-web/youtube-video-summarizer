const $ = (id) => document.getElementById(id);
let player = null;
let lastResult = null;

// YouTube IFrame API calls this when loaded; we create the player lazily per result.
window.onYouTubeIframeAPIReady = () => {};

function show(el, visible) { el.hidden = !visible; }

function setError(msg) {
  $("error").textContent = msg || "";
  show($("error"), Boolean(msg));
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => (k === "class" ? (node.className = v) : node.setAttribute(k, v)));
  children.forEach((c) => node.append(c));
  return node;
}

function tsLink(item, seconds) {
  const a = el("a", { class: "ts", href: item.link, target: "_blank", rel: "noopener" }, item.timestamp);
  a.addEventListener("click", (e) => {
    if (player && typeof player.seekTo === "function") {
      e.preventDefault();
      player.seekTo(seconds, true);
      player.playVideo();
      $("player").scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });
  return a;
}

function loadPlayer(videoId) {
  if (!(window.YT && YT.Player)) return; // falls back to plain links
  if (player && player.loadVideoById) { player.cueVideoById(videoId); return; }
  player = new YT.Player("player", { videoId, playerVars: { rel: 0, modestbranding: 1 } });
}

function fmtDuration(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m} min`;
}

function render(data) {
  lastResult = data;
  const v = data.video;
  $("title").textContent = v.title || v.video_id;
  $("channel").textContent = v.channel || "";
  $("tldr").textContent = data.tldr;
  $("summary").textContent = data.summary;
  $("details").textContent =
    `${fmtDuration(v.duration_seconds)} · ${v.transcript_is_generated ? "auto-generated" : "manual"} captions (${v.transcript_language})` +
    ` · ${data.model}${data.cached ? " · cached" : ""}`;

  $("topics").replaceChildren(...data.topics.map((t) => el("span", { class: "tag" }, t)));
  $("key-points").replaceChildren(
    ...data.key_points.map((k) => el("li", {}, tsLink(k, k.timestamp_seconds), el("span", {}, k.point)))
  );
  $("chapters").replaceChildren(
    ...data.chapters.map((c) =>
      el("li", {}, tsLink(c, c.start_seconds), el("div", {}, el("strong", {}, c.title), el("p", {}, c.summary)))
    )
  );
  loadPlayer(v.video_id);
  show($("result"), true);
}

function toMarkdown(d) {
  const lines = [
    `# ${d.video.title || d.video.video_id}`,
    `${d.video.url}`,
    "",
    `**TL;DR:** ${d.tldr}`,
    "",
    "## Summary",
    d.summary,
    "",
    "## Key points",
    ...d.key_points.map((k) => `- [${k.timestamp}](${k.link}) ${k.point}`),
    "",
    "## Chapters",
    ...d.chapters.map((c) => `- [${c.timestamp}](${c.link}) **${c.title}** — ${c.summary}`),
  ];
  return lines.join("\n");
}

$("copy").addEventListener("click", async () => {
  if (!lastResult) return;
  await navigator.clipboard.writeText(toMarkdown(lastResult));
  $("copy").textContent = "Copied!";
  setTimeout(() => ($("copy").textContent = "Copy as Markdown"), 1500);
});

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = $("url").value.trim();
  if (!url) return;

  setError("");
  show($("result"), false);
  show($("loading"), true);
  $("submit").disabled = true;
  const stages = ["Fetching transcript…", "Reading the video…", "Writing summary…"];
  let i = 0;
  $("loading-text").textContent = stages[0];
  const timer = setInterval(() => ($("loading-text").textContent = stages[Math.min(++i, stages.length - 1)]), 4000);

  try {
    const res = await fetch("/api/summarize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) {
      const detail = Array.isArray(data.detail) ? "Please enter a valid URL." : data.detail;
      throw new Error(detail || `Request failed (${res.status})`);
    }
    render(data);
    history.replaceState(null, "", `?v=${data.video.video_id}`);
  } catch (err) {
    setError(err.message || "Something went wrong.");
  } finally {
    clearInterval(timer);
    show($("loading"), false);
    $("submit").disabled = false;
  }
});

// Support shareable links: /?v=VIDEO_ID
const initial = new URLSearchParams(location.search).get("v");
if (initial) {
  $("url").value = `https://www.youtube.com/watch?v=${initial}`;
  $("form").requestSubmit();
}
