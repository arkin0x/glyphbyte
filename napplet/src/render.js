// Canvas rendering: bytes to symbols to copy from, the reference sheet, and the detection overlay.
// SHAPES is the canonical list: [{name, outer:[[x,y]...], features:[[[x,y]...]]}] in a unit box.

function glyphPath(ctx, shape, rot, cx, cy, size) {
  const t = rot * Math.PI / 2, c = Math.cos(t), s = Math.sin(t);
  const put = (poly) => { poly.forEach((p, i) => { const x = cx + (p[0] * c - p[1] * s) * size, y = cy + (p[0] * s + p[1] * c) * size; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.closePath(); };
  ctx.beginPath(); put(shape.outer); for (const f of shape.features) put(f);
}

export function drawCell(ctx, SHAPES, byte, cx, cy, cell, lw) {
  const g = { symbol: byte >> 4, rotation: (byte >> 2) & 3, fill: (byte >> 1) & 1, frame: byte & 1 };
  ctx.lineWidth = lw; ctx.strokeStyle = '#000'; ctx.fillStyle = '#000'; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
  ctx.beginPath();
  if (g.frame) ctx.arc(cx, cy, cell / 2, 0, 2 * Math.PI); else ctx.rect(cx - cell / 2, cy - cell / 2, cell, cell);
  ctx.stroke();
  const size = cell * (g.frame ? 0.56 : 0.62);
  glyphPath(ctx, SHAPES[g.symbol], g.rotation, cx, cy, size);
  if (g.fill) ctx.fill('evenodd');
  ctx.stroke();
}

// returns the canvas size used; bytes is an array of 0..255
export function drawRow(canvas, SHAPES, bytes, cell = 120, baseline = true) {
  const margin = Math.round(cell * 0.6), pitch = cell * 1.35, n = bytes.length;
  const W = Math.round(margin * 2 + pitch * n), H = Math.round(margin * 2 + cell * 1.5);
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H);
  const lw = Math.max(2, cell * 0.045), y = margin + cell * 0.55;
  bytes.forEach((b, i) => drawCell(ctx, SHAPES, b, margin + cell * 0.6 + pitch * i, y, cell, lw));
  if (baseline && n) {
    const y0 = y + cell * 0.72, x0 = margin * 0.5, x1 = W - margin * 0.5;
    ctx.lineWidth = lw; ctx.strokeStyle = '#000'; ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y0); ctx.stroke();
    ctx.fillStyle = '#000'; ctx.beginPath(); ctx.arc(x0, y0, Math.max(3, cell * 0.13), 0, 2 * Math.PI); ctx.fill();
  }
  return { W, H };
}

export function drawSheet(canvas, SHAPES, cell = 64) {
  const rows = 16, cols = 8, pitch = Math.round(cell * 1.25);
  canvas.width = pitch * cols + cell; canvas.height = pitch * rows + cell;
  const ctx = canvas.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  for (let s = 0; s < 16; s++) for (let c = 0; c < cols; c++) {
    const fill = c >> 2, rot = c & 3, frame = (s + c) & 1, b = (s << 4) | (rot << 2) | (fill << 1) | frame;
    drawCell(ctx, SHAPES, b, cell * 0.6 + pitch * c, cell * 0.6 + pitch * s, cell, Math.max(2, cell * 0.045));
  }
}

// draw what the detector found on top of the (downscaled) photo already painted on the canvas
export function drawDetection(ctx, det) {
  ctx.lineWidth = 2; ctx.font = '14px sans-serif';
  det.frames.forEach((f, i) => {
    ctx.strokeStyle = f.kind === 0 ? '#00c853' : '#ff9100'; ctx.beginPath();
    f.hull.forEach((p, k) => k ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); ctx.stroke();
    ctx.fillStyle = '#ff1744'; ctx.fillText(String(i), f.center[0] - 4, f.center[1] + 5);
  });
  if (det.baseline) {
    const [a, b] = det.baseline; ctx.strokeStyle = '#d500f9'; ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
    ctx.beginPath(); ctx.arc(a[0], a[1], 8, 0, 2 * Math.PI); ctx.lineWidth = det.startKnown ? 3 : 1; ctx.stroke();
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2; ctx.strokeStyle = '#ffea00'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(mx, my); ctx.lineTo(mx + det.up[0] * 40, my + det.up[1] * 40); ctx.stroke();
  }
}
