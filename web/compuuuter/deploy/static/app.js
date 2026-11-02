"use strict";

// Operation metadata. Numeric `type` matches the server's OPS table.
const OPS = {
  1:  { name: "const", color: "#ffd36b", value: true, arity: 0 },
  2:  { name: "add",   color: "#8ad98a", variadic: true, min: 1 },
  3:  { name: "sub",   color: "#8ad2da", variadic: true, min: 1 },
  4:  { name: "mul",   color: "#dbb188", variadic: true, min: 1 },
  5:  { name: "xor",   color: "#cf9ae6", variadic: true, min: 1 },
  6:  { name: "and",   color: "#a8cdff", variadic: true, min: 1 },
  7:  { name: "or",    color: "#a3f0cf", variadic: true, min: 1 },
  8:  { name: "shl",   color: "#ffa8bb", arity: 2 },
  9:  { name: "shr",   color: "#ffbfa8", arity: 2 },
  10: { name: "mod",   color: "#c3c3ff", arity: 2 },
};

const stage = document.getElementById("stage");
const wires = document.getElementById("wires");
const statusEl = document.getElementById("status");

const nodes = new Map(); // id -> node
let nextId = 1;

// --------------------------------------------------------------------------- //
//  Palette
// --------------------------------------------------------------------------- //
const paletteList = document.getElementById("palette-list");
for (const [type, meta] of Object.entries(OPS)) {
  const b = document.createElement("button");
  b.className = "pal-block";
  b.textContent = meta.name;
  b.style.background = meta.color;
  b.onclick = () => {
    const sr = stage.getBoundingClientRect();
    addNode(Number(type),
      stage.scrollLeft + sr.width / 2 - 85 + (Math.random() * 60 - 30),
      stage.scrollTop + 80 + (Math.random() * 60 - 30));
  };
  paletteList.appendChild(b);
}

// --------------------------------------------------------------------------- //
//  Node model + rendering
// --------------------------------------------------------------------------- //
function addNode(type, x, y, forcedId) {
  const meta = OPS[type];
  const id = forcedId != null ? forcedId : nextId;
  if (forcedId != null) nextId = Math.max(nextId, forcedId + 1);
  else nextId += 1;

  const argCount = meta.arity != null ? meta.arity : (meta.min || 1);
  const node = {
    id, type, x, y,
    value: 0,
    args: new Array(argCount).fill(null),
    el: null,
  };
  nodes.set(id, node);
  renderNode(node);
  redrawWires();
  return node;
}

function renderNode(node) {
  const meta = OPS[node.type];
  const el = document.createElement("div");
  el.className = "node";
  el.style.left = node.x + "px";
  el.style.top = node.y + "px";
  el.dataset.id = node.id;
  node.el = el;

  const head = document.createElement("div");
  head.className = "head";
  head.style.background = meta.color;
  head.innerHTML = `<span>${meta.name}</span><span class="id">#${node.id}</span>`;
  const del = document.createElement("button");
  del.className = "del";
  del.textContent = "×";
  del.onclick = (e) => { e.stopPropagation(); removeNode(node.id); };
  head.appendChild(del);
  el.appendChild(head);

  const body = document.createElement("div");
  body.className = "body";

  if (meta.value) {
    const inp = document.createElement("input");
    inp.className = "value";
    inp.type = "text";
    inp.value = node.value;
    inp.oninput = () => { node.value = inp.value; };
    body.appendChild(inp);
  }

  const slotsWrap = document.createElement("div");
  slotsWrap.className = "slots";
  body.appendChild(slotsWrap);
  node._slotsWrap = slotsWrap;
  renderSlots(node);

  if (meta.variadic) {
    const btns = document.createElement("div");
    btns.className = "slotbtns";
    const add = document.createElement("button");
    add.textContent = "+";
    add.onclick = () => { node.args.push(null); renderSlots(node); redrawWires(); };
    const rem = document.createElement("button");
    rem.textContent = "−";
    rem.onclick = () => {
      if (node.args.length > (meta.min || 1)) { node.args.pop(); renderSlots(node); redrawWires(); }
    };
    btns.append(add, rem);
    body.appendChild(btns);
  }

  const outRow = document.createElement("div");
  outRow.className = "out-row";
  outRow.innerHTML = `<span class="lbl">out</span>`;
  const outDot = document.createElement("div");
  outDot.className = "dot out-dot";
  outDot.onpointerdown = (e) => startWire(e, node);
  outRow.appendChild(outDot);
  body.appendChild(outRow);

  const res = document.createElement("div");
  res.className = "result";
  node._result = res;
  body.appendChild(res);

  el.appendChild(body);
  stage.appendChild(el);

  head.onpointerdown = (e) => startDragNode(e, node);
}

