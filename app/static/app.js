/* PBP Studio UI logic — plain JS, no dependencies. Polls the local server API. */
const $ = (id) => document.getElementById(id);
let selectedMagic = "Poison";
let pollTimer = null;
let statusCache = null;

async function api(path, body) {
  const opts = body === undefined
    ? {}
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

function setPill(el, text, cls) {
  el.textContent = text;
  el.className = "pill " + cls;
}

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    statusCache = s;
    setPill($("pill-backend"),
      s.swarm.up ? "AI backend: ready" : "AI backend: off",
      s.swarm.up ? "ok" : "warn");
    setPill($("pill-template"),
      s.template.ok ? `Template: ${s.template.source}` : "Template: missing",
      s.template.ok ? "ok" : "warn");
    // settings form
    ["swarm_root", "swarm_url", "template_path", "game_dir"].forEach((k) => {
      if (!$ (k)) return;
      if (document.activeElement !== $(k)) $(k).value = s.settings[k] || "";
    });
    if (document.activeElement !== $("output_dir")) $("output_dir").value = s.settings.output_dir || "";
    if (document.activeElement !== $("creativity")) {
      $("creativity").value = s.settings.creativity ?? 0.55;
      $("creativity-val").textContent = Number($("creativity").value).toFixed(2);
    }
    if (document.activeElement !== $("steps")) $("steps").value = String(s.settings.steps || 40);
    if (document.activeElement !== $("cfg")) $("cfg").value = String(s.settings.cfg ?? 3);
    if (document.activeElement !== $("sampler")) $("sampler").value = s.settings.sampler || "";
    if (document.activeElement !== $("scheduler")) $("scheduler").value = s.settings.scheduler || "";
    if (document.activeElement !== $("seed")) $("seed").value = s.settings.seed || "";
    $("palette_lock").checked = !!s.settings.palette_lock;
    if (document.activeElement !== $("name") && !$("name").value) $("name").value = s.settings.name || "";
    $("footer-info").textContent =
      `${s.app.name} v${s.app.version} — game: ${s.game_dir || "not found"} — local-only server`;
  } catch (e) {
    setPill($("pill-backend"), "server error", "warn");
  }
}

async function loadMagics() {
  const data = await api("/api/magics");
  const grid = $("magic-grid");
  grid.innerHTML = "";
  for (const [num, name] of data.ui) {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.name = name;
    b.innerHTML = `${name}<small>magic #${num}</small>`;
    b.onclick = () => {
      selectedMagic = name;
      [...grid.children].forEach((c) => c.classList.toggle("sel", c === b));
    };
    if (name === selectedMagic) b.classList.add("sel");
    grid.appendChild(b);
  }
  const fav = data.ui.find(([n, m]) => m === (statusCache?.settings?.magic || "Poison"));
  if (fav) [...grid.children].forEach((c) => c.classList.toggle("sel", c.dataset.name === fav[1]));
}

$("color1").oninput = () => { $("color1").dataset.touched = "1"; };
$("color2").oninput = () => { $("color2").dataset.touched = "1"; };
$("creativity").oninput = () => { $("creativity-val").textContent = Number($("creativity").value).toFixed(2); };
$("engine").onchange = () => { $("solid-opts").style.display = $("engine").value === "solid" ? "flex" : "none"; };
[...$("chips").children].forEach((c) => c.onclick = () => { $("design").value = c.textContent; });

$("btn-pick").onclick = async () => {
  const r = await api("/api/pick-folder", {});
  if (r.path) { $("output_dir").value = r.path; persistSettings(); }
};
$("btn-open").onclick = () => api("/api/open-folder", { path: $("output_dir").value });
$("btn-open-out").onclick = () => api("/api/open-folder", { path: $("output_dir").value });

$("btn-settings").onclick = () => {
  const card = $("settings-card");
  card.style.display = card.style.display === "none" ? "block" : "none";
};
$("btn-save-settings").onclick = async () => {
  await persistSettings();
  alert("Settings saved.");
};
$("btn-redownload").onclick = async () => {
  try { const r = await api("/api/redownload-template", {}); alert(`Template ready: ${r.source}`); refreshStatus(); }
  catch (e) { alert("Failed: " + e.message); }
};
$("btn-start-backend").onclick = async () => {
  setPill($("pill-backend"), "AI backend: starting…", "warn");
  try { await api("/api/start-backend", {}); } catch (e) { alert("Failed: " + e.message); }
  refreshStatus();
};

