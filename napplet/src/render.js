// Canvas rendering: bytes to glyphs to copy from, the reference sheet, and the detection overlay.
// SHAPES is the icon list (shapes.json): {icons: [{name, strokes: [{points: [[x, y]...], closed}]}], icon_scale,
// dot_offset, dot_radius} in a unit box, y down, upright.

export function drawCell(ctx, SHAPES, byte, cx, cy, cell, lw) {
  ctx.lineWidth = lw; ctx.strokeStyle = '#000'; ctx.fillStyle = '#000'; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
  ctx.beginPath(); ctx.rect(cx - cell / 2, cy - cell / 2, cell, cell); ctx.stroke();
  const size = cell * SHAPES.icon_scale;
  for (const st of SHAPES.icons[byte >> 4].strokes) {
    ctx.beginPath();
    st.points.forEach((p, i) => { const x = cx + p[0] * size, y = cy + p[1] * size; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    if (st.closed) ctx.closePath();
    ctx.stroke();
  }
  [[-1, -1], [1, -1], [1, 1], [-1, 1]].forEach(([dx, dy], i) => {
    if ((byte >> (3 - i)) & 1) {
      ctx.beginPath(); ctx.arc(cx + dx * SHAPES.dot_offset * cell, cy + dy * SHAPES.dot_offset * cell, SHAPES.dot_radius * cell, 0, 2 * Math.PI); ctx.fill();
    }
  });
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

// all 256 glyphs: row = icon (first hex digit), column = corner dots (second)
export function drawSheet(canvas, SHAPES, cell = 48) {
  const pitch = Math.round(cell * 1.2);
  canvas.width = pitch * 16 + cell / 2; canvas.height = pitch * 16 + cell / 2;
  const ctx = canvas.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  for (let b = 0; b < 256; b++) drawCell(ctx, SHAPES, b, cell * 0.75 + pitch * (b & 15), cell * 0.75 + pitch * (b >> 4), cell, Math.max(2, cell * 0.04));
}

// draw what the detector found on top of the (downscaled) photo already painted on the canvas
export function drawDetection(ctx, det) {
  ctx.lineWidth = 2; ctx.font = '14px sans-serif';
  det.frames.forEach((f, i) => {
    ctx.strokeStyle = '#00c853'; ctx.beginPath();
    f.hull.forEach((p, k) => k ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); ctx.stroke();
    ctx.fillStyle = '#ff1744'; ctx.fillText(String(i), f.center[0] - 4, f.center[1] + 5);
  });
  if (det.baseline) {
    const [a, b] = det.baseline; ctx.strokeStyle = '#d500f9'; ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
    ctx.beginPath(); ctx.arc(a[0], a[1], 8, 0, 2 * Math.PI); ctx.lineWidth = det.startKnown ? 3 : 1; ctx.stroke();
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2; ctx.strokeStyle = '#ffea00'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(mx, my); ctx.lineTo(mx + det.up[0] * 40, my + det.up[1] * 40); ctx.stroke();
  }
}
