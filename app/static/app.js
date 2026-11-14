/* LabVis – Oberfläche. Kein Build-Schritt, reines JS + SVG. */
'use strict';
const PAL = {BG: '#0b0f15', PANEL: '#111821', CHIP: '#19222e', BORDER: '#253042', TEXT: '#e6edf3', MUTED: '#8d9aab',
  FAINT: '#5d6a7c', TRUNK: '#d5dde6', TRUNKB: '#3a475a', LINK: '#79c0ff', OK: '#3fb950', BAD: '#f85149'};
const SPEED_W = {'100M': 1.4, '1G': 2.4, '2.5G': 3.8, '5G': 5.5, '10G': 8, '25G': 10, '40G': 12};
const TYPES = {internet: 'Internet', router: 'Router', firewall: 'Firewall', switch: 'Switch', ap: 'Access Point',
  hypervisor: 'Hypervisor', server: 'Server', nas: 'NAS', workstation: 'Workstation', client: 'Client', iot: 'IoT',
  printer: 'Drucker', vm: 'VM', container: 'Container', app: 'App', service: 'Dienst', other: 'Gerät'};
const API_COL = '#d2a8ff';
const KINDS = [['cable', 'Kabel'], ['wlan', 'WLAN (Funk)'], ['api', 'API / Datenabfrage'], ['logical', 'logisch (VPN, Cloud)']];
const BANDS = ['2,4 GHz', '5 GHz', '6 GHz', '2,4 + 5 GHz', '2,4 + 5 + 6 GHz'], SECS = ['WPA2', 'WPA2/WPA3', 'WPA3', 'WPA-Enterprise', 'offen'];
const TAB = 30, PAD = 16, GAP = 10;

let S = null, view = 'topo', sel = null, panelMode = null, vfilter = null, busy = false;
let multi = new Set(), selMode = false;
let cards = new Map(), cam = {x: 40, y: 60, k: 0.6}, camSet = false;

const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const main = $('#main'), panel = $('#panel');

async function api(method, url, body, raw) {
  const r = await fetch(url, {method, headers: body && !raw ? {'Content-Type': 'application/json'} : {},
    body: body ? (raw ? body : JSON.stringify(body)) : undefined});
  if (r.status === 401) { location.href = '/login'; throw new Error('Nicht angemeldet'); }
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (e) { /* kein JSON */ }
    throw new Error(msg);
  }
  return r.json();
}
function toast(msg, err) {
  const t = $('#toast');
  t.textContent = msg; t.className = err ? 'err' : ''; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, err ? 6000 : 2600);
}
async function run(fn, okMsg) {
  try { await fn(); if (okMsg) toast(okMsg); await load(); } catch (e) { toast(e.message, true); }
}

// ------------------------------------------------------------ Daten-Helfer
const dev = id => S.devices.find(d => d.id === id);
const kidsOf = id => S.devices.filter(d => d.parent_id === id);
const vlan = id => S.vlans.find(v => v.id === id);
const vcol = id => (vlan(id) || {}).color || PAL.TRUNKB;
const icon = d => '/api/icon/' + encodeURIComponent(d.icon || 'type-' + (d.type || 'other'));
const addrsOf = d => (d.meta && d.meta.addrs) || [];
const inVlan = (d, vid) => d.vlan_id === vid || addrsOf(d).some(a => a.vlan_id === vid);
const wlan = id => S.wlans.find(w => w.id === id);
const ssidsOf = id => S.wlans.filter(w => (w.aps || []).includes(id));
const vtag = v => v ? (v.vid != null ? 'VLAN ' + v.vid : v.name) : '';
function topOf(id) { let d = dev(id), n = 0; while (d && d.parent_id && n++ < 8) d = dev(d.parent_id) || d; return d ? d.id : null; }
function ago(t) {
  if (!t) return 'nie';
  const s = S.now - t;
  if (s < 90) return 'gerade eben';
  if (s < 5400) return Math.round(s / 60) + ' min';
  if (s < 129600) return Math.round(s / 3600) + ' h';
  return Math.round(s / 86400) + ' Tage';
}
const ip2int = ip => ip.split('.').reduce((a, o) => a * 256 + (+o), 0);
const int2ip = n => [n >>> 24, (n >>> 16) & 255, (n >>> 8) & 255, n & 255].join('.');

// ------------------------------------------------------------ Laden / Ansichten
async function load(silent) {
  try {
    S = await api('GET', '/api/state');
  } catch (e) { if (!silent) toast(e.message, true); return; }
  $('#title').textContent = S.settings.title || 'LabVis';
  document.body.classList.toggle('ro', S.role === 'read');
  document.title = S.settings.title && S.settings.title !== 'LabVis' ? S.settings.title + ' · LabVis' : 'LabVis';
  $('#badge').textContent = S.discoveries.filter(d => d.state === 'pending').length || '';
  $('#scanstate').textContent = S.scanner.running ? `Scan ${S.scanner.running} · ${S.scanner.phase}` : '';
  for (const id of [...multi]) if (!dev(id)) multi.delete(id);
  bulkBar();
  if (busy) return;
  render();
  if (sel && panelMode === 'device' && dev(sel)) showDevice(sel, true);
}
function render() {
  main.className = view === 'topo' ? 'canvas' : '';
  ({topo: renderTopo, racks: renderRacks, nets: renderNets, finds: renderFinds, integ: renderInteg, system: renderSystem})[view]();
}
$('#tabs').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  view = b.dataset.view;
  document.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('on', x === b));
  closePanel(); render();
});

// ------------------------------------------------------------ Text messen
const _c = document.createElement('canvas').getContext('2d');
function tw(s, size, weight = 400, mono = false) {
  _c.font = `${weight} ${size}px ${mono ? '"Fira Code"' : '"Fira Sans"'}`;
  return _c.measureText(s || '').width;
}
function fit(s, max, size, weight, mono) {
  s = String(s || '');
  if (tw(s, size, weight, mono) <= max) return s;
  while (s.length > 1 && tw(s + '…', size, weight, mono) > max) s = s.slice(0, -1);
  return s + '…';
}
function T(x, y, s, o = {}) {
  return `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" font-size="${o.size || 13}" fill="${o.fill || PAL.TEXT}" ` +
    `font-weight="${o.weight || 400}" text-anchor="${o.anchor || 'start'}"${o.mono ? ' class="m"' : ''}>${esc(s)}</text>`;
}
const IMG = (name, x, y, s) => `<image href="/api/icon/${encodeURIComponent(name)}" x="${x}" y="${y}" width="${s}" height="${s}"/>`;
const statusDot = (d, x, y, r = 4.5) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${d.status === 'online' ? PAL.OK : d.status === 'offline' ? PAL.BAD : PAL.FAINT}"/>`;

// ------------------------------------------------------------ Topologie: Karten
function chipH(c) {
  const g = kidsOf(c.id).length;
  return (c.ip || c.hostname ? 60 : 46) + (g ? g * 19 + 8 : 0);
}
function chipSvg(c, x, y, w, parentVlan) {
  const h = chipH(c), col = vcol(c.vlan_id), gk = kidsOf(c.id);
  const stroke = c.vlan_id && c.vlan_id !== parentVlan ? col : PAL.BORDER;
  const off = (vfilter && !inVlan(c, vfilter) ? ' off' : '') + (multi.has(c.id) ? ' msel' : '');
  const tag = c.meta && c.meta.vmid ? (c.type === 'vm' ? 'VM ' : 'CT ') + c.meta.vmid : '';
  const tagW = tag ? tw(tag, 10.5, 400, true) + 8 : 0;
  let s = `<g class="chip${off}" data-id="${c.id}" transform="translate(${x.toFixed(1)},${y.toFixed(1)})">` +
    `<rect class="cb" width="${w.toFixed(1)}" height="${h}" rx="8" fill="${PAL.CHIP}" stroke="${stroke}" stroke-width="1.2"/>` +
    IMG(c.icon || 'type-' + c.type, 10, 11, 22) +
    T(40, 21, fit(c.name, w - 62 - tagW, 13.5, 600), {size: 13.5, weight: 600}) +
    (tag ? T(w - 22, 20, tag, {size: 10.5, fill: PAL.FAINT, mono: true, anchor: 'end'}) : '') +
    statusDot(c, w - 11, 16, 3.6) +
    T(40, 36, fit(c.note || c.os || TYPES[c.type] || '', w - 50, 11, 400), {size: 11, fill: PAL.MUTED});
  if (c.ip || c.hostname) {
    const a = c.url && c.hostname ? c.hostname : [c.ip, addrsOf(c).length ? '+' + addrsOf(c).length : '', c.hostname].filter(Boolean).join(' · ');
    s += T(40, 51, fit(a, w - 50, 11, 400, true), {size: 11, mono: true, fill: c.url && c.hostname ? PAL.LINK : col});
  }
  gk.forEach((g, i) => {
    const gy = (c.ip || c.hostname ? 62 : 48) + i * 19;
    const right = g.hostname || g.note || '';
    const nameW = Math.min(tw(g.name, 12, 500), w * 0.5);
    s += IMG(g.icon || 'type-' + g.type, 13, gy, 14) + T(34, gy + 11, fit(g.name, w * 0.5, 12, 500), {size: 12, weight: 500}) +
      T(w - 10, gy + 11, fit(right, w - 54 - nameW, 10.5, 400, true), {size: 10.5, mono: true, anchor: 'end',
        fill: g.url ? PAL.LINK : PAL.MUTED});
  });
  return s + '</g>';
}
function folder(w, h, tabW, stroke) {
  const r = 10, t = TAB, s = 14;
  return `<path class="frame" d="M${r},0 H${tabW - s - 4} q6,0 9,5 l${s - 5},${t - 10} q3,5 9,5 H${w - r} a${r},${r} 0 0 1 ${r},${r} ` +
    `V${h - r} a${r},${r} 0 0 1 -${r},${r} H${r} a${r},${r} 0 0 1 -${r},-${r} V${r} a${r},${r} 0 0 1 ${r},-${r} z" ` +
    `fill="${PAL.PANEL}" stroke="${stroke}" stroke-width="1.6"/>`;
}
function buildCard(d) {
  const kids = kidsOf(d.id), hw = (d.meta && d.meta.hw) || [];
  const trunk = S.links.some(l => l.trunk && (l.a_id === d.id || l.b_id === d.id));
  const col = vcol(d.vlan_id), stroke = trunk || !d.vlan_id ? PAL.TRUNKB : col;
  const type = TYPES[d.type] || d.type;
  const tabW = Math.round(tw(d.name, 19, 700) + tw('\u00a0·\u00a0' + type, 13, 500) + 44);
  const extra = addrsOf(d).length;
  const addr = [d.ip, extra ? `+${extra} ${extra > 1 ? 'Adressen' : 'Adresse'}` : '', d.hostname].filter(Boolean).join(' · ');
  const l1 = d.model || d.note || '', l3 = d.os || (d.model ? d.note : '') || '';
  const headW = Math.max(70 + Math.max(tw(l1, 14, 500), tw(addr, 12.5, 400, true), tw(l3, 12)) + 40,
    ssidsOf(d.id).reduce((a, w) => a + tw(w.ssid, 11.5, 500, true) + 40, 0) + 2 * PAD);
  // Blöcke: Gruppen (falls vorhanden) bleiben zusammen, sonst jeder Chip einzeln
  const blocks = [];
  const grouped = kids.some(k => k.meta && k.meta.group);
  for (const k of kids) {
    const g = grouped ? ((k.meta && k.meta.group) || 'Weitere') : null;
    let b = g && blocks.find(x => x.title === g);
    if (!b) { b = {title: g, chips: []}; blocks.push(b); }
    b.chips.push(k);
  }
  const n = kids.length;
  let cols = n <= 1 ? 1 : n <= 4 ? 2 : n <= 10 ? 3 : n <= 24 ? 4 : 5;
  if (!n && hw.length) cols = Math.min(hw.length, 2);
  let cw = 240;
  const has = n || hw.length;
  const w = Math.ceil(Math.max(tabW + 60, headW, has ? cols * cw + (cols - 1) * GAP + 2 * PAD : 0));
  cw = (w - 2 * PAD - (cols - 1) * GAP) / cols;
  let s = T(16, 21, d.name, {size: 19, weight: 700}) + T(16 + tw(d.name, 19, 700), 21, '\u00a0·\u00a0' + type, {size: 13, weight: 500, fill: PAL.MUTED});
  s += IMG(d.icon || 'type-' + d.type, 18, TAB + 15, 38) + statusDot(d, w - 18, TAB + 20);
  s += T(70, TAB + 29, l1, {size: 14, weight: 500}) + T(70, TAB + 47, addr, {size: 12.5, mono: true, fill: d.vlan_id ? col : PAL.MUTED}) +
    T(70, TAB + 63, l3, {size: 12, fill: PAL.MUTED});
  let y = TAB + 80;
  const ssids = ssidsOf(d.id);
  if (ssids.length) {
    let px = PAD;
    for (const w of ssids) {
      const c = w.vlan_id ? vcol(w.vlan_id) : PAL.MUTED, pw = tw(w.ssid, 11.5, 500, true) + 34;
      s += `<rect x="${px}" y="${y - 2}" width="${pw.toFixed(1)}" height="22" rx="11" fill="${PAL.CHIP}" stroke="${c}" stroke-width="1.2"/>` +
        `<path d="M${px + 9},${y + 8} a7,7 0 0 1 10,0 M${px + 11.500},${y + 11} a3.500,3.500 0 0 1 5,0" fill="none" stroke="${c}" stroke-width="1.5" stroke-linecap="round"/><circle cx="${px + 14}" cy="${y + 14}" r="1.3" fill="${c}"/>` +
        T(px + 25, y + 13, w.ssid, {size: 11.5, weight: 500, mono: true, fill: c});
      px += pw + 6;
    }
    y += 30;
  }
  if (hw.length) {
    hw.forEach((t, i) => {
      const tx = PAD + (i % cols) * (cw + GAP), ty = y + Math.floor(i / cols) * 52;
      s += `<rect x="${tx}" y="${ty}" width="${cw}" height="44" rx="7" fill="${PAL.CHIP}" stroke="${PAL.BORDER}"/>` +
        `<rect x="${tx}" y="${ty}" width="4" height="44" rx="2" fill="#b08d57"/>` + IMG(t.icon || 'glyph-cpu', tx + 12, ty + 11, 22) +
        T(tx + 42, ty + 13, t.label || '', {size: 9, weight: 600, fill: '#b08d57', mono: true}) +
        T(tx + 42, ty + 26, fit(t.value, cw - 50, 12.5, 600), {size: 12.5, weight: 600}) +
        T(tx + 42, ty + 38, fit(t.sub, cw - 50, 10), {size: 10, fill: PAL.MUTED});
    });
    y += Math.ceil(hw.length / cols) * 52 + 4;
  }
  const colY = Array(cols).fill(y);
  for (const b of blocks) {
    const ci = colY.indexOf(Math.min(...colY)), bx = PAD + ci * (cw + GAP);
    if (b.title) { s += T(bx + 2, colY[ci] + 13, b.title.toUpperCase(), {size: 10.5, weight: 600, fill: '#b08d57'}); colY[ci] += 21; }
    for (const c of b.chips) { s += chipSvg(c, bx, colY[ci], cw, d.vlan_id); colY[ci] += chipH(c) + 8; }
    if (b.title) colY[ci] += 6;
  }
  const h = Math.ceil(has ? Math.max(...colY, y) + PAD - 8 : TAB + 78 + (ssids.length ? 32 : 0));
  s = folder(w, h, tabW, stroke) + s;
  return {id: d.id, d, w, h, tabW, x: d.x, y: d.y, svg: s};
}