async function persistSettings() {
  const body = {
    output_dir: $("output_dir").value.trim(),
    swarm_root: $("swarm_root").value.trim(),
    swarm_url: $("swarm_url").value.trim(),
    template_path: $("template_path").value.trim(),
    game_dir: $("game_dir").value.trim(),
    creativity: Number($("creativity").value),
    steps: Number($("steps").value),
    cfg: Number($("cfg").value),
    sampler: $("sampler").value.trim(),
    scheduler: $("scheduler").value.trim(),
    seed: Number($("seed").value) || 0,
    palette_lock: $("palette_lock").checked,
    name: $("name").value.trim(),
    magic: selectedMagic,
  };
  await api("/api/settings", body);
}

function renderJob(job) {
  $("progress-card").style.display = "block";
  $("progress-phase").textContent = job.phase || "";
  const pct = job.total ? Math.round(100 * job.done / job.total) : (job.state === "done" ? 100 : 4);
  $("bar-fill").style.width = pct + "%";
  $("progress-text").textContent =
    job.total ? `${job.done}/${job.total}  ${job.current || ""}` : (job.state || "");
  $("log").textContent = (job.logs || []).join("\n");
  $("log").scrollTop = $("log").scrollHeight;
  if (job.result && job.result.preview) {
    const img = $("live-preview");
    img.style.display = "block";
    img.src = `/api/file?p=${encodeURIComponent(job.result.preview)}&t=${Date.now()}`;
  }
  const running = job.state === "running" || job.state === "queued";
  $("btn-start").disabled = running;
  $("btn-cancel").style.display = running ? "inline-block" : "none";
  if (job.state === "done") finishJob(job);
  if (job.state === "error") { alert("Generation failed:\n" + job.error); }
}

function finishJob(job) {
  clearInterval(pollTimer); pollTimer = null;
  $("result-card").style.display = "block";
  const r = job.result || {};
  if (r.painting) $("res-painting").src = `/api/file?p=${encodeURIComponent(r.painting)}&t=${Date.now()}`;
  if (r.sheet) $("res-sheet").src = `/api/file?p=${encodeURIComponent(r.sheet)}&t=${Date.now()}`;
  $("res-path").textContent = r.export_dir || "";
  refreshStatus();
}

$("btn-start").onclick = async () => {
  const design = $("design").value.trim();
  if (!design) { alert("Describe your character first (step 1)."); return; }
  if (!$("output_dir").value.trim()) { alert("Pick an output folder (step 3)."); return; }
  try {
    await persistSettings();
    $("result-card").style.display = "none";
    await api("/api/job", {
      design,
      extra_style: $("extra_style").value,
      name: $("name").value || "Custom Character",
      magic: selectedMagic,
      mode: $("mode").value,
      engine: $("engine").value,
      creativity: Number($("creativity").value),
      steps: Number($("steps").value),
      cfg: Number($("cfg").value),
      sampler: $("sampler").value.trim(),
      scheduler: $("scheduler").value.trim(),
      seed: Number($("seed").value) || 0,
      output_dir: $("output_dir").value.trim(),
      color1: $("color1").dataset.touched ? $("color1").value : "",
      color2: $("color2").dataset.touched ? $("color2").value : "",
    });
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      try {
        const job = await api("/api/job");
        renderJob(job);
        if (job.state && job.state !== "running" && job.state !== "queued") clearInterval(pollTimer);
      } catch (e) { /* transient */ }
    }, 1200);
  } catch (e) {
    alert("Could not start: " + e.message);
  }
};
$("btn-cancel").onclick = () => api("/api/cancel", {});

$("btn-install").onclick = async () => {
  const job = await api("/api/job");
  if (!job.result || !job.result.export_dir) { alert("Generate a character first."); return; }
  try {
    const r = await api("/api/install-to-game", { source_dir: job.result.export_dir, name: job.result.name });
    alert("Installed to:\n" + r.installed_to + "\n\nIt will show up wherever the game lists local painter characters.");
  } catch (e) { alert("Install failed: " + e.message); }
};

(async function init() {
  await refreshStatus();
  await loadMagics();
  try { const job = await api("/api/job"); if (job.state && job.state !== "none") renderJob(job); } catch {}
  setInterval(refreshStatus, 15000);
})();
