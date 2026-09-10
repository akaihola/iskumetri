"use strict";
const $ = (id) => document.getElementById(id);
const form = $("form"), status = $("status"), go = $("go");
const canvas = $("chart"), tip = $("tooltip"), audio = $("audio");
const ctx = canvas.getContext("2d");
const PAD = { l: 56, r: 12, t: 12, b: 32 };

let data = null;       // { onsets: [s], intervals: [s], duration }
let view = { t0: 0, t1: 1 };
let hover = -1;
let drag = null;

const css = (name) => getComputedStyle(document.querySelector(".viz-root")).getPropertyValue(name).trim();
const fmtTime = (s) => `${Math.floor(s / 60)}:${(s % 60).toFixed(2).padStart(5, "0")}`;
// Axis ticks land on whole seconds, where hundredths are just noise.
// Round to whole seconds *before* splitting, or a tick at 119.9999 renders as "1:60".
const fmtClock = (s) => {
  const t = Math.round(s);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  go.disabled = true;
  status.textContent = "Downloading audio and detecting strokes… this can take a minute.";
  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: $("url").value,
        sensitivity: Number($("sensitivity").value),
        min_interval: Number($("mingap").value) / 1000,
      }),
    });
    if (!res.ok) throw new Error(await errorText(res));
    show(await res.json());
    status.textContent = "";
  } catch (err) {
    status.textContent = `Error: ${err.message}`;
  } finally {
    go.disabled = false;
  }
});

// FastAPI reports our own failures as a string, but a schema violation as an
// array of objects; that array used to reach the user as "[object Object]".
async function errorText(res) {
  const detail = await res.json().then((body) => body.detail, () => null);
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg ?? JSON.stringify(d)).join("; ");
  // statusText is empty over HTTP/2, so lead with the status code.
  return `HTTP ${res.status}${res.statusText ? " " + res.statusText : ""}`;
}

function show(d) {
  data = d;
  $("result").hidden = false;
  $("title").textContent = d.title;
  if (!audio.src.endsWith(`/api/audio/${d.video_id}`)) audio.src = `/api/audio/${d.video_id}`;
  view = { t0: 0, t1: d.duration };
  const ms = d.intervals.map((x) => x * 1000);
  $("summary").textContent = ms.length
    ? `${d.onsets.length} strokes over ${fmtTime(d.duration)}. ` +
      `Shortest gap ${Math.min(...ms).toFixed(0)} ms, longest ${Math.max(...ms).toFixed(0)} ms.`
    : `Only ${d.onsets.length} stroke(s) detected over ${fmtTime(d.duration)} — too few to measure a duration. Try raising sensitivity.`;
  $("table").tBodies[0].replaceChildren(...d.intervals.map((iv, i) => {
    const tr = document.createElement("tr");
    for (const v of [i + 1, d.onsets[i].toFixed(3), (iv * 1000).toFixed(1), (60 / iv).toFixed(1)]) {
      const td = document.createElement("td");
      td.textContent = v;
      tr.append(td);
    }
    return tr;
  }));
  draw();
}

// ---- geometry -------------------------------------------------------------
function plotBox() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  return { x: PAD.l, y: PAD.t, w: w - PAD.l - PAD.r, h: h - PAD.t - PAD.b };
}
const xOf = (t, b) => b.x + ((t - view.t0) / (view.t1 - view.t0)) * b.w;
const tOf = (x, b) => view.t0 + ((x - b.x) / b.w) * (view.t1 - view.t0);

function visibleRange() {
  // indices of bars [i0, i1) overlapping the view
  const on = data.onsets;
  let i0 = lowerBound(on, view.t0) - 1, i1 = lowerBound(on, view.t1);
  return [Math.max(0, i0), Math.min(data.intervals.length, i1)];
}
function lowerBound(arr, v) {
  let lo = 0, hi = arr.length;
  while (lo < hi) { const m = (lo + hi) >> 1; arr[m] < v ? (lo = m + 1) : (hi = m); }
  return lo;
}
function niceStep(range, target) {
  const raw = range / target, p = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw);
}