function renderSlots(node) {
  const wrap = node._slotsWrap;
  wrap.innerHTML = "";
  node.args.forEach((src, i) => {
    const slot = document.createElement("div");
    slot.className = "slot in";
    slot.dataset.node = node.id;   // whole slot is a drop target
    slot.dataset.arg = i;
    const dot = document.createElement("div");
    dot.className = "dot in-dot";
    dot.dataset.node = node.id;
    dot.dataset.arg = i;
    const drop = document.createElement("div");
    drop.className = "drop" + (src != null ? " filled" : "");
    drop.dataset.node = node.id;
    drop.dataset.arg = i;
    drop.textContent = src != null ? `#${src}` : `arg ${i}`;
    drop.onclick = () => { if (node.args[i] != null) { node.args[i] = null; renderSlots(node); redrawWires(); } };
    slot.append(dot, drop);
    wrap.appendChild(slot);
  });
}

function removeNode(id) {
  const node = nodes.get(id);
  if (!node) return;
  node.el.remove();
  nodes.delete(id);
  // drop dangling references
  for (const n of nodes.values()) {
    n.args = n.args.map((a) => (a === id ? null : a));
    renderSlots(n);
  }
  redrawWires();
}

// --------------------------------------------------------------------------- //
//  Dragging nodes
// --------------------------------------------------------------------------- //
function startDragNode(e, node) {
  if (e.target.classList.contains("del")) return;
  e.preventDefault();
  const sr = stage.getBoundingClientRect();
  const offX = e.clientX - sr.left + stage.scrollLeft - node.x;
  const offY = e.clientY - sr.top + stage.scrollTop - node.y;
  function move(ev) {
    node.x = Math.max(0, ev.clientX - sr.left + stage.scrollLeft - offX);
    node.y = Math.max(0, ev.clientY - sr.top + stage.scrollTop - offY);
    node.el.style.left = node.x + "px";
    node.el.style.top = node.y + "px";
    redrawWires();
  }
  function up() {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
  }
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
}

// --------------------------------------------------------------------------- //
//  Wiring
// --------------------------------------------------------------------------- //
let tempPath = null;
function startWire(e, srcNode) {
  e.preventDefault();
  e.stopPropagation();
  try { e.target.setPointerCapture(e.pointerId); } catch (_) { /* ok */ }
  tempPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
  tempPath.style.strokeDasharray = "6 5";
  wires.appendChild(tempPath);
  const from = dotPoint(srcNode.el.querySelector(".out-dot"));

  function move(ev) {
    const p = toStage(ev.clientX, ev.clientY);
    tempPath.setAttribute("d", bezier(from, p));
  }
  function up(ev) {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    tempPath.remove();
    tempPath = null;
    const target = document.elementFromPoint(ev.clientX, ev.clientY);
    // Accept a drop anywhere on an input slot (dot, label or padding).
    const slot = target && target.closest(".slot.in");
    if (slot) {
      const tgt = nodes.get(Number(slot.dataset.node));
      const i = Number(slot.dataset.arg);
      if (tgt && tgt.id !== srcNode.id) {
        tgt.args[i] = srcNode.id;
        renderSlots(tgt);
        redrawWires();
      }
    }
  }
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
}