// ------------------------------------------------------------ Topologie: Kabel
function rounded(p, r) {
  let d = `M${p[0][0].toFixed(1)},${p[0][1].toFixed(1)}`;
  for (let i = 1; i < p.length - 1; i++) {
    const [x0, y0] = p[i - 1], [x1, y1] = p[i], [x2, y2] = p[i + 1];
    const l1 = Math.hypot(x1 - x0, y1 - y0), l2 = Math.hypot(x2 - x1, y2 - y1), rr = Math.min(r, l1 / 2, l2 / 2);
    if (rr < 0.5) { d += ` L${x1.toFixed(1)},${y1.toFixed(1)}`; continue; }
    const ax = x1 - (x1 - x0) / l1 * rr, ay = y1 - (y1 - y0) / l1 * rr, bx = x1 + (x2 - x1) / l2 * rr, by = y1 + (y2 - y1) / l2 * rr;
    d += ` L${ax.toFixed(1)},${ay.toFixed(1)} Q${x1.toFixed(1)},${y1.toFixed(1)} ${bx.toFixed(1)},${by.toFixed(1)}`;
  }
  const e = p[p.length - 1];
  return d + ` L${e[0].toFixed(1)},${e[1].toFixed(1)}`;
}
const wcol = l => { const w = wlan(l.wlan_id); return w && w.vlan_id ? vcol(w.vlan_id) : l.vlan_id ? vcol(l.vlan_id) : PAL.LINK; };
function linksSvg() {
  const segs = [], ends = new Map();
  const push = (c, side, e) => { const k = c.id + side; if (!ends.has(k)) ends.set(k, {c, side, list: []}); ends.get(k).list.push(e); };
  for (const l of S.links) {
    const A = cards.get(topOf(l.a_id)), B = cards.get(topOf(l.b_id));
    if (!A || !B || A === B) continue;
    let sa, sb;
    if (A.y + A.h <= B.y - 16) { sa = 'b'; sb = 't'; } else if (B.y + B.h <= A.y - 16) { sa = 't'; sb = 'b'; }
    else if (A.x + A.w <= B.x) { sa = 'r'; sb = 'l'; } else { sa = 'l'; sb = 'r'; }
    const seg = {l, A, B, sa, sb};
    segs.push(seg); push(A, sa, {seg, o: B, k: 'pa'}); push(B, sb, {seg, o: A, k: 'pb'});
  }
  for (const {c, side, list} of ends.values()) {
    const vert = side === 't' || side === 'b';
    list.sort((p, q) => vert ? (p.o.x + p.o.w / 2) - (q.o.x + q.o.w / 2) : (p.o.y + p.o.h / 2) - (q.o.y + q.o.h / 2));
    list.forEach((e, i) => {
      const f = (i + 1) / (list.length + 1);
      let lo, hi;
      if (side === 't') { lo = c.x + Math.min(c.tabW + 22, c.w - 44); hi = c.x + c.w - 16; e.seg[e.k] = [lo + f * (hi - lo), c.y + TAB]; }
      else if (side === 'b') { lo = c.x + 16; hi = c.x + c.w - 16; e.seg[e.k] = [lo + f * (hi - lo), c.y + c.h]; }
      else { lo = c.y + TAB + 12; hi = c.y + c.h - 12; e.seg[e.k] = [side === 'l' ? c.x : c.x + c.w, lo + f * (hi - lo)]; }
      e.seg[e.k + 'i'] = i - (list.length - 1) / 2;
    });
  }
  let out = '';
  for (const {l, A, B, sa, pa, pb, pai, pbi} of segs) {
    let pts;
    if (sa === 'b' || sa === 't') { const my = (pa[1] + pb[1]) / 2 + pai * 9; pts = [pa, [pa[0], my], [pb[0], my], pb]; }
    else { const mx = (pa[0] + pb[0]) / 2 + pai * 9; pts = [pa, [mx, pa[1]], [mx, pb[1]], pb]; }
    const d = rounded(pts, 12), w = SPEED_W[l.speed] || 2.4, col = l.vlan_id ? vcol(l.vlan_id) : PAL.LINK;
    const off = vfilter && !l.trunk && l.vlan_id !== vfilter ? ' off' : '';
    let p;
    if (l.kind === 'api') p = `<path class="core" d="${d}" fill="none" stroke="${API_COL}" stroke-width="1.8" stroke-dasharray="7 5" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#arr)"/>`;
    else if (l.kind === 'wlan') p = `<path class="core" d="${d}" fill="none" stroke="${wcol(l)}" stroke-width="3.2" stroke-dasharray="0.1 8" stroke-linecap="round" stroke-linejoin="round"/>`;
    else if (l.kind === 'logical') p = `<path class="core" d="${d}" fill="none" stroke="${PAL.MUTED}" stroke-width="1.6" stroke-dasharray="2 6" stroke-linecap="round"/>`;
    else if (l.trunk) p = `<path d="${d}" fill="none" stroke="${PAL.TRUNK}" stroke-width="${w + 3.4}" stroke-linecap="round" stroke-linejoin="round"/>` +
      `<path class="core" d="${d}" fill="none" stroke="${PAL.BG}" stroke-width="${Math.max(w - 1, 1)}" stroke-linecap="round" stroke-linejoin="round"/>`;
    else p = `<path class="core" d="${d}" fill="none" stroke="${col}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
    const tagAt = (pt, side, txt, c, idx) => {
      const row = Math.abs(Math.round(idx * 2)) % 4 >= 2 ? 1 : 0;
      if (!txt) return '';
      const tx = pt[0] + (side === 'l' ? -8 : 8), ty = pt[1] + (side === 't' ? -9 - row * 15 : side === 'b' ? 17 + row * 15 : -7);
      const anchor = side === 'l' ? 'end' : 'start', wd = tw(txt, 10.5, 500, true) + 8;
      return `<rect x="${(anchor === 'end' ? tx - wd + 4 : tx - 4).toFixed(1)}" y="${(ty - 11).toFixed(1)}" width="${wd.toFixed(1)}" height="15" rx="4" fill="${PAL.BG}"/>` +
        T(tx, ty, txt, {size: 10.5, weight: 500, mono: true, fill: c, anchor});
    };
    const sb = {b: 't', t: 'b', r: 'l', l: 'r'}[sa];
    const api = l.kind === 'api', lcol = api ? API_COL : l.kind === 'wlan' ? wcol(l) : l.kind === 'logical' ? PAL.MUTED : l.trunk ? PAL.TRUNK : col;
    const btag = api ? ['API', l.note, l.b_port].filter(Boolean).join(' · ') : l.kind === 'wlan' ? ['WLAN', (wlan(l.wlan_id) || {}).ssid, l.note].filter(Boolean).join(' · ') : l.kind === 'logical' ? (l.note || '') : [l.speed, l.b_port].filter(Boolean).join(' · ');
    out += `<g class="link${off}" data-link="${l.id}" data-a="${A.id}" data-b="${B.id}">${p}<path class="hit" d="${d}"/>` +
      tagAt(pb, sb, btag, lcol, pbi) + tagAt(pa, sa, l.a_port || '', lcol, pai) + '</g>';
  }
  return out;
}

// ------------------------------------------------------------ Topologie: Layout + Rendern
function autoLayout(all) {
  const tiers = [[], [], [], [], [], []];
  let maxY = 0;
  for (const c of cards.values()) {
    if (!all && c.x != null) { maxY = Math.max(maxY, c.y + c.h); continue; }
    const t = {internet: 0, router: 1, firewall: 2, switch: 3}[c.d.type];
    tiers[t !== undefined ? t : (kidsOf(c.id).length ? 5 : 4)].push(c);
  }
  let y = all ? 70 : maxY + 110;
  const moved = [];
  for (const row of tiers) {
    const lines = [[]]; let cur = 0;
    for (const c of row) {
      if (cur + c.w > 2600 && lines[lines.length - 1].length) { lines.push([]); cur = 0; }
      lines[lines.length - 1].push(c); cur += c.w + 70;
    }
    for (const line of lines) {
      if (!line.length) continue;
      const total = line.reduce((a, c) => a + c.w, 0) + 70 * (line.length - 1);
      let x = 1300 - total / 2;
      for (const c of line) { c.x = Math.round(x); c.y = y; x += c.w + 70; moved.push({id: c.id, x: c.x, y: c.y}); }
      y += Math.max(...line.map(c => c.h)) + 110;
    }
  }
  for (const m of moved) { const d = dev(m.id); d.x = m.x; d.y = m.y; }
  if (moved.length && !ro()) api('POST', '/api/positions/save', moved).catch(e => toast(e.message, true));
}
function fitView() {
  const cs = [...cards.values()];
  if (!cs.length) return;
  const x0 = Math.min(...cs.map(c => c.x)), y0 = Math.min(...cs.map(c => c.y));
  const x1 = Math.max(...cs.map(c => c.x + c.w)), y1 = Math.max(...cs.map(c => c.y + c.h));
  const W = main.clientWidth, H = main.clientHeight;
  cam.k = Math.min((W - 40) / (x1 - x0), (H - 110) / (y1 - y0), 1.4);
  cam.x = (W - (x1 - x0) * cam.k) / 2 - x0 * cam.k; cam.y = 64 - y0 * cam.k;
  applyCam();
}
function applyCam() { const w = $('#world'); if (w) w.setAttribute('transform', `translate(${cam.x.toFixed(1)},${cam.y.toFixed(1)}) scale(${cam.k.toFixed(4)})`); }
function toggleMulti(id) {
  multi.has(id) ? multi.delete(id) : multi.add(id);
  document.querySelectorAll(`.card[data-id="${id}"], .chip[data-id="${id}"]`).forEach(n => n.classList.toggle('msel', multi.has(id)));
  document.querySelectorAll(`input[data-act="rowSel"][data-id="${id}"]`).forEach(n => { n.checked = multi.has(id); });
  bulkBar();
}
function bulkBar() {
  let b = $('#bulk');
  if (!multi.size || ro()) { if (b) b.remove(); return; }
  if (!b) { b = document.createElement('div'); b.id = 'bulk'; document.body.appendChild(b); }
  b.innerHTML = `<b>${multi.size} ausgewählt</b><button class="btn sm pri" data-act="bulkEdit">Ändern</button>` +
    (multi.size > 1 ? '<button class="btn sm" data-act="bulkMerge">Zusammenführen</button>' : '') +
    '<button class="btn sm bad" data-act="bulkDel">Löschen</button><button class="btn sm" data-act="bulkClear">Aufheben</button>';
}
function cardNode(c) {
  const off = vfilter && !inVlan(c.d, vfilter) && !S.devices.some(k => topOf(k.id) === c.id && inVlan(k, vfilter)) ? ' off' : '';
  return `<g class="card${off}${sel === c.id ? ' sel' : ''}${multi.has(c.id) ? ' msel' : ''}" data-id="${c.id}" transform="translate(${c.x},${c.y})">${c.svg}</g>`;
}
function renderTopo() {
  const tops = S.devices.filter(d => !d.parent_id);
  if (!tops.length) {
    main.className = '';
    main.innerHTML = `<div class="page"><div class="hint"><b>Noch keine Geräte.</b><br>Lege unter <b>Netzwerke</b> ein Netz an und starte einen Scan, ` +
      `füge Geräte von Hand hinzu oder importiere unter <b>System</b> eine <span class="mono">inventory.yaml</span> ` +
      `(Format von homelab-diagram).<div class="acts"><button class="btn pri" data-act="newDevice">+ Gerät</button></div></div></div>`;
    return;
  }
  cards = new Map(tops.map(d => [d.id, buildCard(d)]));
  if ([...cards.values()].some(c => c.x == null)) autoLayout([...cards.values()].every(c => c.x == null));
  main.innerHTML = `<svg id="svg"><defs><marker id="arr" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="${API_COL}"/></marker></defs><g id="world" class="world"><g id="links">${linksSvg()}</g>` +
    `<g id="cards">${[...cards.values()].map(cardNode).join('')}</g></g></svg>` +
    `<div id="vbar">${S.vlans.map(v => `<button class="vp${vfilter === v.id ? ' on' : ''}" style="border-left-color:${esc(v.color)}" data-act="vfilter" data-id="${v.id}">${esc(vtag(v))}${v.vid != null ? ' · ' + esc(v.name) : ''}</button>`).join('')}</div>` +
    `<div id="legend"><i style="height:8px"></i><span>10G</span><i style="height:3.8px"></i><span>2.5G</span><i style="height:2.4px"></i><span>1G</span>` +
    `<i class="tr"></i><span>Trunk (tagged)</span><i class="wl"></i><span>WLAN</span><i class="ap"></i><span>API (Pfeil = fragt ab)</span><i class="lg"></i><span>logisch</span></div>` +
    `<div id="tsearch">${searchBox('topoq', '', 'Gerät suchen …')}<div id="tres" hidden></div></div>` +
    `<div id="tools"><button class="btn" data-act="newDevice">+ Gerät</button><button class="btn${selMode ? ' pri' : ''}" data-act="selMode" title="Auch: Strg/Umschalt + Klick">${selMode ? 'Auswahl beenden' : 'Auswählen'}</button><button class="btn" data-act="relayout">Auto-Layout</button>` +
    `<button class="btn" data-act="fit">Einpassen</button><button class="btn" data-act="svgExport">SVG</button></div>`;
  if (!camSet) { fitView(); camSet = true; } else applyCam();
  bindCanvas();
  focusSel();
  $('#topoq').addEventListener('input', e => {
    const q = e.target.value, box = $('#tres');
    const hits = q.trim() ? S.devices.filter(d => match(q, d.name, d.ip, d.hostname, d.mac, d.vendor, d.model, d.note, TYPES[d.type], addrsOf(d).map(a => a.ip).join(' '))).slice(0, 10) : [];
    box.hidden = !q.trim();
    box.innerHTML = hits.map(d => `<button data-act="jump" data-id="${d.id}"><img src="${icon(d)}" width="18" height="18" alt=""><b>${esc(d.name)}</b><span class="mono">${esc(d.ip || '')}</span></button>`).join('') ||
      '<span class="muted" style="padding:8px 10px;display:block">Keine Treffer</span>';
  });
}
function focusSel() {
  const w = $('#world'); if (!w) return;
  const t = sel ? topOf(sel) : null;
  w.classList.toggle('focus', !!t && cards.has(t));
  w.querySelectorAll('.hl').forEach(n => n.classList.remove('hl'));
  if (!t) return;
  w.querySelectorAll('.link').forEach(n => {
    if (+n.dataset.a === t || +n.dataset.b === t) {
      n.classList.add('hl');
      const o = w.querySelector(`.card[data-id="${+n.dataset.a === t ? n.dataset.b : n.dataset.a}"]`); if (o) o.classList.add('hl');
    }
  });
  const me = w.querySelector(`.card[data-id="${t}"]`); if (me) me.classList.add('hl');
}
function bindCanvas() {
  const svg = $('#svg'), pts = new Map();
  let mode = null, start = null, card = null, moved = false, pinch = null;
  svg.addEventListener('wheel', e => {
    e.preventDefault();
    const r = svg.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    const k = Math.min(3, Math.max(0.08, cam.k * Math.exp(-e.deltaY * 0.0015)));
    cam.x = mx - (mx - cam.x) * k / cam.k; cam.y = my - (my - cam.y) * k / cam.k; cam.k = k; applyCam();
  }, {passive: false});
  svg.addEventListener('pointerdown', e => {
    pts.set(e.pointerId, [e.clientX, e.clientY]);
    svg.setPointerCapture(e.pointerId);
    if (pts.size === 2) {
      const [a, b] = [...pts.values()];
      pinch = {d: Math.hypot(a[0] - b[0], a[1] - b[1]), k: cam.k, cx: (a[0] + b[0]) / 2, cy: (a[1] + b[1]) / 2, x: cam.x, y: cam.y};
      mode = 'pinch'; return;
    }
    const cn = e.target.closest('.card');
    moved = false; start = [e.clientX, e.clientY];
    if (cn) { card = cards.get(+cn.dataset.id); mode = 'card'; start.push(card.x, card.y); card.node = cn; card.hit = e.target; }
    else { mode = 'pan'; start.push(cam.x, cam.y); card = null; }
    start.target = e.target;
  });
  svg.addEventListener('pointermove', e => {
    if (!pts.has(e.pointerId)) return;
    pts.set(e.pointerId, [e.clientX, e.clientY]);
    if (mode === 'pinch' && pts.size === 2) {
      const [a, b] = [...pts.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]);
      const r = svg.getBoundingClientRect(), cx = pinch.cx - r.left, cy = pinch.cy - r.top;
      const k = Math.min(3, Math.max(0.08, pinch.k * d / pinch.d));
      cam.x = cx - (cx - pinch.x) * k / pinch.k; cam.y = cy - (cy - pinch.y) * k / pinch.k; cam.k = k; applyCam(); return;
    }
    const dx = e.clientX - start[0], dy = e.clientY - start[1];
    if (!moved && Math.hypot(dx, dy) < 5) return;
    moved = true; busy = true;
    if (mode === 'pan') { cam.x = start[2] + dx; cam.y = start[3] + dy; applyCam(); }
    else if (mode === 'card') {
      card.x = Math.round(start[2] + dx / cam.k); card.y = Math.round(start[3] + dy / cam.k);
      card.node.setAttribute('transform', `translate(${card.x},${card.y})`);
      $('#links').innerHTML = linksSvg(); focusSel();
    }
  });
  const up = e => {
    if (!pts.has(e.pointerId)) return;
    pts.delete(e.pointerId);
    if (mode === 'pinch') { if (pts.size < 2) mode = null; return; }
    busy = false;
    if (mode === 'card' && moved) {
      const d = dev(card.id); d.x = card.x; d.y = card.y;
      if (!ro()) api('POST', '/api/positions/save', [{id: card.id, x: card.x, y: card.y}]).catch(er => toast(er.message, true));
    } else if (!moved) {
      const t = start.target, chip = t.closest('.chip'), cn = t.closest('.card'), ln = t.closest('.link');
      if ((selMode || e.ctrlKey || e.metaKey || e.shiftKey) && (chip || cn) && !ro()) toggleMulti(+(chip || cn).dataset.id);
      else if (chip) showDevice(+chip.dataset.id); else if (cn) showDevice(+cn.dataset.id);
      else if (ln) showLink(+ln.dataset.link); else closePanel();
    }
    mode = null;
  };
  svg.addEventListener('pointerup', up); svg.addEventListener('pointercancel', up);
}

// ------------------------------------------------------------ Panel
function closePanel() { panel.hidden = true; panelMode = null; sel = null; focusSel(); document.querySelectorAll('.card.sel').forEach(n => n.classList.remove('sel')); }
function openPanel(html, mode) { panel.innerHTML = html; panel.hidden = false; panelMode = mode; if (mode !== 'device') panel.scrollTop = 0; }
const closeBtn = '<button class="x" data-act="close" aria-label="Schließen">×</button>';
function fact(k, v) { return v ? `<dt>${k}</dt><dd>${v}</dd>` : ''; }

function showDevice(id, keep) {
  const d = dev(id); if (!d) return closePanel();
  sel = id;
  const v = vlan(d.vlan_id), m = d.meta || {}, kids = kidsOf(id), par = d.parent_id && dev(d.parent_id);
  const links = S.links.filter(l => l.a_id === id || l.b_id === id);
  const rack = S.racks.find(r => r.id === d.rack_id);
  const integ = S.integrations.filter(i => i.device_id === id);
  let h = `<div class="phead"><img src="${icon(d)}" alt=""><div><h2>${esc(d.name)}</h2><span class="muted">${esc(TYPES[d.type] || d.type)}` +
    `${par ? ' · in <a href="#" data-act="show" data-id="' + par.id + '">' + esc(par.name) + '</a>' : ''}</span></div>${closeBtn}</div>` +
    `<div class="rowl" style="border:0"><span class="dot ${d.status}"></span>${d.status === 'online' ? 'online' : d.status === 'offline' ? 'offline' : 'Status unbekannt'}` +
    `<span class="muted">· zuletzt gesehen: ${ago(d.last_seen)}</span></div>` +
    `<div class="acts">${d.url ? `<a class="btn pri" href="${esc(d.url)}" target="_blank" rel="noopener">Öffnen ↗</a>` : ''}` +
    `<button class="btn" data-act="editDevice" data-id="${id}">Bearbeiten</button><button class="btn" data-act="newLink" data-id="${id}">Verbinden</button><button class="btn" data-act="newLink" data-id="${id}" data-kind="wlan">WLAN-Verbindung</button><button class="btn" data-act="newLink" data-id="${id}" data-kind="api">API-Verbindung</button>` +
    `<button class="btn" data-act="addAddr" data-id="${id}">+ Adresse</button><button class="btn" data-act="merge" data-id="${id}">Zusammenführen</button>` +
    `<button class="btn" data-act="newDevice" data-parent="${id}">+ Kind</button><button class="btn bad" data-act="delDevice" data-id="${id}">Löschen</button></div>` +
    `<dl class="facts">${fact('IP', d.ip && `<span class="mono">${esc(d.ip)}</span>`)}${fact('Hostname', d.hostname && `<span class="mono">${esc(d.hostname)}</span>`)}` +
    fact('MAC', d.mac && `<span class="mono">${esc(d.mac)}</span>${d.vendor ? ' · ' + esc(d.vendor) : ''}`) +
    fact('Netzwerk', v && `<span style="color:${esc(v.color)}">${esc(v.vid != null ? vtag(v) + ' · ' + v.name : v.name)}</span>`) +
    fact('Modell', esc(d.model)) + fact('System', esc(d.os)) + fact('Notiz', esc(d.note)) +
    fact('Rack', rack && `${esc(rack.name)} · HE ${d.rack_u}${d.rack_height > 1 ? '–' + (d.rack_u + d.rack_height - 1) : ''}`) +
    fact('Offene Ports', (d.ports || []).length ? d.ports.map(p => `<span class="pill">${p}</span>`).join(' ') : '') +
    fact('Quelle', esc({manual: 'manuell', scan: 'Scan', import: 'Import'}[d.source] || d.source)) + '</dl>';
  if (addrsOf(d).length) h += `<h3>Weitere Adressen (${addrsOf(d).length})</h3>` + addrsOf(d).map((a, n) => { const av = vlan(a.vlan_id);
    return `<div class="rowl" style="flex-wrap:wrap"><span class="dot ${a.up === true ? 'online' : a.up === false ? 'offline' : ''}"></span><span class="mono">${esc(a.ip || '–')}</span>` +
      `${a.label ? `<b>${esc(a.label)}</b>` : ''}${av ? `<span style="color:${esc(av.color)};font-size:12px">${esc(av.vid != null ? vtag(av) : av.name)}</span>` : ''}` +
      `<button class="btn sm" style="margin-left:auto" data-act="delAddr" data-id="${id}" data-idx="${n}" aria-label="Adresse entfernen">✕</button>` +
      `${a.mac ? `<span class="mono faint" style="flex-basis:100%;font-size:11.5px;padding-left:17px">${esc(a.mac)}${a.vendor ? ' · ' + esc(a.vendor) : ''}</span>` : ''}</div>`; }).join('');
  if (ssidsOf(id).length) h += `<h3>WLANs (${ssidsOf(id).length})</h3>` + ssidsOf(id).map(w => { const wv = vlan(w.vlan_id);
    return `<div class="rowl"><b class="mono">${esc(w.ssid)}</b>${wv ? `<span style="color:${esc(wv.color)};font-size:12px">${esc(wv.vid != null ? vtag(wv) + ' · ' + wv.name : wv.name)}</span>` : ''}` +
      `<span class="muted" style="margin-left:auto;font-size:12px">${esc([w.band, w.security].filter(Boolean).join(' · '))}</span><button class="btn sm" data-act="editWlan" data-id="${w.id}">✎</button></div>`; }).join('');
  if ((m.hw || []).length) h += '<h3>Hardware</h3>' + m.hw.map(t => `<div class="tile"><img src="/api/icon/${esc(t.icon || 'glyph-cpu')}" alt=""><div>` +
    `<span class="lab">${esc(t.label)}</span><br><b>${esc(t.value)}</b><small>${esc(t.sub)}</small></div></div>`).join('');
  if ((m.pools || []).length) h += '<h3>Storage</h3>' + m.pools.map(p => `<div class="box" style="margin-bottom:6px"><b>${esc(p.name)}</b> <span class="muted">${esc(p.layout)}</span>` +
    `<div class="bar2"><i style="width:${+p.pct || 0}%"></i></div><small class="muted">${esc(p.used)}</small></div>`).join('');
  if ((m.ifaces || []).length) {
    const vbyvid = x => S.vlans.find(vv => String(vv.vid) === String(x));
    h += `<h3>Ports (${m.ifaces.filter(i => i.up).length}/${m.ifaces.length} aktiv)</h3><div class="ports">` +
      m.ifaces.map((i, n) => { const pv = vbyvid(i.pvid); return `<div class="${i.up ? 'up' : ''}${i.neighbor ? ' nb' : ''}" style="${pv ? 'border-color:' + esc(pv.color) : ''}" ` +
        `title="${esc(i.name)}${i.alias ? ' · ' + esc(i.alias) : ''}${i.pvid ? ' · PVID ' + esc(i.pvid) : ''}${i.up ? ' · ' + esc(i.speed) : ''}${i.neighbor ? ' → ' + esc(i.neighbor) : ''}">${n + 1}</div>`; }).join('') + '</div>';
    const nb = m.ifaces.filter(i => i.neighbor && i.neighbor !== 'free');
    if (nb.length) h += '<div style="margin-top:8px">' + nb.map(i => `<div class="rowl"><span class="mono">${esc(i.name)}</span><span class="muted">→</span>${esc(i.neighbor)}` +
      `<span class="pill" style="margin-left:auto">${esc(i.speed)}</span></div>`).join('') + '</div>';
  }
  const sug = (m.suggestions || []);
  if (sug.length) h += '<h3>Schnittstellen-Vorschläge</h3>' + sug.map((s, n) => {
    const have = integ.some(i => i.kind === s.connector);
    return `<div class="sug"><b>${esc(s.title)}</b><small>${esc(s.reason)} · liest: ${esc(s.reads)}</small>` +
      (s.connector ? (have ? '<span class="pill" style="color:var(--ok)">eingerichtet</span>' :
        `<button class="btn sm pri" data-act="newInteg" data-kind="${esc(s.connector)}" data-dev="${id}" data-sug="${n}">Einrichten</button>`) :
        '<span class="pill">Hinweis · noch kein Connector</span>') + '</div>';
  }).join('');
  if (integ.length) h += '<h3>Anbindungen</h3>' + integ.map(i => `<div class="rowl"><b>${esc(S.kinds[i.kind].label)}</b><span class="muted">${esc(i.last_status || 'noch nicht synchronisiert')}</span>` +
    `<button class="btn sm" style="margin-left:auto" data-act="sync" data-id="${i.id}">Sync</button></div>`).join('');
  if (links.length) h += '<h3>Verbindungen</h3>' + links.map(l => {
    const o = dev(l.a_id === id ? l.b_id : l.a_id), mp = l.a_id === id ? l.a_port : l.b_port, op = l.a_id === id ? l.b_port : l.a_port;
    return `<div class="rowl">${mp ? `<span class="mono">${esc(mp)}</span><span class="muted">→</span>` : ''}<a href="#" data-act="show" data-id="${o ? o.id : 0}">${esc(o ? o.name : '?')}</a>` +
      `${op ? `<span class="mono muted">${esc(op)}</span>` : ''}<span class="pill" style="margin-left:auto${l.kind === 'api' ? ';color:' + API_COL : ''}">${l.kind === 'api' ? (l.a_id === id ? 'API →' : '← API') + (l.note ? ' · ' + esc(l.note) : '') : l.kind === 'wlan' ? 'WLAN' + (wlan(l.wlan_id) ? ' · ' + esc(wlan(l.wlan_id).ssid) : '') : l.kind === 'logical' ? 'logisch' : esc(l.speed) + (l.trunk ? ' · Trunk' : '')}</span>` +
      `<button class="btn sm" data-act="editLink" data-id="${l.id}">✎</button></div>`;
  }).join('');
  if (kids.length) h += `<h3>Enthält (${kids.length})</h3>` + kids.map(k => `<div class="rowl"><span class="dot ${k.status}"></span><a href="#" data-act="show" data-id="${k.id}">${esc(k.name)}</a>` +
    `<span class="muted mono" style="margin-left:auto">${esc(k.ip || '')}</span></div>`).join('');
  const st = keep ? panel.scrollTop : 0;
  openPanel(h, 'device'); panel.scrollTop = st;
  document.querySelectorAll('.card').forEach(n => n.classList.toggle('sel', +n.dataset.id === id));
  focusSel();
}

// generisches Formular: fields = [[key,label,type,options]]
function formHtml(title, fields, val, extra = '') {
  const inp = ([k, label, type, opts]) => {
    const v = val[k] ?? '';
    if (type === 'select') return `<label>${label}<select name="${k}">${opts.map(([ov, ol]) => `<option value="${esc(ov)}"${String(ov) === String(v) ? ' selected' : ''}>${esc(ol)}</option>`).join('')}</select></label>`;
    if (type === 'multi') return `<label>${label}<select name="${k}" multiple size="${Math.min(6, Math.max(3, opts.length))}">${opts.map(([ov, ol]) => `<option value="${esc(ov)}"${(v || []).map(String).includes(String(ov)) ? ' selected' : ''}>${esc(ol)}</option>`).join('')}</select></label>`;
    if (type === 'check') return `<label class="chk"><input type="checkbox" name="${k}"${+v ? ' checked' : ''}>${label}</label>`;
    if (type === 'area') return `<label>${label}<textarea name="${k}" rows="2">${esc(v)}</textarea></label>`;
    return `<label>${label}<input name="${k}" type="${type || 'text'}" value="${esc(v)}"${opts ? ` placeholder="${esc(opts)}"` : ''} autocomplete="off"></label>`;
  };
  return `<div class="phead"><h2>${title}</h2>${closeBtn}</div><form class="f">${fields.map(f => Array.isArray(f[0]) ? `<div class="two">${f.map(inp).join('')}</div>` : inp(f)).join('')}` +
    `<div class="acts"><button class="btn pri" type="submit">Speichern</button><button class="btn" type="button" data-act="cancel">Abbrechen</button>${extra}</div></form>`;
}
function openForm(title, fields, val, onSave, extra, keepSel) {
  if (ro()) return;
  if (!keepSel) sel = null;
  openPanel(formHtml(title, fields, val, extra), 'form');
  $('form', panel).addEventListener('submit', e => {
    e.preventDefault();
    const data = {};
    for (const el of e.target.elements) if (el.name) data[el.name] = el.multiple ? [...el.selectedOptions].map(o => +o.value) : el.type === 'checkbox' ? (el.checked ? 1 : 0) : el.value.trim();
    run(async () => { await onSave(data); if (sel) panelMode = 'device'; else closePanel(); }, 'Gespeichert');
  });
}
const vlanOpts = () => [['', '– keins –'], ...S.vlans.map(v => [v.id, v.vid != null ? `${vtag(v)} · ${v.name}` : v.name])];
const devOpts = (skip) => [['', '– keins –'], ...S.devices.filter(d => d.id !== skip && !['app', 'service'].includes(d.type)).map(d => [d.id, d.name])];
function deviceForm(d) {
  const isNew = !d.id;
  openForm(isNew ? 'Neues Gerät' : esc(d.name), [
    ['name', 'Name'], [['type', 'Typ', 'select', Object.entries(TYPES)], ['vlan_id', 'Netzwerk', 'select', vlanOpts()]],
    [['ip', 'IP-Adresse'], ['mac', 'MAC-Adresse']], [['hostname', 'Hostname'], ['url', 'Web-URL']],
    [['model', 'Modell'], ['os', 'System']], ['icon', 'Icon (Name aus dashboard-icons, z. B. proxmox)'],
    ['parent_id', 'Läuft auf / gehört zu', 'select', devOpts(d.id)], ['note', 'Notiz', 'area'],
    [['rack_id', 'Rack', 'select', [['', '– keins –'], ...S.racks.map(r => [r.id, r.name])]], ['rack_u', 'unterste HE', 'number']],
    ['rack_height', 'Höhe in HE', 'number'],
  ], d, async data => {
    if (!data.name) throw new Error('Name fehlt');
    if (data.rack_id && !data.rack_u) data.rack_u = 1;
    if (isNew) { const r = await api('POST', '/api/devices', data); sel = r.id; } else { await api('PUT', '/api/devices/' + d.id, data); sel = d.id; }
  }, '', true);
}
function linkForm(l) {
  const isNew = !l.id;
  openForm(isNew ? 'Neue Verbindung' : 'Verbindung', [
    [['a_id', 'Von (bei API: fragt ab)', 'select', devOpts().slice(1)], ['a_port', 'Port']], [['b_id', 'Nach (bei API: wird abgefragt)', 'select', devOpts().slice(1)], ['b_port', 'Port']],
    [['speed', 'Geschwindigkeit', 'select', Object.keys(SPEED_W).map(s => [s, s])], ['kind', 'Art', 'select', KINDS]],
    ['wlan_id', 'WLAN / SSID (nur bei Art „WLAN“)', 'select', [['', '– keins –'], ...S.wlans.map(w => [w.id, w.ssid])]],
    ['vlan_id', 'Access-VLAN', 'select', vlanOpts()], ['trunk', 'Trunk (mehrere getaggte VLANs)', 'check'], ['note', 'Notiz / bei API: Protokoll, z. B. REST :8006, SNMP, MQTT'],
  ], l, async data => {
    if (isNew) await api('POST', '/api/links', data); else await api('PUT', '/api/links/' + l.id, data);
  }, isNew ? '' : `<button class="btn bad" type="button" data-act="delLink" data-id="${l.id}">Löschen</button>`, true);
}
function showLink(id) { const l = S.links.find(x => x.id === id); if (l) linkForm(l); }

// ------------------------------------------------------------ Racks
const UH = 28;
function renderRacks() {
  const free = S.devices.filter(d => !d.parent_id && !d.rack_id && !['internet', 'client', 'iot', 'workstation'].includes(d.type));
  let h = `<div class="page" style="max-width:none"><div class="bar"><h2>Racks</h2><button class="btn pri" data-act="newRack">+ Rack</button>` +
    `<span class="muted">Geräte per Ziehen verschieben · freie Höheneinheit antippen zum Einbauen</span></div>`;
  if (!S.racks.length) h += '<div class="hint">Noch kein Rack angelegt.</div>';
  h += '<div class="racks">' + S.racks.map(r => {
    const ds = S.devices.filter(d => d.rack_id === r.id && d.rack_u);
    let rows = '';
    for (let u = 1; u <= r.units; u++) {
      const t = (r.units - u) * UH;
      rows += `<span class="un" style="top:${t}px">${u}</span><span class="un r" style="top:${t}px">${u}</span>`;
    }
    const used = ds.reduce((a, d) => a + (d.rack_height || 1), 0);
    return `<div class="rack"><div class="rh"><b>${esc(r.name)}</b><span class="muted">${esc(r.location || '')} · ${used}/${r.units} HE belegt</span>` +
      `<button class="btn sm" style="margin-left:auto" data-act="editRack" data-id="${r.id}">✎</button></div>` +
      `<div class="rbody" data-rack="${r.id}" data-units="${r.units}" style="height:${r.units * UH + 4}px">${rows}` +
      ds.map(d => { const hh = d.rack_height || 1; return `<div class="rdev" data-id="${d.id}" style="--c:${esc(vcol(d.vlan_id))};top:${(r.units - (d.rack_u + hh - 1)) * UH + 1}px;height:${hh * UH - 2}px">` +
        `<img src="${icon(d)}" alt=""><span class="dot ${d.status}"></span><b>${esc(d.name)}</b><span class="ip">${esc(d.ip || d.model || "")}</span></div>`; }).join('') +
      '</div></div>';
  }).join('');
  if (S.racks.length) h += `<div class="unracked"><div class="rh"><b>Nicht eingebaut</b></div>` +
    (free.map(d => `<div class="rowl"><img src="${icon(d)}" width="18" height="18" alt=""><a href="#" data-act="show" data-id="${d.id}">${esc(d.name)}</a>` +
      `<span class="muted" style="margin-left:auto">${esc(TYPES[d.type] || '')}</span></div>`).join('') || '<span class="muted">alles eingebaut</span>') + '</div>';
  main.innerHTML = h + '</div></div>';
  main.querySelectorAll('.rbody').forEach(bindRack);
}
function bindRack(body) {
  const units = +body.dataset.units, rid = +body.dataset.rack;
  const occupied = (u, hh, skip) => S.devices.some(d => d.rack_id === rid && d.id !== skip && d.rack_u && u < d.rack_u + (d.rack_height || 1) && d.rack_u < u + hh);
  body.addEventListener('click', e => {
    if (ro() || e.target.closest('.rdev')) return;
    const u = units - Math.floor((e.clientY - body.getBoundingClientRect().top) / UH);
    if (u < 1 || u > units || occupied(u, 1)) return;
    const free = S.devices.filter(d => !d.parent_id && !d.rack_id);
    if (!free.length) return toast('Kein freies Gerät – erst ein Gerät anlegen');
    openForm(`Einbauen in HE ${u}`, [['id', 'Gerät', 'select', free.map(d => [d.id, d.name])], ['rack_height', 'Höhe in HE', 'number']], {rack_height: 1},
      async data => {
        const hh = Math.max(1, +data.rack_height || 1);
        if (u + hh - 1 > units || occupied(u, hh)) throw new Error('Dort ist nicht genug Platz');
        await api('PUT', '/api/devices/' + data.id, {rack_id: rid, rack_u: u, rack_height: hh});
      });
  });
  body.querySelectorAll('.rdev').forEach(el => {
    let sy = null, top0 = 0, moved = false;
    el.addEventListener('pointerdown', e => { sy = e.clientY; top0 = parseFloat(el.style.top); moved = false; el.setPointerCapture(e.pointerId); });
    el.addEventListener('pointermove', e => {
      if (sy == null) return;
      if (ro() || (!moved && Math.abs(e.clientY - sy) < 5)) return;
      moved = true; busy = true; el.classList.add('drag'); el.style.top = (top0 + e.clientY - sy) + 'px';
    });
    el.addEventListener('pointerup', () => {
      if (sy == null) return;
      sy = null; busy = false; el.classList.remove('drag');
      const d = dev(+el.dataset.id), hh = d.rack_height || 1;
      if (!moved) return showDevice(d.id);
      const u = Math.min(units - hh + 1, Math.max(1, units - Math.round((parseFloat(el.style.top) - 1) / UH) - hh + 1));
      if (u === d.rack_u || occupied(u, hh, d.id)) { if (u !== d.rack_u) toast('Platz ist belegt', true); return renderRacks(); }
      run(() => api('PUT', '/api/devices/' + d.id, {rack_u: u}));
    });
  });
}

// ------------------------------------------------------------ Netzwerke
let netMode = 'grid', netQ = '', netVlan = '', netSort = {k: 'ip', dir: 1}, findQ = '';
const match = (q, ...vals) => { q = q.trim().toLowerCase(); return !q || q.split(/\s+/).every(w => vals.some(x => String(x ?? '').toLowerCase().includes(w))); };
const searchBox = (id, val, ph) => `<input class="inp search" id="${id}" type="search" value="${esc(val)}" placeholder="${ph}" aria-label="${ph}" autocomplete="off">`;
function netRows() {
  const rows = [];
  for (const d of S.devices) {
    const base = {id: d.id, name: d.name, type: TYPES[d.type] || d.type, hostname: d.hostname || ''};
    const multi = addrsOf(d).length && d.meta.up0 !== undefined;
    if (d.ip) rows.push({...base, ip: d.ip, mac: d.mac || '', vendor: d.vendor || '', vlan_id: d.vlan_id,
      status: multi ? (d.meta.up0 ? 'online' : 'offline') : d.status || 'unknown', seen: d.last_seen});
    for (const a of addrsOf(d)) if (a.ip) rows.push({...base, name: d.name + (a.label ? ' · ' + a.label : ''), ip: a.ip, mac: a.mac || '', vendor: a.vendor || '',
      vlan_id: a.vlan_id, hostname: a.hostname || '', status: a.up === true ? 'online' : a.up === false ? 'offline' : 'unknown', seen: a.last_seen});
  }
  for (const f of S.discoveries.filter(x => x.state === 'pending')) rows.push({find: f.id, name: '', type: TYPES[(f.guess || {}).type] || '', hostname: f.hostname || '',
    ip: f.ip, mac: f.mac || '', vendor: f.vendor || '', vlan_id: f.vlan_id, status: 'pending', seen: f.last_seen});
  return rows;
}
const STATUS = {online: 'online', offline: 'offline', unknown: 'unbekannt', pending: 'neu gefunden'};
function netFiltered() {
  const k = netSort.k, key = r => k === 'ip' ? (/^\d+\.\d+\.\d+\.\d+$/.test(r.ip) ? ip2int(r.ip) : 0) : k === 'seen' ? (r.seen || 0) :
    k === 'vlan' ? ((vlan(r.vlan_id) || {}).vid ?? 99999) : String(r[k] || '').toLowerCase();
  return netRows().filter(r => (!netVlan || String(r.vlan_id) === netVlan) &&
    match(netQ, r.ip, r.name, r.hostname, r.type, r.mac, r.vendor, STATUS[r.status], (vlan(r.vlan_id) || {}).name, vtag(vlan(r.vlan_id))))
    .sort((a, b) => { const x = key(a), y = key(b); return (x < y ? -1 : x > y ? 1 : 0) * netSort.dir; });
}
function netTable() {
  const rows = netFiltered(), cols = [['status', 'Status'], ['ip', 'IP-Adresse'], ['name', 'Gerät'], ['hostname', 'Hostname'], ['type', 'Typ'], ['mac', 'MAC'],
    ['vendor', 'Hersteller'], ['vlan', 'Netzwerk'], ['seen', 'Zuletzt gesehen']];
  return `<div class="muted" style="font-size:12.5px;margin-bottom:8px">${rows.length} ${rows.length === 1 ? 'Adresse' : 'Adressen'}</div><div class="tscroll"><table class="t sortable"><tr><th style="width:28px"><input type="checkbox" data-act="rowAll" aria-label="Alle auswählen"></th>` +
    cols.map(([k, l]) => `<th data-act="netSort" data-k="${k}" aria-sort="${netSort.k === k ? (netSort.dir > 0 ? 'ascending' : 'descending') : 'none'}">${l}${netSort.k === k ? (netSort.dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>' +
    (rows.map(r => { const v = vlan(r.vlan_id);
      return `<tr class="clk" ${r.find ? 'data-act="goFinds"' : `data-act="show" data-id="${r.id}"`}><td>${r.find ? '' : `<input type="checkbox" data-act="rowSel" data-id="${r.id}"${multi.has(r.id) ? ' checked' : ''} aria-label="${esc(r.name)} auswählen">`}</td><td><span class="dot ${r.status === 'pending' ? 'pending' : r.status}"></span> ${STATUS[r.status]}</td>` +
        `<td class="mono">${esc(r.ip)}</td><td>${r.find ? '<span class="muted">– noch nicht dokumentiert –</span>' : `<b>${esc(r.name)}</b>`}</td><td class="mono">${esc(r.hostname)}</td><td>${esc(r.type)}</td>` +
        `<td class="mono">${esc(r.mac)}</td><td>${esc(r.vendor)}</td><td>${v ? `<span style="color:${esc(v.color)}">${esc(v.vid != null ? vtag(v) + ' · ' + v.name : v.name)}</span>` : ''}</td><td>${r.seen ? 'vor ' + ago(r.seen) : ''}</td></tr>`; }).join('') ||
      `<tr><td colspan="${cols.length + 1}" class="muted">Keine Treffer.</td></tr>`) + '</table></div>';
}
function netGrid() {
  const byIp = new Map();
  for (const d of S.devices) {
    for (const a of addrsOf(d)) if (a.ip) byIp.set(a.ip, {id: d.id, name: d.name + (a.label ? ' · ' + a.label : ''), status: a.up === true ? 'online' : a.up === false ? 'offline' : 'unknown'});
  }
  for (const d of S.devices) if (d.ip) byIp.set(d.ip, addrsOf(d).length && d.meta.up0 !== undefined ? {id: d.id, name: d.name, status: d.meta.up0 ? 'online' : 'offline'} : d);
  const pend = new Map(S.discoveries.filter(d => d.state === 'pending').map(d => [d.ip, d]));
  let h = '<div class="cards">';
  for (const v of S.vlans.filter(v => match(netQ, vtag(v), v.name, v.subnet, v.note, v.gateway))) {
    const devs = S.devices.filter(d => inVlan(d, v.id));
    let grid = '';
    const m = /^(\d+\.\d+\.\d+\.\d+)\/(\d+)$/.exec(v.subnet || '');
    if (m && +m[2] >= 22 && +m[2] <= 30) {
      const size = 2 ** (32 - +m[2]), base = (ip2int(m[1]) >>> 0) & ~(size - 1);
      for (let i = 0; i < size; i++) {
        const ip = int2ip((base + i) >>> 0), d = byIp.get(ip), p = pend.get(ip);
        const cls = d ? 'd ' + (d.status || 'unknown') : p ? 'd pending' : '';
        grid += `<i class="${cls}${ip === v.gateway ? ' gw' : ''}" title="${ip}${d ? ' · ' + esc(d.name) : p ? ' · neu gefunden' : ''}"` +
          (d ? ` data-act="show" data-id="${d.id}"` : p ? ' data-act="goFinds"' : '') + '></i>';
      }
      grid = `<div class="ipgrid">${grid}</div>`;
    }
    h += `<div class="box net" style="--c:${esc(v.color)}"><div class="hd"><span class="tag">${esc(vtag(v))}</span><b>${esc(v.name)}</b><span class="sub">${esc(v.subnet || '')}</span></div>` +
      `<div class="muted" style="font-size:12.5px">${esc(v.note || '')}${v.gateway ? ' · Gateway ' + esc(v.gateway) : ''}</div>${grid}` +
      `<div class="keyrow"><span>${devs.length} Geräte · ${devs.filter(d => d.status === 'online').length} online</span>` +
      `<span>${v.scan ? 'Auto-Scan an' : 'Auto-Scan aus'} · letzter Scan: ${ago(v.last_scan)}</span></div>` +
      `<div class="acts" style="margin-bottom:0"><button class="btn sm" data-act="scan" data-id="${v.id}"${v.subnet && !S.scanner.running ? '' : ' disabled'}>Jetzt scannen</button>` +
      `<button class="btn sm" data-act="editVlan" data-id="${v.id}">Bearbeiten</button></div></div>`;
  }
  h += '</div>' + (S.vlans.length ? `<div class="keyrow"><span><i style="background:var(--ok)"></i>online</span><span><i style="background:var(--bad)"></i>offline</span>` +
    `<span><i style="background:var(--faint)"></i>dokumentiert, Status unbekannt</span><span><i style="background:var(--warn)"></i>neu gefunden</span><span><i style="background:#161f2b"></i>frei</span></div>` :
    '<div class="hint">Lege dein erstes Netz an (z. B. 192.168.178.0/24) und aktiviere den Auto-Scan.</div>');
  return h;
}
function wlanSection() {
  const ws = S.wlans.filter(w => match(netQ, w.ssid, w.band, w.security, w.note, (vlan(w.vlan_id) || {}).name, (w.aps || []).map(a => (dev(a) || {}).name).join(' ')));
  return `<div class="bar" style="margin-top:28px"><h2>WLAN</h2><button class="btn pri" data-act="newWlan">+ WLAN</button><span class="muted">${S.wlans.length} SSIDs</span></div>` +
    (ws.length ? '<div class="cards">' + ws.map(w => { const v = vlan(w.vlan_id), aps = (w.aps || []).map(dev).filter(Boolean);
      const clients = S.links.filter(l => l.kind === 'wlan' && l.wlan_id === w.id).length;
      return `<div class="box net" style="--c:${esc(v ? v.color : '#5d6a7c')}"><div class="hd"><span class="tag">SSID</span><b class="mono">${esc(w.ssid)}</b><span class="sub">${esc(w.band || '')}</span></div>` +
        `<div class="muted" style="font-size:12.5px;margin:3px 0 8px">${v ? `<span style="color:${esc(v.color)}">${esc(v.vid != null ? vtag(v) + ' · ' + v.name : v.name)}</span>` : 'kein Netzwerk zugeordnet'}` +
        `${w.security ? ' · ' + esc(w.security) : ''}${w.note ? ' · ' + esc(w.note) : ''}</div>` +
        `<div style="display:flex;flex-wrap:wrap;gap:5px">${aps.map(a => `<a class="pill" href="#" data-act="show" data-id="${a.id}"><span class="dot ${a.status}" style="width:7px;height:7px;margin-right:5px"></span>${esc(a.name)}</a>`).join('') || '<span class="muted" style="font-size:12.5px">noch keinem Access Point zugeordnet</span>'}</div>` +
        `<div class="keyrow"><span>${aps.length} Access Points · ${clients} dokumentierte WLAN-Verbindungen</span></div>` +
        `<div class="acts" style="margin-bottom:0"><button class="btn sm" data-act="editWlan" data-id="${w.id}">Bearbeiten</button></div></div>`; }).join('') + '</div>' :
      `<div class="hint">${S.wlans.length ? 'Keine Treffer.' : 'Lege deine SSIDs an und ordne sie einem Netzwerk und den Access Points zu. Die SSIDs erscheinen dann auf den AP-Karten in der Topologie.'}</div>`);
}
function wlanForm(w) {
  const isNew = !w.id, aps = S.devices.filter(d => !['app', 'service', 'internet', 'container', 'vm', 'client'].includes(d.type))
    .sort((a, b) => (b.type === 'ap') - (a.type === 'ap') || a.name.localeCompare(b.name)).map(d => [d.id, d.name + (d.type === 'ap' ? '' : ' (' + (TYPES[d.type] || d.type) + ')')]);
  openForm(isNew ? 'Neues WLAN' : esc(w.ssid), [['ssid', 'SSID (Name des WLANs)'], ['vlan_id', 'Netzwerk / VLAN', 'select', vlanOpts()],
    [['band', 'Band', 'select', [['', '–'], ...BANDS.map(b => [b, b])]], ['security', 'Verschlüsselung', 'select', [['', '–'], ...SECS.map(b => [b, b])]]],
    ['aps', 'Ausgestrahlt von (Mehrfachauswahl)', 'multi', aps], ['note', 'Notiz (z. B. Gäste, nur IoT)']], isNew ? {aps: []} : w, async data => {
    if (!data.ssid) throw new Error('SSID fehlt');
    if (isNew) await api('POST', '/api/wlans', data); else await api('PUT', '/api/wlans/' + w.id, data);
  }, isNew ? '' : `<button class="btn bad" type="button" data-act="delWlan" data-id="${w.id}">Löschen</button>`, !!sel);
}
function fillNets() {
  const b = $('#netbody'); if (b) b.innerHTML = netMode === 'table' ? netTable() : netGrid();
  const w = $('#wlanbody'); if (w) w.innerHTML = wlanSection();
}
function renderNets() {
  main.innerHTML = `<div class="page"><div class="bar"><h2>Netzwerke &amp; VLANs</h2><button class="btn pri" data-act="newVlan">+ Netzwerk</button>` +
    `<span class="seg"><button class="btn sm${netMode === 'grid' ? ' on' : ''}" data-act="netMode" data-m="grid">Raster</button><button class="btn sm${netMode === 'table' ? ' on' : ''}" data-act="netMode" data-m="table">Tabelle</button></span>` +
    `<span class="grow"></span><span class="muted">Auto-Scan alle ${esc(S.settings.scan_interval_min)} min</span></div>` +
    `<div class="bar">${searchBox('netq', netQ, netMode === 'table' ? 'Suchen: IP, Name, MAC, Hersteller …' : 'Netzwerk suchen …')}` +
    (netMode === 'table' ? `<select class="inp" id="netv" style="width:auto" aria-label="Netzwerk filtern"><option value="">Alle Netzwerke</option>${S.vlans.map(v => `<option value="${v.id}"${String(v.id) === netVlan ? ' selected' : ''}>${esc(v.vid != null ? vtag(v) + ' · ' + v.name : v.name)}</option>`).join('')}</select>` +
      `<button class="btn" data-act="netCsv">CSV</button>` : '') + '</div>' +
    (S.scanner.privileged ? '' : '<div class="hint" style="margin-bottom:14px">Der Container läuft ohne Root-Rechte – MAC-Adressen und Hersteller werden so nicht erkannt.</div>') +
    '<div id="netbody"></div><div id="wlanbody"></div></div>';
  fillNets();
  $('#netq').addEventListener('input', e => { netQ = e.target.value; fillNets(); });
  if ($('#netv')) $('#netv').addEventListener('change', e => { netVlan = e.target.value; fillNets(); });
}
function vlanForm(v) {
  const isNew = !v.id;
  openForm(isNew ? 'Neues Netzwerk' : esc(v.name), [
    [['name', 'Name'], ['vid', 'VLAN-ID (leer = untagged)', 'number']], [['subnet', 'Subnetz (CIDR)', 'text', '192.168.178.0/24'], ['gateway', 'Gateway']],
    [['color', 'Farbe', 'color'], ['scan', 'Automatisch scannen', 'check']], ['note', 'Regel / Notiz'],
  ], isNew ? {color: '#58a6ff', scan: 1} : v, async data => {
    if (!data.name) throw new Error('Name fehlt');
    if (isNew) await api('POST', '/api/vlans', data); else await api('PUT', '/api/vlans/' + v.id, data);
  }, isNew ? '' : `<button class="btn bad" type="button" data-act="delVlan" data-id="${v.id}">Löschen</button>`);
}

// ------------------------------------------------------------ Funde
function renderFinds() {
  const pend = S.discoveries.filter(d => d.state === 'pending'), ign = S.discoveries.filter(d => d.state === 'ignored');
  const card = d => {
    const g = d.guess || {}, v = vlan(d.vlan_id), titles = Object.entries(d.http || {}).filter(([, x]) => x.title).map(([p, x]) => `${p}: ${x.title}`);
    return `<div class="box find"><div class="hd"><img src="/api/icon/${esc(g.icon || 'type-' + (g.type || 'other'))}" width="26" height="26" alt="">` +
      `<b>${esc(d.ip)}</b><span>${esc(d.hostname || '')}</span><span class="pill" style="margin-left:auto">${esc(TYPES[g.type] || 'Gerät')}</span></div>` +
      `<div class="muted" style="font-size:12.5px;margin-top:4px">${d.mac ? `<span class="mono">${esc(d.mac)}</span> · ${esc(d.vendor || 'Hersteller unbekannt')}` : 'keine MAC (anderes Subnetz oder ohne Host-Netz)'}` +
      `${v ? ` · <span style="color:${esc(v.color)}">${esc(v.name)}</span>` : ''}${g.os ? ' · ' + esc(g.os) : ''}</div>` +
      (titles.length ? `<div class="faint" style="font-size:12px">${esc(titles.join(' | '))}</div>` : '') +
      `<div class="pl">${(d.ports || []).map(p => `<span class="pill">${p}</span>`).join('')}</div>` +
      (g.suggestions || []).map(s => `<div class="sug"><b>${esc(s.title)}</b><small>${esc(s.reason)} · liest: ${esc(s.reads)}</small></div>`).join('') +
      `<div class="acts" style="margin-bottom:0">` + (d.state === 'pending' ?
        `<button class="btn sm pri" data-act="approve" data-id="${d.id}">Übernehmen</button><button class="btn sm" data-act="attach" data-id="${d.id}">Zu Gerät hinzufügen</button><button class="btn sm" data-act="ignore" data-id="${d.id}">Ignorieren</button>` :
        `<button class="btn sm" data-act="restore" data-id="${d.id}">Wiederherstellen</button>`) + '</div></div>';
  };
  const fq = d => match(findQ, d.ip, d.hostname, d.mac, d.vendor, TYPES[(d.guess || {}).type], (d.guess || {}).os, (vlan(d.vlan_id) || {}).name,
    (d.ports || []).join(' '), Object.values(d.http || {}).map(x => x.title).join(' '), ((d.guess || {}).suggestions || []).map(x => x.title).join(' '));
  const body = () => { const p = pend.filter(fq), g = ign.filter(fq);
    return (p.length ? `<div class="cards">${p.map(card).join('')}</div>` : `<div class="hint">${pend.length ? 'Keine Treffer.' : 'Keine neuen Geräte. Scans startest du unter <b>Netzwerke</b>.'}</div>`) +
      (g.length ? `<h3 class="faint" style="margin-top:26px">Ignoriert (${g.length})</h3><div class="cards">${g.map(card).join('')}</div>` : ''); };
  main.innerHTML = `<div class="page"><div class="bar"><h2>Funde</h2>${pend.length ? `<button class="btn pri" data-act="approve" data-id="all">Alle ${pend.length} übernehmen</button>` : ''}` +
    `<span class="muted">Geräte aus dem Scan, die noch nicht dokumentiert sind</span></div>` +
    `<div class="bar">${searchBox('findq', findQ, 'Suchen: IP, Name, MAC, Hersteller, Port …')}</div><div id="findbody">${body()}</div>` +
    `<h3 class="faint" style="margin-top:26px">Scan-Verlauf</h3><div class="tscroll"><table class="t"><tr><th>Netz</th><th>Start</th><th>Dauer</th><th>Hosts</th><th>Neu</th><th>Status</th></tr>` +
    S.scans.map(s => `<tr><td class="mono">${esc(s.network)}</td><td>vor ${ago(s.started)}</td><td>${s.finished ? Math.round(s.finished - s.started) + ' s' : '…'}</td>` +
      `<td>${s.hosts}</td><td>${s.new}</td><td>${esc(s.status)}${s.log ? ' · ' + esc(s.log) : ''}</td></tr>`).join('') + '</table></div></div>';
  $('#findq').addEventListener('input', e => { findQ = e.target.value; $('#findbody').innerHTML = body(); });
}

// ------------------------------------------------------------ Anbindungen
function renderInteg() {
  const open = [];
  for (const d of S.devices) for (const [n, s] of ((d.meta || {}).suggestions || []).entries())
    if (s.connector && !S.integrations.some(i => i.kind === s.connector && i.device_id === d.id)) open.push({d, s, n});
  main.innerHTML = `<div class="page"><div class="bar"><h2>Anbindungen</h2>` +
    Object.entries(S.kinds).map(([k, v]) => `<button class="btn" data-act="newInteg" data-kind="${k}">+ ${esc(v.label)}</button>`).join('') +
    `<span class="grow"></span><span class="muted">Sync alle ${esc(S.settings.sync_interval_min)} min</span></div>` +
    (S.integrations.length ? `<div class="cards">${S.integrations.map(i => { const d = dev(i.device_id); const bad = (i.last_status || '').startsWith('Fehler');
      return `<div class="box"><div class="rowl" style="border:0;padding:0"><b>${esc(S.kinds[i.kind].label)}</b><span class="muted">${esc(i.name || i.config.host || i.config.url || '')}</span>` +
        `<span class="dot ${bad ? 'offline' : i.last_sync ? 'online' : ''}" style="margin-left:auto"></span></div>` +
        `<div class="muted" style="font-size:12.5px;margin:4px 0">${d ? 'Gerät: ' + esc(d.name) + ' · ' : ''}Sync vor ${ago(i.last_sync)}</div>` +
        `<div style="font-size:13px;${bad ? 'color:#ffb4ae' : ''}">${esc(i.last_status || 'noch nicht synchronisiert')}</div>` +
        `<div class="acts" style="margin-bottom:0"><button class="btn sm pri" data-act="sync" data-id="${i.id}">Jetzt synchronisieren</button>` +
        `<button class="btn sm" data-act="editInteg" data-id="${i.id}">Bearbeiten</button><button class="btn sm bad" data-act="delInteg" data-id="${i.id}">Löschen</button></div></div>`; }).join('')}</div>` :
      '<div class="hint">Anbindungen lesen Systeme regelmäßig aus: Proxmox liefert VMs und Container, Docker die Container je Host, SNMP die Switch-Ports samt LLDP-Nachbarn (daraus werden Kabel), OPNsense die VLANs.</div>') +
    (open.length ? `<h3 class="faint" style="margin-top:26px">Vorschläge aus dem Scan</h3><div class="cards">${open.map(({d, s, n}) => `<div class="box"><b>${esc(s.title)}</b> für <a href="#" data-act="show" data-id="${d.id}">${esc(d.name)}</a>` +
      `<div class="muted" style="font-size:12.5px;margin:4px 0 8px">${esc(s.reason)} · liest: ${esc(s.reads)}</div>` +
      `<button class="btn sm pri" data-act="newInteg" data-kind="${esc(s.connector)}" data-dev="${d.id}" data-sug="${n}">Einrichten</button></div>`).join('')}</div>` : '') + '</div>';
}
function integForm(i) {
  const isNew = !i.id, k = S.kinds[i.kind];
  // Auswahl: dokumentierte Geräte und Funde aus dem Scan; passende (laut Erkennung) zuerst
  const fits = sug => (sug || []).some(x => x.connector === i.kind);
  const cands = [
    ...S.devices.filter(d => d.ip && !['app', 'service'].includes(d.type)).map(d => ({v: 'd:' + d.id, ip: d.ip, name: d.name, fit: fits((d.meta || {}).suggestions), label: `${d.name} · ${d.ip}`})),
    ...S.discoveries.filter(f => f.state === 'pending').map(f => ({v: 'f:' + f.id, ip: f.ip, name: (f.hostname || '').split('.')[0] || f.ip, fit: fits((f.guess || {}).suggestions),
      label: `Fund: ${f.ip}${f.hostname ? ' · ' + f.hostname : ''}${f.vendor ? ' · ' + f.vendor : ''}`})),
  ].sort((a, b) => b.fit - a.fit || a.label.localeCompare(b.label));
  const pickOpts = [['', '– von Hand eintragen –'], ...cands.map(c => [c.v, (c.fit ? '★ ' : '') + c.label])];
  const fields = [...(isNew && cands.length ? [['pick', `Gerät oder Fund auswählen (★ = ${esc(k.label)} erkannt)`, 'select', pickOpts]] : []),
    ['name', 'Bezeichnung'], ...k.fields.map(([key, label, ph, type]) => ['c_' + key, label, type || 'text', ph]),
    ['device_id', 'Gehört zu Gerät', 'select', devOpts()], ['enabled', 'Automatisch synchronisieren', 'check']];
  const val = {name: i.name, device_id: i.device_id, enabled: i.enabled ?? 1, pick: i.device_id ? 'd:' + i.device_id : ''};
  for (const [key, , ph] of k.fields) val['c_' + key] = (i.config || {})[key] ?? ph ?? '';
  openForm((isNew ? 'Neu: ' : '') + esc(k.label), fields, val, async data => {
    const body = {kind: i.kind, name: data.name, device_id: data.device_id, enabled: data.enabled, config: {}};
    for (const key in data) if (key.startsWith('c_')) body.config[key.slice(2)] = data[key];
    if ((data.pick || '').startsWith('f:')) body.device_id = (await api('POST', `/api/discoveries/${data.pick.slice(2)}/approve`)).ids[0];   // Fund wird dabei übernommen
    const id = isNew ? (await api('POST', '/api/integrations', body)).id : (await api('PUT', '/api/integrations/' + i.id, body), i.id);
    const r = await api('POST', `/api/integrations/${id}/sync`);
    setTimeout(() => toast(r.status, r.status.startsWith('Fehler')), 50);
  }, '', !!i.device_id && sel === i.device_id);
  const pick = $('[name=pick]', panel);
  if (pick) pick.addEventListener('change', () => {
    const c = cands.find(x => x.v === pick.value), f = n => $(`[name=${n}]`, panel);
    if (!c) return;
    if (f('c_host')) f('c_host').value = c.ip;
    if (f('c_url')) f('c_url').value = `http://${c.ip}:2375`;
    if (!f('name').value || f('name').dataset.auto) { f('name').value = c.name; f('name').dataset.auto = '1'; }
    f('device_id').value = c.v.startsWith('d:') ? c.v.slice(2) : '';
  });
}

// ------------------------------------------------------------ System
const ROLE = {read: 'Lesen', write: 'Ändern', admin: 'Admin'};
const roleOpts = cur => Object.entries(ROLE).map(([k, v]) => `<option value="${k}"${k === cur ? ' selected' : ''}>${v}</option>`).join('');
function renderSystem() {
  const s = S.settings, admin = S.role === 'admin';
  const vals = f => { const d = {}; for (const el of f.elements) if (el.name) d[el.name] = el.value; return d; };
  let h = `<div class="page" style="max-width:760px"><div class="bar"><h2>System</h2></div>` +
    `<h3 class="faint" style="margin-top:0">Konto</h3><div class="box"><div class="rowl" style="border:0;padding:0 0 10px">Angemeldet als <b>${esc(S.user)}</b>` +
    `<span class="pill">${ROLE[S.role]}</span><button class="btn sm" style="margin-left:auto" data-act="logout">Abmelden</button></div><form class="f" id="pwf"><div class="two">` +
    `<label>Aktuelles Passwort<input name="current" type="password" autocomplete="current-password" required></label>` +
    `<label>Neues Passwort<input name="new" type="password" autocomplete="new-password" minlength="10" required></label></div>` +
    `<div class="acts" style="margin:0"><button class="btn">Passwort ändern</button></div></form></div>`;
  if (admin) h += `<h3 class="faint" style="margin-top:24px">Benutzerverwaltung</h3><div class="box"><div id="users" class="muted">lädt …</div>` +
    `<p class="muted" style="font-size:12.5px;margin:10px 0"><b>Lesen</b>: alles ansehen · <b>Ändern</b>: dokumentieren, scannen, Anbindungen pflegen · ` +
    `<b>Admin</b>: zusätzlich Benutzer, Einstellungen, Export</p><form class="f" id="uf"><div class="two">` +
    `<label>Neuer Benutzername<input name="username" autocomplete="off" autocapitalize="none" required></label>` +
    `<label>Recht<select name="role">${roleOpts('read')}</select></label></div>` +
    `<label>Passwort (mind. 10 Zeichen)<input name="password" type="password" autocomplete="new-password" minlength="10" required></label>` +
    `<div class="acts" style="margin:0"><button class="btn pri">Benutzer anlegen</button></div></form></div>` +
    `<h3 class="faint" style="margin-top:24px">Einstellungen</h3><div class="box"><form class="f" id="setf">` +
    `<label>Titel<input name="title" value="${esc(s.title)}"></label><div class="two"><label>Scan-Intervall (Minuten)<input name="scan_interval_min" type="number" min="5" value="${esc(s.scan_interval_min)}"></label>` +
    `<label>Sync-Intervall der Anbindungen (Minuten)<input name="sync_interval_min" type="number" min="1" value="${esc(s.sync_interval_min)}"></label></div>` +
    `<label>SNMP-Community für den Scan<input name="snmp_community" value="${esc(s.snmp_community)}"></label>` +
    `<div class="acts" style="margin:0"><button class="btn pri">Speichern</button></div></form></div>` +
    `<h3 class="faint" style="margin-top:24px">Daten</h3><div class="box"><div class="acts" style="margin:0"><a class="btn" href="/api/export" download>Export (JSON)</a>` +
    `<button class="btn" data-act="pick" data-kind="restore">Export wiederherstellen</button><button class="btn" data-act="pick" data-kind="inventory">inventory.yaml importieren</button></div>` +
    `<p class="muted" style="margin:10px 0 0;font-size:12.5px">Der Export enthält die Zugangsdaten der Anbindungen. Der YAML-Import liest das Format von Goblinmine/homelab-diagram und legt die Einträge zusätzlich an. Wiederherstellen ersetzt alle Daten.</p></div>`;
  else if (S.role === 'write') h += `<h3 class="faint" style="margin-top:24px">Daten</h3><div class="box"><button class="btn" data-act="pick" data-kind="inventory">inventory.yaml importieren</button></div>`;
  main.innerHTML = h + `<p class="faint" style="font-size:12px;margin-top:18px">${S.devices.length} Geräte · ${S.links.length} Verbindungen · ${S.vlans.length} Netzwerke · ${S.racks.length} Racks</p></div>`;
  $('#pwf').addEventListener('submit', async e => {
    e.preventDefault();
    try { await api('POST', '/api/auth/password', vals(e.target)); e.target.reset(); toast('Passwort geändert – andere Sitzungen wurden abgemeldet'); }
    catch (x) { toast(x.message, true); }
  });
  if (!admin) return;
  $('#uf').addEventListener('submit', async e => {
    e.preventDefault();
    try { await api('POST', '/api/auth/users', vals(e.target)); toast('Benutzer angelegt'); renderSystem(); } catch (x) { toast(x.message, true); }
  });
  $('#setf').addEventListener('submit', e => { e.preventDefault(); run(() => api('POST', '/api/settings/save', vals(e.target)), 'Gespeichert'); });
  api('GET', '/api/auth/users').then(r => {
    const box = $('#users'); if (!box) return;
    box.className = '';
    box.innerHTML = r.users.map(u => `<div class="rowl" style="flex-wrap:wrap"><b>${esc(u.username)}</b><span class="muted" style="font-size:12px">zuletzt: ${ago(u.last_login)}</span>` +
      `<span style="margin-left:auto;display:flex;gap:6px;align-items:center">` + (u.id === r.me ? `<span class="pill">${ROLE[u.role]} · du</span>` :
        `<select class="inp usel" data-id="${u.id}" style="width:auto;padding:3px 6px;font-size:12.5px" aria-label="Recht von ${esc(u.username)}">${roleOpts(u.role)}</select>` +
        `<button class="btn sm" data-act="pwUser" data-id="${u.id}" data-name="${esc(u.username)}">Passwort</button>` +
        `<button class="btn sm bad" data-act="delUser" data-id="${u.id}" data-name="${esc(u.username)}">Löschen</button>`) + '</span></div>').join('');
    box.querySelectorAll('.usel').forEach(sel2 => sel2.addEventListener('change', async () => {
      try { await api('PUT', '/api/auth/users/' + sel2.dataset.id, {role: sel2.value}); toast('Recht geändert'); } catch (x) { toast(x.message, true); renderSystem(); }
    }));
  }).catch(() => {});
}

// ------------------------------------------------------------ Aktionen
const ACT = {
  close: closePanel,
  cancel: () => { if (sel && dev(sel)) showDevice(sel); else closePanel(); },
  show: d => { const x = dev(+d.id); if (x) showDevice(x.id); },
  goFinds: () => $('#tabs [data-view="finds"]').click(),
  fit: fitView,
  relayout: () => { if (confirm('Alle Karten neu anordnen? Deine Positionen gehen verloren.')) { for (const c of cards.values()) { c.x = null; c.d.x = null; } renderTopo(); fitView(); } },
  vfilter: d => { vfilter = vfilter === +d.id ? null : +d.id; renderTopo(); },
  newDevice: d => deviceForm({type: d.parent ? 'container' : 'server', parent_id: d.parent || '', rack_height: 1}),
  editDevice: d => deviceForm(dev(+d.id)),
  delDevice: d => { const x = dev(+d.id), n = kidsOf(x.id).length; if (confirm(`„${x.name}“${n ? ` samt ${n} enthaltenen Einträgen` : ''} löschen?`)) { closePanel(); run(() => api('DELETE', '/api/devices/' + x.id)); } },
  addAddr: d => { const x = dev(+d.id); sel = x.id; openForm('Weitere Adresse', [[['ip', 'IP-Adresse'], ['mac', 'MAC-Adresse']],
    ['label', 'Bezeichnung (z. B. eth1, Storage-Netz)'], ['vlan_id', 'Netzwerk (leer = automatisch nach Subnetz)', 'select', vlanOpts()]], {},
    data => api('POST', `/api/devices/${x.id}/addrs`, data), '', true); },
  delAddr: d => { if (confirm('Adresse entfernen? Beim nächsten Scan taucht sie wieder als Fund auf.')) run(() => api('DELETE', `/api/devices/${d.id}/addrs/${d.idx}`)); },
  merge: d => {
    const x = dev(+d.id); sel = x.id;
    const cand = S.devices.filter(o => o.id !== x.id && !['app', 'service', 'internet'].includes(o.type)).map(o => [o.id, o.name + (o.ip ? ' · ' + o.ip : '')]);
    if (!cand.length) return toast('Kein zweites Gerät vorhanden');
    openForm(`„${esc(x.name)}“ zusammenführen`, [['other_id', 'Dieses Gerät geht in „' + esc(x.name) + '“ auf', 'select', cand]], {},
      data => api('POST', `/api/devices/${x.id}/merge`, data),
      '<p class="muted" style="flex-basis:100%;font-size:12.5px;margin:6px 0 0">IP und MAC des gewählten Geräts werden zu einer weiteren Adresse. Kabel, enthaltene Geräte und Anbindungen wandern mit, der zweite Eintrag wird entfernt.</p>', true);
  },
  attach: d => {
    const f = S.discoveries.find(z => z.id === +d.id);
    const cand = S.devices.filter(o => !['app', 'service', 'internet'].includes(o.type)).map(o => [o.id, o.name + (o.ip ? ' · ' + o.ip : '')]);
    if (!cand.length) return toast('Noch kein Gerät dokumentiert');
    openForm(`${esc(f.ip)} hinzufügen zu`, [['device_id', 'Gerät', 'select', cand]], {},
      async data => { await api('POST', `/api/devices/${data.device_id}/attach/${f.id}`); });
  },
  netMode: d => { netMode = d.m; renderNets(); },
  netSort: d => { netSort = netSort.k === d.k ? {k: d.k, dir: -netSort.dir} : {k: d.k, dir: 1}; fillNets(); },
  netCsv: () => {
    const q = x => '"' + String(x ?? '').replace(/"/g, '""') + '"';
    const lines = [['Status', 'IP', 'Gerät', 'Hostname', 'Typ', 'MAC', 'Hersteller', 'VLAN', 'Netzwerk'].map(q).join(';'),
      ...netFiltered().map(r => { const v = vlan(r.vlan_id) || {}; return [STATUS[r.status], r.ip, r.name, r.hostname, r.type, r.mac, r.vendor, v.vid ?? '', v.name || ''].map(q).join(';'); })];
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(['\ufeff' + lines.join('\r\n')], {type: 'text/csv'})); a.download = 'labvis-adressen.csv'; a.click();
  },
  jump: d => {
    const x = dev(+d.id), c = cards.get(topOf(x.id)); if (!c) return;
    cam.k = Math.max(cam.k, 0.75); cam.x = main.clientWidth / 2 - (c.x + c.w / 2) * cam.k; cam.y = main.clientHeight / 2 - (c.y + Math.min(c.h, 300) / 2) * cam.k;
    applyCam(); $('#tres').hidden = true; $('#topoq').value = ''; showDevice(x.id);
  },
  newWlan: () => wlanForm({}),
  editWlan: d => wlanForm(wlan(+d.id)),
  delWlan: d => { if (confirm('WLAN löschen? Geräte und Verbindungen bleiben erhalten.')) { closePanel(); run(() => api('DELETE', '/api/wlans/' + d.id)); } },
  selMode: () => { selMode = !selMode; if (!selMode) multi.clear(); bulkBar(); renderTopo(); },
  rowSel: d => toggleMulti(+d.id),
  rowAll: (d, el) => { const ids = [...new Set(netFiltered().filter(r => r.id).map(r => r.id))]; for (const id of ids) if (multi.has(id) !== el.checked) toggleMulti(id); },
  bulkClear: () => { multi.clear(); selMode = false; bulkBar(); render(); },
  bulkDel: () => {
    const ids = [...multi], kids = ids.reduce((a, id) => a + kidsOf(id).filter(k => !multi.has(k.id)).length, 0);
    if (!confirm(`${ids.length} Geräte${kids ? ` samt ${kids} enthaltenen Einträgen` : ''} löschen?`)) return;
    closePanel(); multi.clear();
    run(async () => { for (const id of ids) if (dev(id)) await api('DELETE', '/api/devices/' + id).catch(() => {}); }, 'Gelöscht');
  },
  bulkEdit: () => {
    const ids = [...multi], keep = [['', '– unverändert –']];
    openForm(`${ids.length} Geräte ändern`, [
      [['type', 'Typ', 'select', [...keep, ...Object.entries(TYPES)]], ['vlan_id', 'Netzwerk', 'select', [...keep, ['none', '– keins –'], ...S.vlans.map(v => [v.id, v.vid != null ? `${vtag(v)} · ${v.name}` : v.name])]]],
      ['parent_id', 'Läuft auf / gehört zu', 'select', [...keep, ['none', '– eigenständig –'], ...S.devices.filter(d => !multi.has(d.id) && !['app', 'service'].includes(d.type)).map(d => [d.id, d.name])]],
      [['model', 'Modell (leer = unverändert)'], ['os', 'System (leer = unverändert)']], ['icon', 'Icon (leer = unverändert)'], ['note', 'Notiz (leer = unverändert)'],
    ], {}, async data => {
      const patch = {};
      for (const [k, v] of Object.entries(data)) if (v !== '') patch[k] = v === 'none' ? '' : v;
      if (!Object.keys(patch).length) throw new Error('Nichts zum Ändern ausgewählt');
      let fail = 0;
      for (const id of ids) await api('PUT', '/api/devices/' + id, patch).catch(() => { fail++; });
      if (fail) throw new Error(`${fail} von ${ids.length} Geräten ließen sich nicht ändern`);
    }, `<p class="muted" style="flex-basis:100%;font-size:12.5px;margin:6px 0 0">${ids.slice(0, 8).map(id => esc(dev(id).name)).join(', ')}${ids.length > 8 ? ' …' : ''}</p>`);
  },
  bulkMerge: () => {
    const ids = [...multi];
    openForm(`${ids.length} Geräte zusammenführen`, [['target', 'Dieses Gerät bleibt bestehen', 'select', ids.map(id => [id, dev(id).name + (dev(id).ip ? ' · ' + dev(id).ip : '')])]], {},
      async data => { for (const id of ids) if (id !== +data.target) await api('POST', `/api/devices/${data.target}/merge`, {other_id: id}); multi.clear(); },
      '<p class="muted" style="flex-basis:100%;font-size:12.5px;margin:6px 0 0">Die anderen Einträge gehen in diesem auf: Ihre Adressen werden zu weiteren Adressen, Kabel und enthaltene Geräte wandern mit. Das lässt sich nicht rückgängig machen.</p>');
  },
  newLink: d => linkForm({a_id: +d.id, speed: '1G', kind: d.kind || 'cable'}),
  editLink: d => showLink(+d.id),
  delLink: d => { closePanel(); run(() => api('DELETE', '/api/links/' + d.id)); },
  newRack: () => openForm('Neues Rack', [['name', 'Name'], [['units', 'Höheneinheiten', 'number'], ['location', 'Standort']], ['note', 'Notiz']], {units: 24},
    async data => { if (!data.name) throw new Error('Name fehlt'); await api('POST', '/api/racks', data); }),
  editRack: d => { const r = S.racks.find(x => x.id === +d.id); openForm(esc(r.name), [['name', 'Name'], [['units', 'Höheneinheiten', 'number'], ['location', 'Standort']], ['note', 'Notiz']], r,
    async data => { await api('PUT', '/api/racks/' + r.id, data); }, `<button class="btn bad" type="button" data-act="delRack" data-id="${r.id}">Löschen</button>`); },
  delRack: d => { if (confirm('Rack löschen? Die Geräte bleiben erhalten.')) { closePanel(); run(() => api('DELETE', '/api/racks/' + d.id)); } },
  newVlan: () => vlanForm({}),
  editVlan: d => vlanForm(vlan(+d.id)),
  delVlan: d => { if (confirm('Netzwerk löschen? Die Geräte bleiben erhalten.')) { closePanel(); run(() => api('DELETE', '/api/vlans/' + d.id)); } },
  scan: d => run(() => api('POST', `/api/vlans/${d.id}/scan`), 'Scan gestartet – Ergebnisse erscheinen unter „Funde“'),
  approve: d => run(() => api('POST', `/api/discoveries/${d.id}/approve`), 'Übernommen'),
  ignore: d => run(() => api('POST', `/api/discoveries/${d.id}/ignore`)),
  restore: d => run(() => api('POST', `/api/discoveries/${d.id}/restore`)),
  newInteg: d => {
    const x = d.dev ? dev(+d.dev) : null, s = x && d.sug != null ? x.meta.suggestions[+d.sug] : null;
    integForm({kind: d.kind, device_id: x ? x.id : '', name: x ? x.name : '', config: s ? s.config : {}});
  },
  editInteg: d => integForm(S.integrations.find(i => i.id === +d.id)),
  delInteg: d => { if (confirm('Anbindung löschen? Bereits ausgelesene Geräte bleiben erhalten.')) run(() => api('DELETE', '/api/integrations/' + d.id)); },
  sync: d => run(async () => { toast('Synchronisiere …'); const r = await api('POST', `/api/integrations/${d.id}/sync`); toast(r.status, r.status.startsWith('Fehler')); }),
  logout: async () => { await fetch('/api/auth/logout', {method: 'POST'}); location.href = '/login'; },
  pwUser: async d => {
    const pw = prompt(`Neues Passwort für „${d.name}“ (mindestens 10 Zeichen). Das Konto wird überall abgemeldet.`);
    if (!pw) return;
    try { await api('PUT', '/api/auth/users/' + d.id, {password: pw}); toast('Passwort gesetzt'); } catch (x) { toast(x.message, true); }
  },
  delUser: async d => {
    if (!confirm(`Benutzer „${d.name}“ löschen?`)) return;
    try { await api('DELETE', '/api/auth/users/' + d.id); renderSystem(); } catch (x) { toast(x.message, true); }
  },
  pick: d => {
    const f = document.createElement('input'); f.type = 'file'; f.accept = d.kind === 'restore' ? '.json' : '.yaml,.yml';
    f.onchange = async () => {
      const text = await f.files[0].text();
      if (d.kind === 'restore' && !confirm('Alle vorhandenen Daten ersetzen?')) return;
      run(() => d.kind === 'restore' ? api('POST', '/api/restore/all', JSON.parse(text)) : api('POST', '/api/import/inventory', text, true), 'Importiert');
      camSet = false;
    };
    f.click();
  },
  svgExport: async () => {
    const svg = $('#svg').cloneNode(true), cs = [...cards.values()];
    const x0 = Math.min(...cs.map(c => c.x)) - 40, y0 = Math.min(...cs.map(c => c.y)) - 40;
    const w = Math.max(...cs.map(c => c.x + c.w)) + 40 - x0, h = Math.max(...cs.map(c => c.y + c.h)) + 40 - y0;
    svg.querySelector('#world').setAttribute('transform', `translate(${-x0},${-y0})`);
    svg.querySelector('#world').classList.remove('focus');
    svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg'); svg.setAttribute('viewBox', `0 0 ${w} ${h}`); svg.setAttribute('width', w); svg.setAttribute('height', h);
    svg.removeAttribute('id');
    for (const im of svg.querySelectorAll('image')) {   // Icons einbetten, damit die Datei allein funktioniert
      try { const t = await (await fetch(im.getAttribute('href'))).text(); im.setAttribute('href', 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(t)))); } catch (e) { /* Icon bleibt verlinkt */ }
    }
    svg.insertAdjacentHTML('afterbegin', `<rect width="100%" height="100%" fill="${PAL.BG}"/><style>text{font-family:"Fira Sans",sans-serif}text.m{font-family:"Fira Code",monospace}.hit{fill:none;stroke:none}</style>`);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)], {type: 'image/svg+xml'}));
    a.download = 'homelab.svg'; a.click();
  },
};
const READ_OK = new Set(['close', 'cancel', 'show', 'goFinds', 'fit', 'vfilter', 'svgExport', 'logout', 'netMode', 'netSort', 'netCsv', 'jump']);
const ro = () => S && S.role === 'read';
document.head.insertAdjacentHTML('beforeend', '<style>' + Object.keys(ACT).filter(a => !READ_OK.has(a)).map(a => `body.ro [data-act="${a}"]`).join(',') + '{display:none!important}body.ro .rbody{cursor:default}body.ro .rdev{cursor:pointer}</style>');
document.addEventListener('click', e => {
  const b = e.target.closest('[data-act]');
  if (!b || !ACT[b.dataset.act]) return;
  if (ro() && !READ_OK.has(b.dataset.act)) return;
  if (b.tagName === 'A') e.preventDefault();
  ACT[b.dataset.act](b.dataset, b);
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !panel.hidden) ACT.cancel(); });

(async () => {
  try { await Promise.all(['400 13px "Fira Sans"', '600 13px "Fira Sans"', '700 19px "Fira Sans"', '500 13px "Fira Sans"', '400 12px "Fira Code"', '500 12px "Fira Code"'].map(f => document.fonts.load(f))); } catch (e) { /* Fallback-Schrift */ }
  await load();
  setInterval(() => {
    const typing = /INPUT|SELECT|TEXTAREA/.test((document.activeElement || {}).tagName || '');   // Eingaben nicht überschreiben
    if (!busy && panelMode !== 'form' && !typing && !document.hidden) load(true);
  }, 15000);
})();
