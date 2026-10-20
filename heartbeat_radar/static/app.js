"use strict";

if (new URLSearchParams(location.search).has("kiosk")) {
  document.documentElement.classList.add("kiosk");
}

// --- Live data -------------------------------------------------------------

let latest = null;        // last snapshot from the server
let lastMessageAt = 0;
const tracks = new Map(); // track id -> smoothed dot {x, y, tx, ty, vitals, seen}
const wave = [];          // recent heart-phase samples for the waveform
const WAVE_SAMPLES = 200; // ~10 s at the radar's ~20 Hz phase rate

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (event) => onSnapshot(JSON.parse(event.data));
  ws.onclose = () => {
    setStatus("bad", "Disconnected from Pi, retrying…");
    setTimeout(connect, 2000);
  };
}

function onSnapshot(msg) {
  latest = msg;
  lastMessageAt = performance.now();

  const seen = new Set();
  for (const p of msg.people) {
    seen.add(p.id);
    const t = tracks.get(p.id);
    if (t) {
      Object.assign(t, { tx: p.x, ty: p.y, vitals: p.vitals, seen: lastMessageAt });
    } else {
      tracks.set(p.id, { x: p.x, y: p.y, tx: p.x, ty: p.y, vitals: p.vitals, seen: lastMessageAt });
    }
  }
  for (const [id, t] of tracks) {
    if (!seen.has(id)) t.vitals = false;
    if (lastMessageAt - t.seen > 1500) tracks.delete(id);
  }

  for (const v of msg.heart_wave || []) wave.push(v);
  if (wave.length > WAVE_SAMPLES) wave.splice(0, wave.length - WAVE_SAMPLES);

  text("hr", msg.heart_rate != null ? Math.round(msg.heart_rate) : "--");
  text("br", msg.breath_rate != null ? Math.round(msg.breath_rate) : "--");
  text("dist", msg.distance_m != null ? msg.distance_m.toFixed(2) : "--");
  text("count", msg.people.length);
  document.getElementById("empty").hidden = msg.people.length > 0;

  const s = msg.status;
  const label = msg.source === "simulator" ? "Simulated" : s.ok ? "Live" : s.message;
  setStatus(s.ok ? "ok" : s.receiving ? "wait" : "bad", label, s.message);
  text("meta", `source: ${msg.source}${s.firmware ? ` · radar firmware ${s.firmware}` : ""}`);
}

function text(id, value) {
  document.getElementById(id).textContent = value;
}

function setStatus(kind, label, title = "") {
  const el = document.getElementById("status");
  el.className = `pill pill-${kind}`;
  el.title = title;
  text("status-text", label);
}

// --- Heartbeat timing --------------------------------------------------------

// Each beat is a "lub-dub": a strong pulse and a softer one ~0.25 s later.
let beatClock = 0;
let lastBeatAt = -Infinity;

function advanceBeat(dt, now) {
  const bpm = latest && latest.heart_rate;
  if (!bpm) return false;
  beatClock += (dt * bpm) / 60;
  if (beatClock >= 1) {
    beatClock %= 1;
    lastBeatAt = now;
  }
  return true;
}

function pulseAmount(now) {
  const t = (now - lastBeatAt) / 1000;
  if (t < 0 || t > 1.2) return 0;
  const lub = Math.exp(-t * 10);
  const dub = t > 0.25 ? 0.55 * Math.exp(-(t - 0.25) * 10) : 0;
  return lub + dub;
}

// --- Drawing -----------------------------------------------------------------

const map = document.getElementById("map");
const mctx = map.getContext("2d");
const waveCanvas = document.getElementById("wave");
const wctx = waveCanvas.getContext("2d");
const heartIcon = document.getElementById("heart");
const css = getComputedStyle(document.documentElement);
const color = (name) => css.getPropertyValue(name).trim();

function fitCanvas(canvas, ctx) {
  const dpr = window.devicePixelRatio || 1;
  const { width, height } = canvas.getBoundingClientRect();
  if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { w: width, h: height };
}

