// Charts for the progress page, drawn as SVG through DOM calls only: no HTML strings, and colors
// come from classes in style.css (the CSP forbids inline styles). Every chart is single-series,
// shows its values on hover and keyboard focus, and has a table view.
"use strict";

const Charts = (() => {
  const NS = "http://www.w3.org/2000/svg";

  function svg(tag, attrs = {}, cls) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
    if (cls) n.setAttribute("class", cls);
    return n;
  }

  function label(x, y, text, cls, anchor = "start") {
    const t = svg("text", { x, y, "text-anchor": anchor }, cls);
    t.textContent = text;
    return t;
  }

  // Shorten a label (already in the DOM, so it can be measured) to fit `max` pixels. The full text
  // stays in the tooltip, the aria label and the table view.
  function fit(t, max) {
    const full = t.textContent;
    if (t.getComputedTextLength() <= max) return;
    let n = full.length;
    while (n > 1 && t.getComputedTextLength() > max) t.textContent = `${full.slice(0, --n).trimEnd()}…`;
  }

  function div(cls, text) {
    const n = document.createElement("div");
    n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  // Round tick steps (1, 2, 5 x 10^n; 2.5 too when fractions are fine) covering 0..max.
  function ticks(max, integer = true) {
    const top = Math.max(max, integer ? 4 : 1);
    const raw = top / 4;
    const mag = 10 ** Math.floor(Math.log10(raw));
    const steps = (integer && mag < 10 ? [1, 2, 5, 10] : [1, 2, 2.5, 5, 10]).map((m) => m * mag);
    const step = steps.find((s) => s >= raw) ?? steps[steps.length - 1];
    const out = [];
    for (let v = 0; v <= top + step / 2 && out.length < 12; v += step) out.push(Math.round(v * 1000) / 1000);
    if (out[out.length - 1] < top) out.push(out[out.length - 1] + step);
    return out;
  }

  // Charts are drawn at the container's width and redrawn when the window is resized.
  const drawn = new Map();
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      for (const [box, draw] of drawn) {
        if (!box.isConnected) drawn.delete(box);
        else if (box.offsetParent !== null) draw();
      }
    }, 150);
  });

  function mount(box, draw) {
    box.classList.add("chart");
    drawn.set(box, draw);
    draw();
  }

  function width(box) {
    return Math.max(260, Math.floor(box.clientWidth || box.parentElement?.clientWidth || 600));
  }

  // One tooltip per chart: the value leads, the details follow.
  function tooltip(box) {
    const tip = div("chart-tip");
    tip.hidden = true;
    box.append(tip);
    return {
      show(x, y, value, lines) {
        tip.replaceChildren(div("chart-tip-value", value), ...lines.map((l) => div("chart-tip-line", l)));
        tip.hidden = false;
        const w = tip.offsetWidth;
        const left = Math.min(Math.max(0, x + 12), Math.max(0, box.clientWidth - w));
        tip.style.left = `${left}px`;
        tip.style.top = `${Math.max(0, y - tip.offsetHeight - 10)}px`;
      },
      hide() { tip.hidden = true; },
    };
  }

  /* Line chart over an ordered sequence (sessions or answers), evenly spaced.
     points: [{ y (number or null), tick (short x label), when (tooltip heading), detail: [lines],
                hollow (draw an open marker, e.g. a wrong answer) }] */
  function line(box, { points, yMax, integer = true, height = 200, format = String, name = "Chart", xTitle = "" }) {
    mount(box, () => {
      const W = width(box);
      const H = height;
      const m = { left: 40, right: 44, top: 14, bottom: xTitle ? 40 : 26 };
      const pw = W - m.left - m.right;
      const ph = H - m.top - m.bottom;
      const values = points.map((p) => p.y).filter((v) => v !== null && v !== undefined);
      const yt = ticks(yMax ?? Math.max(0, ...values), integer);
      const top = yt[yt.length - 1];
      const n = points.length;
      const x = (i) => m.left + (n === 1 ? pw / 2 : (i * pw) / (n - 1));
      const y = (v) => m.top + ph * (1 - v / top);

      const root = svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": name });
      for (const t of yt) {
        root.append(svg("line", { x1: m.left, x2: m.left + pw, y1: y(t), y2: y(t) }, t === 0 ? "axis" : "grid"),
          label(m.left - 6, y(t) + 4, format(t), "tick", "end"));
      }
      // x labels: the last point, the first, then others while they neither crowd nor repeat a label
      const chosen = [];
      const fits = (i) => points[i].tick && chosen.every((j) => Math.abs(x(j) - x(i)) >= 64 && points[j].tick !== points[i].tick);
      for (const i of [n - 1, 0, ...points.keys()]) {
        if (i >= 0 && !chosen.includes(i) && fits(i)) chosen.push(i);
      }
      for (const i of chosen) {
        const anchor = n === 1 ? "middle" : i === 0 ? "start" : i === n - 1 ? "end" : "middle";
        root.append(label(x(i), m.top + ph + 16, points[i].tick, "tick", anchor));
      }
      if (xTitle) root.append(label(m.left + pw / 2, H - 6, xTitle, "tick", "middle"));

      let d = "";
      let pen = false;
      points.forEach((p, i) => {
        if (p.y === null || p.y === undefined) { pen = false; return; }
        d += `${pen ? "L" : "M"}${x(i).toFixed(1)} ${y(p.y).toFixed(1)}`;
        pen = true;
      });
      if (d) root.append(svg("path", { d }, "line"));
      const marks = n <= 40;  // markers on every point only while they don't clutter
      points.forEach((p, i) => {
        if (p.y === null || p.y === undefined) return;
        if (marks || i === n - 1) root.append(svg("circle", { cx: x(i), cy: y(p.y), r: 4 }, p.hollow ? "dot hollow" : "dot"));
      });
      const last = [...points].reverse().find((p) => p.y !== null && p.y !== undefined);
      if (last) root.append(label(x(points.lastIndexOf(last)) + 8, y(last.y) + 4, format(last.y), "end-label"));

      const cross = svg("line", { y1: m.top, y2: m.top + ph }, "crosshair");
      const ring = svg("circle", { r: 6 }, "focus-dot");
      cross.setAttribute("visibility", "hidden");
      ring.setAttribute("visibility", "hidden");
      const hit = svg("rect", { x: m.left - 8, y: 0, width: pw + 16, height: m.top + ph + 8, tabindex: 0 }, "hit");
      hit.setAttribute("aria-label", `${name}: use the arrow keys to read each point`);
      root.append(cross, ring, hit);
      box.replaceChildren(root);
      const tip = tooltip(box);

      let at = n - 1;
      const showAt = (i) => {
        at = Math.max(0, Math.min(n - 1, i));
        const p = points[at];
        cross.setAttribute("x1", x(at));
        cross.setAttribute("x2", x(at));
        cross.setAttribute("visibility", "visible");
        if (p.y !== null && p.y !== undefined) {
          ring.setAttribute("cx", x(at));
          ring.setAttribute("cy", y(p.y));
          ring.setAttribute("visibility", "visible");
        } else ring.setAttribute("visibility", "hidden");
        tip.show(x(at), p.y === null || p.y === undefined ? m.top + ph / 2 : y(p.y),
          p.y === null || p.y === undefined ? "no value" : format(p.y), [p.when ?? "", ...(p.detail ?? [])].filter(Boolean));
      };
      const hide = () => { cross.setAttribute("visibility", "hidden"); ring.setAttribute("visibility", "hidden"); tip.hide(); };
      hit.addEventListener("pointermove", (e) => {
        const r = root.getBoundingClientRect();
        const px = e.clientX - r.left;
        showAt(n === 1 ? 0 : Math.round(((px - m.left) / pw) * (n - 1)));
      });
      hit.addEventListener("pointerleave", hide);
      hit.addEventListener("focus", () => showAt(at));
      hit.addEventListener("blur", hide);
      hit.addEventListener("keydown", (e) => {
        const moves = { ArrowLeft: -1, ArrowRight: 1, Home: -n, End: n };
        if (e.key in moves) { e.preventDefault(); showAt(at + moves[e.key]); }
        else if (e.key === "Escape") hide();
      });
    });
  }

  /* Horizontal bars, one row per category, label above its bar (fits phone widths).
     rows: [{ label, value (number or null), valueText, empty (text when null), detail: [lines] }] */
  function bars(box, { rows, max = 100, name = "Chart" }) {
    mount(box, () => {
      const W = width(box);
      const rowH = 42;
      const H = rows.length * rowH + 4;
      const left = 0;
      const right = 56;  // room for the value at the bar's end
      const pw = W - left - right;
      const root = svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": name });
      box.replaceChildren(root);
      const tip = tooltip(box);
      rows.forEach((r, i) => {
        const y0 = i * rowH;
        const g = svg("g", {}, "bar-row");
        const name = label(left, y0 + 14, r.label, "row-label");
        g.append(name);
        root.append(g);
        fit(name, W - 4);
        const by = y0 + 21;
        const bh = 14;
        g.append(svg("rect", { x: left, y: by, width: pw, height: bh, rx: 4 }, "track"));
        if (r.value === null || r.value === undefined) {
          g.append(label(left + 6, by + 11, r.empty ?? "no data", "tick"));
        } else {
          const w = Math.max(0, (pw * Math.min(r.value, max)) / max);
          const rad = Math.min(4, w / 2, bh / 2);
          // square at the baseline, rounded at the data end
          g.append(svg("path", {
            d: `M${left} ${by}H${left + w - rad}A${rad} ${rad} 0 0 1 ${left + w} ${by + rad}V${by + bh - rad}` +
               `A${rad} ${rad} 0 0 1 ${left + w - rad} ${by + bh}H${left}Z`,
          }, "bar"));
          g.append(label(left + w + 6, by + 11, r.valueText ?? String(r.value), "value"));
        }
        const hit = svg("rect", { x: 0, y: y0, width: W, height: rowH, tabindex: 0 }, "hit");
        hit.setAttribute("aria-label", [r.label, r.valueText ?? r.empty ?? "", ...(r.detail ?? [])].join(", "));
        const on = () => { g.classList.add("lift"); tip.show(Math.min(W - 40, left + (pw * Math.min(r.value ?? 0, max)) / max), by, r.valueText ?? r.empty ?? "", [r.label, ...(r.detail ?? [])]); };
        const off = () => { g.classList.remove("lift"); tip.hide(); };
        hit.addEventListener("pointerenter", on);
        hit.addEventListener("pointerleave", off);
        hit.addEventListener("focus", on);
        hit.addEventListener("blur", off);
        g.append(hit);
      });
    });
  }

  /* Vertical columns on a 0..max scale.
     cols: [{ label, short and subShort (used when narrow), sub, value (number or null), valueText, detail: [lines] }] */
  function columns(box, { cols, max = 100, height = 210, format = String, name = "Chart" }) {
    mount(box, () => {
      const W = width(box);
      const H = height;
      const m = { left: 40, right: 8, top: 18, bottom: 44 };
      const pw = W - m.left - m.right;
      const ph = H - m.top - m.bottom;
      const yt = ticks(max, true);
      const top = yt[yt.length - 1];
      const y = (v) => m.top + ph * (1 - v / top);
      const slot = pw / cols.length;
      const cw = Math.min(24, slot * 0.5);
      const root = svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": name });
      for (const t of yt) {
        root.append(svg("line", { x1: m.left, x2: m.left + pw, y1: y(t), y2: y(t) }, t === 0 ? "axis" : "grid"),
          label(m.left - 6, y(t) + 4, format(t), "tick", "end"));
      }
      box.replaceChildren(root);
      const tip = tooltip(box);
      cols.forEach((c, i) => {
        const cx = m.left + slot * i + slot / 2;
        const g = svg("g", {}, "bar-row");
        if (c.value !== null && c.value !== undefined) {
          const h = (ph * Math.min(c.value, top)) / top;
          const x0 = cx - cw / 2;
          const yb = m.top + ph;
          const rad = Math.min(4, h / 2, cw / 2);
          g.append(svg("path", {
            d: `M${x0} ${yb}V${yb - h + rad}A${rad} ${rad} 0 0 1 ${x0 + rad} ${yb - h}H${x0 + cw - rad}` +
               `A${rad} ${rad} 0 0 1 ${x0 + cw} ${yb - h + rad}V${yb}Z`,
          }, "bar"));
          g.append(label(cx, yb - h - 6, c.valueText ?? format(c.value), "value", "middle"));
        } else {
          g.append(label(cx, m.top + ph - 6, "none", "tick", "middle"));
        }
        const narrow = slot < 92;  // short labels where the full ones would collide
        g.append(label(cx, m.top + ph + 17, narrow && c.short ? c.short : c.label, "row-label", "middle"),
          label(cx, m.top + ph + 35, (narrow ? c.subShort : null) ?? c.sub ?? "", "tick", "middle"));
        const hit = svg("rect", { x: cx - slot / 2, y: 0, width: slot, height: H, tabindex: 0 }, "hit");
        hit.setAttribute("aria-label", [c.label, c.valueText ?? "none", ...(c.detail ?? [])].join(", "));
        const on = () => { g.classList.add("lift"); tip.show(cx, c.value === null || c.value === undefined ? m.top + ph / 2 : y(c.value), c.valueText ?? "none", [c.label, ...(c.detail ?? [])]); };
        const off = () => { g.classList.remove("lift"); tip.hide(); };
        hit.addEventListener("pointerenter", on);
        hit.addEventListener("pointerleave", off);
        hit.addEventListener("focus", on);
        hit.addEventListener("blur", off);
        g.append(hit);
        root.append(g);
      });
    });
  }

  // The chart's numbers as a table (the accessible twin of every chart).
  function tableView(head, rows, summary = "Show as a table") {
    const box = document.createElement("details");
    box.className = "table-view";
    const s = document.createElement("summary");
    s.textContent = summary;
    const wrap = div("table-wrap");
    const t = document.createElement("table");
    const hr = document.createElement("tr");
    for (const h of head) { const th = document.createElement("th"); th.textContent = h; hr.append(th); }
    const thead = document.createElement("thead");
    thead.append(hr);
    const tbody = document.createElement("tbody");
    for (const r of rows) {
      const tr = document.createElement("tr");
      for (const c of r) { const td = document.createElement("td"); td.textContent = c; tr.append(td); }
      tbody.append(tr);
    }
    t.append(thead, tbody);
    wrap.append(t);
    box.append(s, wrap);
    return box;
  }

  return { line, bars, columns, tableView };
})();