// ---- drawing --------------------------------------------------------------
function draw() {
  if (!data) return;
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth, H = canvas.clientHeight;
  if (canvas.width !== W * dpr || canvas.height !== H * dpr) { canvas.width = W * dpr; canvas.height = H * dpr; }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  const b = plotBox();
  const [i0, i1] = visibleRange();
  const { onsets: on, intervals: iv } = data;

  let yMax = 0;
  for (let i = i0; i < i1; i++) yMax = Math.max(yMax, iv[i]);
  yMax = (yMax || 1) * 1000 * 1.08;
  const yOf = (ms) => b.y + b.h - (ms / yMax) * b.h;

  // grid + y axis (ms)
  ctx.font = "12px system-ui, sans-serif";
  ctx.fillStyle = css("--text-secondary");
  ctx.strokeStyle = css("--grid");
  ctx.lineWidth = 1;
  ctx.textAlign = "right"; ctx.textBaseline = "middle";
  const ys = niceStep(yMax, 6);
  for (let v = 0; v <= yMax; v += ys) {
    const y = Math.round(yOf(v)) + 0.5;
    ctx.beginPath(); ctx.moveTo(b.x, y); ctx.lineTo(b.x + b.w, y); ctx.stroke();
    ctx.fillText(v.toLocaleString(), b.x - 8, y);
  }
  ctx.save(); ctx.translate(14, b.y + b.h / 2); ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center"; ctx.fillText("ms per stroke", 0, 0); ctx.restore();

  // x axis (time)
  ctx.textAlign = "center"; ctx.textBaseline = "top";
  const xs = niceStep(view.t1 - view.t0, Math.max(3, b.w / 90));
  for (let t = Math.ceil(view.t0 / xs) * xs; t <= view.t1; t += xs) {
    const x = Math.round(xOf(t, b)) + 0.5;
    ctx.beginPath(); ctx.moveTo(x, b.y + b.h); ctx.lineTo(x, b.y + b.h + 4); ctx.stroke();
    ctx.fillText(xs < 1 ? t.toFixed(xs < 0.1 ? 2 : 1) + " s" : fmtClock(t), x, b.y + b.h + 8);
  }

  // bars: one per stroke, spanning to the next stroke, 2px surface gap, rounded top
  ctx.save();
  ctx.beginPath(); ctx.rect(b.x, b.y, b.w, b.h); ctx.clip();
  const fill = css("--series-1"), hoverFill = css("--series-1-hover");
  for (let i = i0; i < i1; i++) {
    const x0 = xOf(on[i], b), x1 = xOf(on[i + 1], b);
    const w = Math.max(1, x1 - x0 - 2);
    const y = yOf(iv[i] * 1000);
    ctx.fillStyle = i === hover ? hoverFill : fill;
    const r = Math.min(4, w / 2, (b.y + b.h - y) / 2);
    ctx.beginPath(); ctx.roundRect(x0 + 1, y, w, b.y + b.h - y, [r, r, 0, 0]); ctx.fill();
  }
  // playhead
  if (audio.src && audio.currentTime >= view.t0 && audio.currentTime <= view.t1) {
    const x = Math.round(xOf(audio.currentTime, b)) + 0.5;
    ctx.strokeStyle = css("--playhead"); ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x, b.y); ctx.lineTo(x, b.y + b.h); ctx.stroke();
  }
  ctx.restore();
  // baseline
  ctx.strokeStyle = css("--text-secondary");
  ctx.beginPath(); ctx.moveTo(b.x, b.y + b.h + 0.5); ctx.lineTo(b.x + b.w, b.y + b.h + 0.5); ctx.stroke();
}

// ---- interaction: wheel zoom, drag pan, hover, click-to-seek, dblclick reset
function setView(t0, t1) {
  const span = Math.max(0.2, Math.min(data.duration, t1 - t0));
  t0 = Math.max(0, Math.min(data.duration - span, t0));
  view = { t0, t1: t0 + span };
  draw();
}
canvas.addEventListener("wheel", (e) => {
  if (!data) return;
  e.preventDefault();
  const b = plotBox(), tc = tOf(e.offsetX, b);
  const k = Math.exp(e.deltaY * 0.0015);
  setView(tc - (tc - view.t0) * k, tc + (view.t1 - tc) * k);
}, { passive: false });
canvas.addEventListener("pointerdown", (e) => {
  if (!data) return;
  drag = { x: e.offsetX, t0: view.t0, t1: view.t1, moved: false };
  canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener("pointermove", (e) => {
  if (!data) return;
  const b = plotBox();
  if (drag) {
    const dt = ((drag.x - e.offsetX) / b.w) * (drag.t1 - drag.t0);
    if (Math.abs(drag.x - e.offsetX) > 3) drag.moved = true;
    setView(drag.t0 + dt, drag.t1 + dt);
    return;
  }
  const t = tOf(e.offsetX, b);
  const i = lowerBound(data.onsets, t) - 1;
  hover = i >= 0 && i < data.intervals.length && e.offsetX >= b.x && e.offsetX <= b.x + b.w ? i : -1;
  if (hover >= 0) {
    const ms = data.intervals[hover] * 1000;
    tip.textContent = `#${hover + 1} at ${fmtTime(data.onsets[hover])} · ${ms.toFixed(1)} ms · ${(60000 / ms).toFixed(0)} strokes/min`;
    tip.hidden = false;
    const wrap = canvas.parentElement.getBoundingClientRect();
    tip.style.left = `${Math.min(e.offsetX + 14, wrap.width - tip.offsetWidth - 4)}px`;
    tip.style.top = `${Math.max(0, e.offsetY - 36)}px`;
  } else tip.hidden = true;
  draw();
});
canvas.addEventListener("pointerup", (e) => {
  if (drag && !drag.moved && audio.src) {
    audio.currentTime = Math.max(0, Math.min(data.duration, tOf(e.offsetX, plotBox())));
    draw();
  }
  drag = null;
});
canvas.addEventListener("pointerleave", () => { hover = -1; tip.hidden = true; draw(); });
canvas.addEventListener("dblclick", () => data && setView(0, data.duration));
new ResizeObserver(draw).observe(canvas);
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", draw);
(function tick() { if (data && !audio.paused) draw(); requestAnimationFrame(tick); })();
audio.addEventListener("seeked", draw);