function drawMap(now, dt, beating) {
  const { w, h } = fitCanvas(map, mctx);
  const view = latest ? latest.view : { max_range_m: 6, fov_deg: 120 };
  const half = (Math.min(view.fov_deg, 180) / 2) * (Math.PI / 180);
  const pad = 28;

  // Sensor sits at the bottom middle, looking "up" into the room.
  const halfWidthM = view.max_range_m * Math.max(Math.sin(half), 0.3);
  const scale = Math.min((h - pad * 2) / view.max_range_m, (w / 2 - pad) / halfWidthM);
  const ox = w / 2;
  const oy = h - pad;
  const toScreen = (x, y) => [ox + x * scale, oy - y * scale];

  mctx.clearRect(0, 0, w, h);

  // Coverage wedge.
  const up = -Math.PI / 2;
  const R = view.max_range_m * scale;
  mctx.beginPath();
  mctx.moveTo(ox, oy);
  mctx.arc(ox, oy, R, up - half, up + half);
  mctx.closePath();
  const fill = mctx.createRadialGradient(ox, oy, 0, ox, oy, R);
  fill.addColorStop(0, "rgba(61, 220, 132, 0.10)");
  fill.addColorStop(1, "rgba(61, 220, 132, 0.02)");
  mctx.fillStyle = fill;
  mctx.fill();
  mctx.strokeStyle = color("--grid-strong");
  mctx.lineWidth = 1;
  mctx.stroke();

  // Range rings with meter labels.
  const step = view.max_range_m > 8 ? 2 : 1;
  mctx.font = "11px system-ui, sans-serif";
  mctx.fillStyle = color("--muted");
  mctx.textAlign = "left";
  for (let m = step; m <= view.max_range_m + 1e-6; m += step) {
    mctx.beginPath();
    mctx.arc(ox, oy, m * scale, up - half, up + half);
    mctx.strokeStyle = color("--grid");
    mctx.stroke();
    const [lx, ly] = [ox + Math.cos(up + half) * m * scale, oy + Math.sin(up + half) * m * scale];
    mctx.fillText(`${m} m`, lx + 4, ly + 4);
  }

  // Spokes every 30°.
  for (let a = -90; a <= 90; a += 30) {
    const rad = (a * Math.PI) / 180;
    if (Math.abs(rad) > half + 1e-6) continue;
    mctx.beginPath();
    mctx.moveTo(ox, oy);
    mctx.lineTo(ox + Math.sin(rad) * R, oy - Math.cos(rad) * R);
    mctx.strokeStyle = color("--grid");
    mctx.stroke();
  }

  // Slow sweep, purely cosmetic.
  const sweep = up - half + ((now / 3000) % 1) * half * 2;
  const sweepGrad = mctx.createLinearGradient(ox, oy, ox + Math.cos(sweep) * R, oy + Math.sin(sweep) * R);
  sweepGrad.addColorStop(0, "rgba(61, 220, 132, 0.35)");
  sweepGrad.addColorStop(1, "rgba(61, 220, 132, 0)");
  mctx.beginPath();
  mctx.moveTo(ox, oy);
  mctx.lineTo(ox + Math.cos(sweep) * R, oy + Math.sin(sweep) * R);
  mctx.strokeStyle = sweepGrad;
  mctx.lineWidth = 2;
  mctx.stroke();
  mctx.lineWidth = 1;

  // The sensor itself.
  mctx.fillStyle = color("--ok");
  mctx.fillRect(ox - 10, oy - 3, 20, 6);
  mctx.fillStyle = color("--muted");
  mctx.textAlign = "center";
  mctx.fillText("sensor", ox, oy + 18);

  // People. Ease toward the latest reported position so motion looks smooth.
  const ease = 1 - Math.exp(-dt * 8);
  const pulse = beating ? pulseAmount(now) : 0;
  const heart = color("--heart");
  for (const t of tracks.values()) {
    t.x += (t.tx - t.x) * ease;
    t.y += (t.ty - t.y) * ease;
    const [sx, sy] = toScreen(t.x, t.y);
    const fade = Math.max(0, 1 - (now - t.seen) / 1500);

    if (t.vitals) {
      const r = 11 * (1 + 0.45 * pulse);
      // Expanding ring on each beat.
      const age = (now - lastBeatAt) / 1000;
      if (beating && age < 1) {
        mctx.beginPath();
        mctx.arc(sx, sy, 11 + age * 45, 0, Math.PI * 2);
        mctx.strokeStyle = `rgba(255, 59, 78, ${0.6 * (1 - age) * fade})`;
        mctx.lineWidth = 2;
        mctx.stroke();
        mctx.lineWidth = 1;
      }
      const glow = mctx.createRadialGradient(sx, sy, 0, sx, sy, r * 3);
      glow.addColorStop(0, `rgba(255, 59, 78, ${(0.35 + 0.4 * pulse) * fade})`);
      glow.addColorStop(1, "rgba(255, 59, 78, 0)");
      mctx.fillStyle = glow;
      mctx.beginPath();
      mctx.arc(sx, sy, r * 3, 0, Math.PI * 2);
      mctx.fill();
      mctx.globalAlpha = fade;
      mctx.fillStyle = heart;
      mctx.beginPath();
      mctx.arc(sx, sy, r, 0, Math.PI * 2);
      mctx.fill();
      if (latest && latest.heart_rate) {
        mctx.fillStyle = color("--text");
        mctx.font = "600 12px system-ui, sans-serif";
        mctx.fillText(`${Math.round(latest.heart_rate)} bpm`, sx, sy - r - 10);
      }
    } else {
      mctx.globalAlpha = 0.75 * fade;
      mctx.fillStyle = "#ff9aa5";
      mctx.beginPath();
      mctx.arc(sx, sy, 8, 0, Math.PI * 2);
      mctx.fill();
    }
    mctx.globalAlpha = fade;
    mctx.fillStyle = color("--muted");
    mctx.font = "11px system-ui, sans-serif";
    mctx.fillText(`${Math.hypot(t.x, t.y).toFixed(1)} m`, sx, sy + 24);
    mctx.globalAlpha = 1;
  }
}

function drawWave() {
  const { w, h } = fitCanvas(waveCanvas, wctx);
  wctx.clearRect(0, 0, w, h);
  if (wave.length < 2) return;
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of wave) {
    lo = Math.min(lo, v);
    hi = Math.max(hi, v);
  }
  const span = hi - lo || 1;
  wctx.beginPath();
  wave.forEach((v, i) => {
    const x = (i / (WAVE_SAMPLES - 1)) * w;
    const y = h - 4 - ((v - lo) / span) * (h - 8);
    if (i === 0) wctx.moveTo(x, y);
    else wctx.lineTo(x, y);
  });
  wctx.strokeStyle = color("--heart");
  wctx.lineWidth = 1.5;
  wctx.stroke();
}

let prev = performance.now();
function frame(now) {
  const dt = Math.min((now - prev) / 1000, 0.1);
  prev = now;
  const beating = advanceBeat(dt, now);
  drawMap(now, dt, beating);
  drawWave();
  heartIcon.classList.toggle("idle", !beating);
  heartIcon.style.transform = `scale(${1 + 0.18 * (beating ? pulseAmount(now) : 0)})`;
  if (latest && now - lastMessageAt > 3000) setStatus("bad", "No data from Pi");
  requestAnimationFrame(frame);
}

connect();
requestAnimationFrame(frame);