function toStage(clientX, clientY) {
  const sr = stage.getBoundingClientRect();
  return { x: clientX - sr.left + stage.scrollLeft, y: clientY - sr.top + stage.scrollTop };
}
function dotPoint(dot) {
  const r = dot.getBoundingClientRect();
  return toStage(r.left + r.width / 2, r.top + r.height / 2);
}
function bezier(a, b) {
  const dx = Math.max(40, Math.abs(b.x - a.x) * 0.5);
  return `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
}

function redrawWires() {
  wires.innerHTML = "";
  for (const node of nodes.values()) {
    node.args.forEach((src, i) => {
      if (src == null) return;
      const srcNode = nodes.get(src);
      if (!srcNode) return;
      const from = dotPoint(srcNode.el.querySelector(".out-dot"));
      const inDot = node.el.querySelector(`.in-dot[data-arg="${i}"]`);
      if (!inDot) return;
      const to = dotPoint(inDot);
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", bezier(from, to));
      wires.appendChild(path);
    });
  }
}

// --------------------------------------------------------------------------- //
//  Serialize + run
// --------------------------------------------------------------------------- //
function serialize() {
  const out = [];
  for (const node of nodes.values()) {
    const meta = OPS[node.type];
    const n = {
      id: node.id,
      type: node.type,
      args: node.args.filter((a) => a != null),
    };
    if (meta.value) {
      const v = parseInt(node.value, 10);
      n.value = Number.isFinite(v) ? v : 0;
    }
    out.push(n);
  }
  return out;
}

async function run() {
  const payload = { nodes: serialize() };
  if (payload.nodes.length === 0) { flash("Add some blocks first.", true); return; }
  try {
    let r = await fetch("/api/graph", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    let data = await r.json();
    if (!r.ok) throw new Error(data.error || "upload failed");
    const gid = data.id;

    r = await fetch(`/api/graph/${gid}/compute`, { method: "POST" });
    data = await r.json();
    if (!r.ok) throw new Error(data.error || "compute failed");

    showResults(data.results);
    flash("Graph computed ✔");
  } catch (err) {
    flash(err.message, true);
  }
}

function showResults(results) {
  for (const node of nodes.values()) {
    const res = node._result;
    const v = results[String(node.id)];
    if (v === undefined) { res.classList.remove("show"); continue; }
    res.textContent = "= " + v;
    res.classList.add("show");
  }
}

function flash(msg, isErr) {
  statusEl.textContent = msg;
  statusEl.className = "status show" + (isErr ? " err" : "");
  clearTimeout(flash._t);
  flash._t = setTimeout(() => (statusEl.className = "status"), 3200);
}

// --------------------------------------------------------------------------- //
//  Toolbar
// --------------------------------------------------------------------------- //
document.getElementById("btn-run").onclick = run;
document.getElementById("btn-clear").onclick = () => {
  for (const id of [...nodes.keys()]) removeNode(id);
  nextId = 1;
};

const jsonDialog = document.getElementById("json-dialog");
const jsonArea = document.getElementById("json-area");
document.getElementById("btn-json").onclick = () => {
  jsonArea.value = JSON.stringify({ nodes: serialize() }, null, 2);
  jsonDialog.showModal();
};
jsonDialog.addEventListener("close", () => {
  if (jsonDialog.returnValue !== "load") return;
  try {
    const parsed = JSON.parse(jsonArea.value);
    loadGraph(parsed.nodes || []);
    flash("Loaded graph.");
  } catch (e) {
    flash("Bad JSON: " + e.message, true);
  }
});

function loadGraph(list) {
  for (const id of [...nodes.keys()]) removeNode(id);
  nextId = 1;
  let i = 0;
  for (const n of list) {
    if (!OPS[n.type]) continue; // only known ops are editable in the UI
    const col = 220 * (i % 4) + 30;
    const row = 170 * Math.floor(i / 4) + 30;
    const node = addNode(n.type, col, row, n.id);
    node.value = n.value ?? 0;
    node.args = Array.isArray(n.args) ? n.args.slice() : [];
    if (node.args.length === 0 && !OPS[n.type].value) node.args = [null];
    node.el.remove();
    renderNode(node);
    i += 1;
  }
  redrawWires();
}

// Start with a friendly example: (40 + 2).
window.addEventListener("load", () => {
  const a = addNode(1, 60, 60);
  a.value = 40;
  a.el.querySelector(".value").value = 40;
  const b = addNode(1, 60, 210);
  b.value = 2;
  b.el.querySelector(".value").value = 2;
  const add = addNode(2, 340, 120);
  add.args = [a.id, b.id];
  renderSlots(add);
  redrawWires();
});
