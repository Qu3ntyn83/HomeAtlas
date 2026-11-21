/* HomeAtlas – Oberfläche. Kein Build-Schritt, reines JS + SVG. */
'use strict';
const PAL = {BG: '#0b0f15', PANEL: '#111821', CHIP: '#19222e', BORDER: '#253042', TEXT: '#e6edf3', MUTED: '#8d9aab',
  FAINT: '#5d6a7c', TRUNK: '#d5dde6', TRUNKB: '#3a475a', LINK: '#79c0ff', OK: '#3fb950', BAD: '#f85149'};
const SPEED_W = {'100M': 1.4, '1G': 2.4, '2.5G': 3.8, '5G': 5.5, '10G': 8, '25G': 10, '40G': 12};
let TYPES = {internet: 'Internet', router: 'Router', firewall: 'Firewall', switch: 'Switch', ap: 'Access Point',
  hypervisor: 'Hypervisor', server: 'Server', nas: 'NAS', workstation: 'Workstation', client: 'Client', iot: 'IoT',
  printer: 'Drucker', vm: 'VM', container: 'Container', app: 'App', service: 'Dienst', other: 'Gerät',
  light: 'Lampe', plug: 'Steckdose', sensor: 'Sensor', thermostat: 'Thermostat', blind: 'Rollladen', lock: 'Türschloss', vacuum: 'Saugroboter',
  camera: 'Kamera', speaker: 'Lautsprecher', tv: 'TV / Medien', group: 'Bereich',
  patchpanel: 'Patchpanel', shelf: 'Rackboden', blank: 'Blende', cablemgmt: 'Kabelführung'};
const PASSIVE = new Set(['patchpanel', 'shelf', 'blank', 'cablemgmt']);   // Rack-Platzhalter: nur im Rack, nicht in der Topologie
const onShelf = id => S.devices.filter(d => (d.meta || {}).shelf === id);
const shelfOf = d => { const sh = dev((d.meta || {}).shelf); return sh && sh.type === 'shelf' && sh.rack_id ? sh : null; };
const API_COL = '#d2a8ff';
// Verbindungsarten. style: line = Kabel (VLAN-Farbe, Breite = Tempo), radio = Funk (gepunktet), bus = Feldbus/seriell (gestrichelt),
// arrow = Abfrage/Nachrichten mit Pfeil, logical = logisch. short erscheint als Beschriftung an der Verbindung.
const LK = {
  cable: {label: 'Kabel (Ethernet)', style: 'line'},
  wlan: {label: 'WLAN', style: 'radio', short: 'WLAN'},
  api: {label: 'API / Datenabfrage', style: 'arrow', short: 'API', col: '#d2a8ff'},
  logical: {label: 'logisch (VPN, Cloud)', style: 'logical'},
  zigbee: {label: 'Zigbee', style: 'radio', short: 'Zigbee', col: '#f0b72f', home: 1},
  zwave: {label: 'Z-Wave', style: 'radio', short: 'Z-Wave', col: '#39c5cf', home: 1},
  thread: {label: 'Thread', style: 'radio', short: 'Thread', col: '#bc8cff', home: 1},
  matter: {label: 'Matter (über WLAN/Ethernet/Thread)', style: 'logical', short: 'Matter', col: '#56d364', home: 1},
  ble: {label: 'Bluetooth / BLE', style: 'radio', short: 'BLE', col: '#4f9dff', home: 1},
  dect: {label: 'DECT ULE (FRITZ!Smart Home)', style: 'radio', short: 'DECT', col: '#ff7b72', home: 1},
  homematic: {label: 'Homematic IP / BidCoS', style: 'radio', short: 'HmIP', col: '#79c0ff', home: 1},
  enocean: {label: 'EnOcean', style: 'radio', short: 'EnOcean', col: '#7ee787', home: 1},
  rf: {label: 'Funk 433/868 MHz', style: 'radio', short: '433/868', col: '#e3b341', home: 1},
  lora: {label: 'LoRa / LoRaWAN', style: 'radio', short: 'LoRa', col: '#db61a2', home: 1},
  ir: {label: 'Infrarot', style: 'radio', short: 'IR', col: '#f778ba', home: 1},
  mqtt: {label: 'MQTT (Nachrichten über Broker)', style: 'arrow', short: 'MQTT', col: '#a5d6ff', home: 1},
  knx: {label: 'KNX (Bus)', style: 'bus', short: 'KNX', col: '#3fb950', home: 1},
  bus: {label: 'Feldbus (RS-485, Modbus, 1-Wire)', style: 'bus', short: 'Bus', col: '#a8b3bf', home: 1},
  usb: {label: 'USB / seriell (z. B. Funkstick)', style: 'bus', short: 'USB', col: '#c9d1d9', home: 1},
};
LK.wan = {label: 'Internetzugang (WAN)', style: 'wan', short: 'WAN', col: '#ffa657'};
const KINDS = ['cable', 'wan', ...Object.keys(LK).filter(k => k !== 'cable' && k !== 'wan')].map(k => [k, LK[k].label]);
// Internetzugang (ISP) eines Internet-Geräts
const ACCESS = {fiber: ['Glasfaser (FTTH)', 'Glasfaser'], vdsl: ['VDSL / Supervectoring', 'VDSL'], adsl: ['ADSL', 'ADSL'], cable: ['Kabel (DOCSIS)', 'Kabel'],
  lte: ['LTE', 'LTE'], '5g': ['5G', '5G'], sat: ['Satellit (z. B. Starlink)', 'Satellit'], wisp: ['Richtfunk', 'Richtfunk'], other: ['sonstiger', '']};
const IP4MODE = {dynamic: 'dynamisch', static: 'statisch', cgnat: 'CGNAT (geteilte IPv4)', dslite: 'DS-Lite (IPv4 über IPv6)', none: 'keine IPv4'};
const isNet = d => d && bt(d.type) === 'internet';
const ispOf = d => (d && d.meta && d.meta.isp) || {};
const liveOf = d => (d && d.meta && d.meta.isp_live) || null;
const bwTxt = i => i.down || i.up ? `${i.down || '?'}/${i.up || '?'} Mbit/s` : '';
const mbit = n => n >= 1000 && n % 1000 === 0 ? n / 1000 + ' Gbit/s' : n + ' Mbit/s';
const liveTxt = L => !L ? '' : L.status === 'down' || L.status === 'force_down' ? 'offline' : [L.delay != null ? Math.round(L.delay) + ' ms' : '', L.loss ? L.loss + ' % Verlust' : ''].filter(Boolean).join(' · ') || 'online';
const lkOf = l => LK[l.kind] || LK.cable;
// Farbe einer Verbindung: Kabel nach VLAN, WLAN nach SSID-Netz, sonst feste Farbe der Art
const lkCol = (l, vlanCol) => l.kind === 'wlan' ? wcol(l) : l.kind === 'logical' ? PAL.MUTED : (LK[l.kind] && LK[l.kind].col) || vlanCol;
const lkName = (l, me) => { const k = lkOf(l); if (l.kind === 'cable' || !LK[l.kind]) return null; if (k.style === 'arrow') return me == null ? k.short : (l.a_id === me ? k.short + ' →' : '← ' + k.short); return k.short || k.label; };
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
let TYPEDEF = {};
// Icon eines Typs: eigenes Icon aus der Typ-Verwaltung, sonst das eingebaute Symbol (bei eigenen Typen das der Vorlage)
const typeIcon = t => { const x = TYPEDEF[t]; return (x && x.icon) || 'type-' + (x && x.custom ? x.base : (t || 'other')); };
const bt = t => (TYPEDEF[t] || {}).base || t;
const typeOpts = cur => (S && S.types ? S.types.filter(t => !t.hidden || t.key === cur).sort((a, b) => a.label.localeCompare(b.label, 'de')).map(t => [t.key, t.label]) : Object.entries(TYPES));
// eigene Icons tragen ihre Dateigröße/Zeit als Version, damit ein ersetztes Icon sofort überall erscheint
const iconUrl = n => '/api/icon/' + encodeURIComponent(n) + (n && n.startsWith('up-') ? '?v=' + (((S && S.icons) || []).find(i => i.name === n) || {}).v : '');
const icon = d => iconUrl(d.icon || typeIcon(d.type || 'other'));
const addrsOf = d => (d.meta && d.meta.addrs) || [];
const inVlan = (d, vid) => d.vlan_id === vid || addrsOf(d).some(a => a.vlan_id === vid);
const wlan = id => S.wlans.find(w => w.id === id);
const ssidsOf = id => S.wlans.filter(w => (w.aps || []).includes(id));
const vtag = v => v ? (v.vid != null ? 'VLAN ' + v.vid : v.name) : '';
function topDev(id) { let d = dev(id), n = 0; while (d && d.parent_id && n++ < 8) d = dev(d.parent_id) || d; return d || null; }
// Raum eines Geräts: eigener Eintrag, sonst der nächste übergeordnete (Host, Bridge, Bereich), sonst der Standort des Racks
const NOROOM = 'Ohne Raum';
function roomOf(d) {
  for (let x = d, n = 0; x && n < 10; x = x.parent_id ? dev(x.parent_id) : null, n++) if ((x.room || '').trim()) return x.room.trim();
  const t = roomUnit(d.id) || d, sh = (t.meta || {}).shelf ? dev(t.meta.shelf) : null;
  const rack = S.racks.find(r => r.id === (t.rack_id || (sh && sh.rack_id)));
  return ((rack && rack.location) || '').trim() || NOROOM;
}
// In der Raum-Ansicht zählen Bereiche (Gruppen) nicht: ihre Geräte stehen einzeln in ihrem Raum
function roomUnit(id) {
  let d = dev(id), n = 0;
  while (d && d.parent_id && n++ < 8) { const p = dev(d.parent_id); if (!p || p.type === 'group') break; d = p; }
  return d || null;
}
const allRooms = () => [...new Set(S.devices.map(d => (d.room || '').trim()).concat(S.racks.map(r => (r.location || '').trim())).filter(Boolean))].sort((a, b) => a.localeCompare(b));
let viewMode = 'normal', roomIds = new Map();
// Karte, zu der ein Gerät gehört: in der Raum-Ansicht die Raumkarte, sonst die Karte des obersten Geräts
function topOf(id) {
  const t = topDev(id); if (!t) return null;
  if (viewMode !== 'rooms') return t.id;
  const u = roomUnit(id) || t;
  return roomIds.get(roomOf(u)) ?? t.id;
}
// frühere Einstellungen aus LabVis übernehmen (einmalig)
try { for (const k of ['nav', 'navgrp', 'roompos']) if (localStorage.getItem('labvis.' + k) !== null && localStorage.getItem('homeatlas.' + k) === null) { localStorage.setItem('homeatlas.' + k, localStorage.getItem('labvis.' + k)); localStorage.removeItem('labvis.' + k); } } catch (e) { /* ohne Speicher nichts zu übernehmen */ }
const roomPos = () => { try { return JSON.parse(localStorage.getItem('homeatlas.roompos') || '{}'); } catch (e) { return {}; } };
const saveRoomPos = (name, x, y) => { try { const p = roomPos(); p[name] = {x, y}; localStorage.setItem('homeatlas.roompos', JSON.stringify(p)); } catch (e) { /* Position gilt dann nur bis zum Neuladen */ } };
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
  if (S.types) { TYPEDEF = Object.fromEntries(S.types.map(t => [t.key, t])); TYPES = Object.fromEntries(S.types.map(t => [t.key, t.label])); }
  if (load.build && S.build !== load.build && panelMode !== 'form') { location.reload(); return; }
  load.build = S.build;
  $('#title').textContent = S.settings.title || 'HomeAtlas';
  renderNavLinks();
  $('#who').textContent = S.user; $('#whorole').textContent = {read: 'Lesen', write: 'Ändern', admin: 'Admin'}[S.role] || '';
  if (!$('#crumb').textContent) $('#crumb').textContent = 'Topologie';
  document.body.classList.toggle('ro', S.role === 'read');
  document.title = S.settings.title && S.settings.title !== 'HomeAtlas' ? S.settings.title + ' · HomeAtlas' : 'HomeAtlas';
  $('#badge').textContent = S.discoveries.filter(d => d.state === 'pending').length || '';
  $('#mbadge').textContent = S.checks.filter(isProblem).length || '';
  $('#scanstate').textContent = S.scanner.running ? `Scan ${S.scanner.running} · ${S.scanner.phase}` : '';
  for (const id of [...multi]) if (!dev(id)) multi.delete(id);
  bulkBar();
  if (busy) return;
  render();
  if (sel && panelMode === 'device' && dev(sel)) showDevice(sel, true);
}
function render() {
  main.className = view === 'topo' ? 'canvas' : '';
  ({topo: renderTopo, monitor: renderMonitor, racks: renderRacks, nets: renderNets, ipam: renderIpam, types: renderTypes, finds: renderFinds, integ: renderInteg, system: renderSystem})[view]();
}
// Seitenmenü: am Desktop ein-/ausklappbar (gemerkt), am Handy als Schublade
const navStore = v => { try { if (v === undefined) return localStorage.getItem('homeatlas.nav'); localStorage.setItem('homeatlas.nav', v); } catch (e) { /* ohne Speicher gilt die Wahl bis zum Neuladen */ } return null; };
const navDrawer = open => { document.body.classList.toggle('nav-open', open); $('#shade').hidden = !open; };
function navMin(min) {
  document.body.classList.toggle('nav-min', min);
  $('#collapse').setAttribute('aria-expanded', String(!min)); $('#collapse .nl').textContent = min ? 'Ausklappen' : 'Einklappen';
}
navMin(navStore() === 'min');
$('#collapse').addEventListener('click', () => { const min = !document.body.classList.contains('nav-min'); navMin(min); navStore(min ? 'min' : 'max'); if (view === 'topo' && S) setTimeout(fitView, 190); });
$('#burger').addEventListener('click', () => navDrawer(true));
$('#shade').addEventListener('click', () => navDrawer(false));
$('#side').addEventListener('click', e => {
  const b = e.target.closest('button[data-view]'); if (!b) return;
  view = b.dataset.view;
  navDrawer(false);
  $('#crumb').textContent = $('.nl', b).textContent;
  document.querySelectorAll('#side button[data-view]').forEach(x => { x.classList.toggle('on', x === b); x.toggleAttribute('aria-current', x === b); });
  closePanel(); render(); renderIpamNav();
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
const IMG = (name, x, y, s) => `<image href="${iconUrl(name)}" x="${x}" y="${y}" width="${s}" height="${s}"/>`;
// Problem = war schon einmal erreichbar und fällt jetzt aus; „nie erreichbar“ ist ein falsches Ziel, kein Ausfall
const isProblem = c => c.enabled && c.status === 'down' && !!c.ever_up;
const isNever = c => c.enabled && c.status === 'down' && !c.ever_up;
const degraded = d => d.status === 'online' && S.checks.some(c => c.device_id === d.id && isProblem(c));
const statusDot = (d, x, y, r = 4.5) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${degraded(d) ? '#e3b341' : d.status === 'online' ? PAL.OK : d.status === 'offline' ? PAL.BAD : PAL.FAINT}"/>`;

// ------------------------------------------------------------ Topologie: Karten
// Notizen auf der Karte: Text auf die Breite umbrechen, höchstens `max` Zeilen
const memoOn = d => !!(d.memo_show && (d.memo || '').trim());
function wrapText(text, width, size, max) {
  const out = [];
  for (const para of String(text).split(/\r?\n/)) {
    let line = '';
    for (const word of para.split(/\s+/).filter(Boolean)) {
      const t = line ? line + ' ' + word : word;
      if (tw(t, size) <= width || !line) line = t; else { out.push(line); line = word; }
    }
    out.push(line);
  }
  while (out.length && !out[out.length - 1]) out.pop();
  if (out.length > max) { out.length = max; out[max - 1] = fit(out[max - 1] + ' …', width, size); if (!out[max - 1].endsWith('…')) out[max - 1] += ' …'; }
  return out.map(l => fit(l, width, size));
}
function chipH(c) {
  const g = kidsOf(c.id).length;
  return (c.ip || c.hostname ? 60 : 46) + (memoOn(c) ? 15 : 0) + (g ? g * 19 + 8 : 0);
}
function chipSvg(c, x, y, w, parentVlan) {
  const h = chipH(c), col = vcol(c.vlan_id), gk = kidsOf(c.id);
  const stroke = c.vlan_id && c.vlan_id !== parentVlan ? col : PAL.BORDER;
  const off = (vfilter && !inVlan(c, vfilter) ? ' off' : '') + (multi.has(c.id) ? ' msel' : '');
  const pr = c.meta && LK[c.meta.proto], tag = c.meta && c.meta.vmid ? (c.type === 'vm' ? 'VM ' : 'CT ') + c.meta.vmid : pr ? pr.short : '';
  const tagW = tag ? tw(tag, 10.5, 400, true) + 8 : 0;
  let s = `<g class="chip${off}" data-id="${c.id}" transform="translate(${x.toFixed(1)},${y.toFixed(1)})">` +
    `<rect class="cb" width="${w.toFixed(1)}" height="${h}" rx="8" fill="${PAL.CHIP}" stroke="${stroke}" stroke-width="1.2"/>` +
    IMG(c.icon || typeIcon(c.type), 10, 11, 22) +
    T(40, 21, fit(c.name, w - 62 - tagW, 13.5, 600), {size: 13.5, weight: 600}) +
    (tag ? T(w - 22, 20, tag, {size: 10.5, fill: pr && !(c.meta || {}).vmid ? pr.col : PAL.FAINT, mono: true, anchor: 'end'}) : '') +
    statusDot(c, w - 11, 16, 3.6) +
    T(40, 36, fit(c.note || c.os || TYPES[c.type] || '', w - 50, 11, 400), {size: 11, fill: PAL.MUTED});
  if (c.ip || c.hostname) {
    const a = c.url && c.hostname ? c.hostname : [c.ip, addrsOf(c).length ? '+' + addrsOf(c).length : '', c.hostname].filter(Boolean).join(' · ');
    s += T(40, 51, fit(a, w - 50, 11, 400, true), {size: 11, mono: true, fill: c.url && c.hostname ? PAL.LINK : col});
  }
  const my = c.ip || c.hostname ? 62 : 48;
  if (memoOn(c)) s += T(40, my + 5, fit('✎ ' + c.memo.trim().split(/\r?\n/)[0], w - 50, 10.5), {size: 10.5, fill: '#d9c58a'});
  gk.forEach((g, i) => {
    const gy = my + (memoOn(c) ? 15 : 0) + i * 19;
    const right = g.hostname || g.note || '';
    const nameW = Math.min(tw(g.name, 12, 500), w * 0.5);
    s += IMG(g.icon || typeIcon(g.type), 13, gy, 14) + T(34, gy + 11, fit(g.name, w * 0.5, 12, 500), {size: 12, weight: 500}) +
      T(w - 10, gy + 11, fit(right, w - 54 - nameW, 10.5, 400, true), {size: 10.5, mono: true, anchor: 'end',
        fill: g.url ? PAL.LINK : PAL.MUTED});
  });
  return s + '</g>';
}
function folder(w, h, tabW, stroke, dash) {
  const r = 10, t = TAB, s = 14;
  return `<path class="frame" d="M${r},0 H${tabW - s - 4} q6,0 9,5 l${s - 5},${t - 10} q3,5 9,5 H${w - r} a${r},${r} 0 0 1 ${r},${r} ` +
    `V${h - r} a${r},${r} 0 0 1 -${r},${r} H${r} a${r},${r} 0 0 1 -${r},-${r} V${r} a${r},${r} 0 0 1 ${r},-${r} z" ` +
    `fill="${dash ? '#0e141c' : PAL.PANEL}" stroke="${stroke}" stroke-width="1.6"${dash ? ' stroke-dasharray="9 6"' : ''}/>`;
}
// Größe von Hand: Bereiche und Karten mit Inhalt (Kinder oder Hardware)
const canResize = d => d.type === 'group' || kidsOf(d.id).length > 0 || ((d.meta || {}).hw || []).length + ((d.meta || {}).hw_bmc || []).length > 0;
function buildCard(d) {
  const kids = kidsOf(d.id), hw = [...((d.meta && d.meta.hw) || []), ...((d.meta && d.meta.hw_bmc) || [])];
  const trunk = S.links.some(l => l.trunk && (l.a_id === d.id || l.b_id === d.id));
  const col = vcol(d.vlan_id), stroke = trunk || !d.vlan_id ? PAL.TRUNKB : col;
  const type = TYPES[d.type] || d.type;
  const tabW = Math.round(tw(d.name, 19, 700) + tw('\u00a0·\u00a0' + type, 13, 500) + 44);
  const extra = addrsOf(d).length;
  const grp = d.type === 'group', on = kids.filter(k => k.status === 'online').length;
  let addr = grp ? '' : [d.ip, extra ? `+${extra} ${extra > 1 ? 'Adressen' : 'Adresse'}` : '', d.hostname].filter(Boolean).join(' · ');
  let l1 = grp ? (d.note || `${kids.length} ${kids.length === 1 ? 'Gerät' : 'Geräte'}`) : d.model || d.note || '';
  let l3 = grp ? (kids.length ? `${d.note ? kids.length + ' Geräte · ' : ''}${on} online` : 'noch leer – Geräte auswählen und „Gruppieren“') : d.os || (d.model ? d.note : '') || '';
  const isp = isNet(d) ? ispOf(d) : null, L = isNet(d) ? liveOf(d) : null, ispPills = [];
  if (isp) {
    const pub = (L && L.wan_ip && !L.nat) ? L.wan_ip : isp.ip || '';
    l1 = isp.provider || l1 || 'Internet';
    addr = [pub, isp.ip4 && isp.ip4 !== 'dynamic' ? IP4MODE[isp.ip4].split(' (')[0] : L && L.cgnat ? 'CGNAT' : L && L.nat ? 'hinter NAT' : ''].filter(Boolean).join(' · ') || d.ip || '';
    l3 = [isp.access && ACCESS[isp.access] ? ACCESS[isp.access][1] : '', bwTxt(isp)].filter(Boolean).join(' · ') || l3;
    if (L) ispPills.push({t: [isp.gateway, liveTxt(L)].filter(Boolean).join(' · '), c: L.status === 'down' || L.status === 'force_down' ? '#f85149' : L.status === 'none' ? '#3fb950' : '#d29922', dot: 1});
    if (isp.dyndns) ispPills.push({t: isp.dyndns, c: PAL.MUTED});
    if (isp.ip6) ispPills.push({t: 'IPv6 ' + isp.ip6, c: PAL.MUTED});
  }
  const headW = Math.max(70 + Math.max(tw(l1, 14, 500), tw(addr, 12.5, 400, true), tw(l3, 12)) + 40,
    ssidsOf(d.id).reduce((a, w) => a + tw(w.ssid, 11.5, 500, true) + 40, 0) + 2 * PAD,
    ispPills.reduce((a, p) => a + tw(p.t, 11.5, 500, true) + (p.dot ? 34 : 22), 0) + 2 * PAD);
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
  const minW = Math.ceil(Math.max(tabW + 60, headW, memoOn(d) ? 320 : 0, has ? 200 + 2 * PAD : 0));
  const own = d.meta || {}, sized = canResize(d) && own.w > 0;      // von Hand gezogene Größe (Griff unten rechts)
  let w = Math.ceil(Math.max(tabW + 60, headW, memoOn(d) ? 320 : 0, has ? cols * cw + (cols - 1) * GAP + 2 * PAD : 0));
  if (sized) {
    w = Math.max(minW, Math.round(own.w));
    if (has) cols = Math.max(1, Math.min(Math.max(n, hw.length, 1), Math.floor((w - 2 * PAD + GAP) / (200 + GAP))));
  }
  cw = (w - 2 * PAD - (cols - 1) * GAP) / cols;
  let s = T(16, 21, d.name, {size: 19, weight: 700}) + T(16 + tw(d.name, 19, 700), 21, '\u00a0·\u00a0' + type, {size: 13, weight: 500, fill: PAL.MUTED});
  s += IMG(d.icon || typeIcon(d.type), 18, TAB + 15, 38) + (grp ? '' : statusDot(d, w - 18, TAB + 20));
  s += T(70, TAB + 29, l1, {size: 14, weight: 500}) + T(70, TAB + 47, addr, {size: 12.5, mono: true, fill: d.vlan_id ? col : PAL.MUTED}) +
    T(70, TAB + 63, l3, {size: 12, fill: PAL.MUTED});
  let y = TAB + 80;
  if (ispPills.length) {
    let px = PAD;
    for (const p of ispPills) {
      const pw = tw(p.t, 11.5, 500, true) + (p.dot ? 32 : 20);
      s += `<rect x="${px}" y="${y - 2}" width="${pw.toFixed(1)}" height="22" rx="11" fill="${PAL.CHIP}" stroke="${p.c}" stroke-width="1.2"/>` +
        (p.dot ? `<circle cx="${px + 13}" cy="${y + 9}" r="3.6" fill="${p.c}"/>` : '') + T(px + (p.dot ? 23 : 10), y + 13, p.t, {size: 11.5, weight: 500, mono: true, fill: p.dot ? PAL.TEXT : p.c});
      px += pw + 6;
    }
    y += 30;
  }
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
  if (memoOn(d)) {          // Notizzettel unter dem Kopf
    const lines = wrapText(d.memo, w - 2 * PAD - 20, 11.5, 6), bh = lines.length * 15 + 12;
    s += `<rect x="${PAD}" y="${y - 2}" width="${w - 2 * PAD}" height="${bh}" rx="6" fill="#1d1a10" stroke="#5c5230"/>` +
      `<rect x="${PAD}" y="${y - 2}" width="3.5" height="${bh}" rx="1.7" fill="#d9c58a"/>` +
      lines.map((l, i) => T(PAD + 12, y + 13 + i * 15, l, {size: 11.5, fill: '#e6dcb8'})).join('');
    y += bh + 8;
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
  const minH = Math.ceil(has ? Math.max(...colY, y) + PAD - 8 : (ssids.length || ispPills.length || memoOn(d) ? y + PAD - 12 : TAB + 78));
  const h = canResize(d) && own.h > 0 ? Math.max(minH, Math.round(own.h)) : minH;
  s = folder(w, h, tabW, stroke, grp) + s;
  if (canResize(d)) s += `<g class="rz" data-rz="${d.id}"><title>Größe ziehen · Doppelklick: automatische Größe</title><rect x="${w - 30}" y="${h - 30}" width="30" height="30" fill="transparent"/>` +
    `<path d="M${w - 7},${h - 17} L${w - 17},${h - 7} M${w - 7},${h - 11} L${w - 11},${h - 7}" stroke="${own.w > 0 || own.h > 0 ? PAL.TEXT || '#e6edf3' : PAL.MUTED}" stroke-width="1.8" stroke-linecap="round" fill="none"/></g>`;
  return {id: d.id, d, w, h, minW, minH, tabW, x: d.x, y: d.y, svg: s};
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
    const k = lkOf(l), kc = lkCol(l, col);
    const netEnd = isNet(A.d) ? A.d : isNet(B.d) ? B.d : null, wi = netEnd ? ispOf(netEnd) : {};
    if (k.style === 'wan') p = ['lte', '5g', 'sat', 'wisp'].includes(wi.access)
      ? `<path class="core" d="${d}" fill="none" stroke="${kc}" stroke-width="4" stroke-dasharray="0.1 9" stroke-linecap="round" stroke-linejoin="round"/>`
      : `<path d="${d}" fill="none" stroke="${kc}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/><path class="core" d="${d}" fill="none" stroke="${PAL.BG}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`;
    else if (k.style === 'arrow') p = `<path class="core" d="${d}" fill="none" stroke="${kc}" stroke-width="1.8" stroke-dasharray="7 5" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#arr-${l.kind === 'api' ? 'api' : esc(l.kind)})"/>`;
    else if (k.style === 'radio') p = `<path class="core" d="${d}" fill="none" stroke="${kc}" stroke-width="${l.kind === 'wlan' ? 3.2 : 2.8}" stroke-dasharray="0.1 ${l.kind === 'wlan' ? 8 : 6}" stroke-linecap="round" stroke-linejoin="round"/>`;
    else if (k.style === 'bus') p = `<path class="core" d="${d}" fill="none" stroke="${kc}" stroke-width="2.2" stroke-dasharray="11 3 2 3" stroke-linejoin="round"/>`;
    else if (k.style === 'logical') p = `<path class="core" d="${d}" fill="none" stroke="${kc}" stroke-width="1.6" stroke-dasharray="${l.kind === 'logical' ? '2 6' : '9 4 2 4'}" stroke-linecap="round"/>`;
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
    const lcol = l.kind === 'cable' || !LK[l.kind] ? (l.trunk ? PAL.TRUNK : col) : kc;
    const btag = l.kind === 'wlan' ? ['WLAN', (wlan(l.wlan_id) || {}).ssid, l.note].filter(Boolean).join(' · ') : l.kind === 'logical' ? (l.note || '')
      : l.kind === 'cable' || !LK[l.kind] ? [l.speed, l.b_port].filter(Boolean).join(' · ')
      : l.kind === 'wan' ? [wi.access && ACCESS[wi.access] ? ACCESS[wi.access][1] : 'WAN', bwTxt(wi), l.note].filter(Boolean).join(' · ') : [k.short, l.note, l.b_port].filter(Boolean).join(' · ');
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
function buildRoomCard(id, name, members, pos) {
  const order = ['internet', 'router', 'firewall', 'switch', 'ap', 'hypervisor', 'server', 'nas'];
  const rank = m => { const i = order.indexOf(m.type); return i < 0 ? 99 : i; };
  members = [...members].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
  const n = members.length, on = members.filter(m => m.status === 'online').length;
  const tabW = Math.round(tw(name, 19, 700) + tw('\u00a0·\u00a0Raum', 13, 500) + 44);
  const cols = n <= 1 ? 1 : n <= 4 ? 2 : n <= 10 ? 3 : n <= 24 ? 4 : 5;
  const w = Math.ceil(Math.max(tabW + 60, 280, cols * 240 + (cols - 1) * GAP + 2 * PAD)), cw = (w - 2 * PAD - (cols - 1) * GAP) / cols;
  let s = T(16, 21, name, {size: 19, weight: 700}) + T(16 + tw(name, 19, 700), 21, '\u00a0·\u00a0Raum', {size: 13, weight: 500, fill: PAL.MUTED}) +
    T(PAD + 2, TAB + 24, `${n} ${n === 1 ? 'Gerät' : 'Geräte'} · ${on} online`, {size: 12.5, fill: PAL.MUTED});
  const colY = Array(cols).fill(TAB + 38);
  for (const m of members) { const ci = colY.indexOf(Math.min(...colY)); s += chipSvg(m, PAD + ci * (cw + GAP), colY[ci], cw, null); colY[ci] += chipH(m) + 8; }
  const h = Math.ceil(Math.max(...colY) + PAD - 8);
  return {id, d: {id, name, type: 'room'}, room: name, w, h, tabW, x: pos ? pos.x : null, y: pos ? pos.y : null, svg: folder(w, h, tabW, name === NOROOM ? PAL.TRUNKB : '#6b7c93', true) + s};
}
function buildRoomCards(tops) {
  const by = new Map();
  for (const d of tops) { const r = roomOf(d); if (!by.has(r)) by.set(r, []); by.get(r).push(d); }
  const names = [...by.keys()].sort((a, b) => (a === NOROOM) - (b === NOROOM) || a.localeCompare(b)), pos = roomPos();
  roomIds = new Map(names.map((nm, i) => [nm, -(i + 1)]));
  cards = new Map(names.map(nm => [roomIds.get(nm), buildRoomCard(roomIds.get(nm), nm, by.get(nm), pos[nm])]));
  let x = 60, y = 70, rowH = 0;                       // Räume ohne gemerkte Position: zeilenweise anordnen
  for (const c of cards.values()) {
    if (c.x != null) continue;
    if (x > 60 && x + c.w > 2500) { x = 60; y += rowH + 90; rowH = 0; }
    c.x = x; c.y = y; x += c.w + 80; rowH = Math.max(rowH, c.h);
  }
}
function toggleMulti(id) {
  if (!dev(id)) return;
  multi.has(id) ? multi.delete(id) : multi.add(id);
  document.querySelectorAll(`.card[data-id="${id}"], .chip[data-id="${id}"]`).forEach(n => n.classList.toggle('msel', multi.has(id)));
  document.querySelectorAll(`input[data-act="rowSel"][data-id="${id}"]`).forEach(n => { n.checked = multi.has(id); });
  bulkBar();
}
function bulkBar() {
  let b = $('#bulk');
  if (!multi.size || ro()) { if (b) b.remove(); return; }
  if (!b) { b = document.createElement('div'); b.id = 'bulk'; document.body.appendChild(b); }
  b.innerHTML = `<b>${multi.size} ausgewählt</b><button class="btn sm pri" data-act="bulkEdit">Ändern</button><button class="btn sm" data-act="bulkGroup">Gruppieren</button>` +
    (multi.size > 1 ? '<button class="btn sm" data-act="bulkMerge">Zusammenführen</button>' : '') +
    '<button class="btn sm bad" data-act="bulkDel">Löschen</button><button class="btn sm" data-act="bulkClear">Aufheben</button>';
}
function cardNode(c) {
  const off = vfilter && !inVlan(c.d, vfilter) && !S.devices.some(k => topOf(k.id) === c.id && inVlan(k, vfilter)) ? ' off' : '';
  return `<g class="card${off}${sel === c.id ? ' sel' : ''}${multi.has(c.id) ? ' msel' : ''}" data-id="${c.id}" transform="translate(${c.x},${c.y})">${c.svg}</g>`;
}
function renderTopo() {
  const tops = S.devices.filter(d => !d.parent_id && !PASSIVE.has(d.type));
  if (!tops.length) {
    main.className = '';
    main.innerHTML = `<div class="page"><div class="hint"><b>Noch keine Geräte.</b><br>Lege unter <b>Netzwerke</b> ein Netz an und starte einen Scan, ` +
      `füge Geräte von Hand hinzu oder importiere unter <b>System</b> eine <span class="mono">inventory.yaml</span> ` +
      `(Format von homelab-diagram).<div class="acts"><button class="btn pri" data-act="newDevice">+ Gerät</button></div></div></div>`;
    return;
  }
  if (viewMode === 'rooms') buildRoomCards(tops.flatMap(d => d.type === 'group' ? kidsOf(d.id) : [d]));
  else {
    cards = new Map(tops.map(d => [d.id, buildCard(d)]));
    if ([...cards.values()].some(c => c.x == null)) autoLayout([...cards.values()].every(c => c.x == null));
  }
  const marker = (id, c) => `<marker id="arr-${id}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="${c}"/></marker>`;
  main.innerHTML = `<svg id="svg"><defs>${Object.entries(LK).filter(([, v]) => v.style === 'arrow').map(([k, v]) => marker(k, v.col)).join('')}</defs><g id="world" class="world"><g id="links">${linksSvg()}</g>` +
    `<g id="cards">${[...cards.values()].map(cardNode).join('')}</g></g></svg>` +
    `<div id="vbar">${S.vlans.map(v => `<button class="vp${vfilter === v.id ? ' on' : ''}" style="border-left-color:${esc(v.color)}" data-act="vfilter" data-id="${v.id}">${esc(vtag(v))}${v.vid != null ? ' · ' + esc(v.name) : ''}</button>`).join('')}</div>` +
    `<div id="legend"><i style="height:8px"></i><span>10G</span><i style="height:3.8px"></i><span>2.5G</span><i style="height:2.4px"></i><span>1G</span>` +
    `<i class="tr"></i><span>Trunk (tagged)</span><i class="wl"></i><span>WLAN</span><i class="ap"></i><span>API (Pfeil = fragt ab)</span><i class="lg"></i><span>logisch</span>` +
    [...new Set([...S.links.map(l => l.kind), ...S.devices.map(d => (d.meta || {}).proto)])].filter(k => LK[k] && (LK[k].home || k === 'wan')).map(k => `<i class="lk ${LK[k].style}" style="--c:${LK[k].col}"></i><span>${esc(LK[k].short)}</span>`).join('') + '</div>' +
    `<div id="tsearch">${searchBox('topoq', '', 'Gerät suchen …')}<div id="tres" hidden></div></div>` +
    `<div id="tools"><span class="seg"><button class="btn${viewMode === 'normal' ? ' on' : ''}" data-act="viewMode" data-m="normal">Normal</button><button class="btn${viewMode === 'rooms' ? ' on' : ''}" data-act="viewMode" data-m="rooms">Räume</button></span><button class="btn" data-act="newDevice">+ Gerät</button><button class="btn" data-act="newGroup">+ Bereich</button><button class="btn${selMode ? ' pri' : ''}" data-act="selMode" title="Auch: Strg/Umschalt + Klick">${selMode ? 'Auswahl beenden' : 'Auswählen'}</button><button class="btn" data-act="relayout">Auto-Layout</button>` +
    `<button class="btn" data-act="fit">Einpassen</button><button class="btn" data-act="svgExport">SVG</button></div>`;
  if (!camSet) { fitView(); camSet = true; } else applyCam();
  bindCanvas();
  focusSel();
  $('#topoq').addEventListener('input', e => {
    const q = e.target.value, box = $('#tres');
    const hits = q.trim() ? S.devices.filter(d => match(q, d.name, d.ip, d.hostname, d.mac, d.vendor, d.model, d.note, d.room, TYPES[d.type], addrsOf(d).map(a => [a.ip, a.label, a.note].join(' ')).join(' '))).slice(0, 10) : [];
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
function resizeCard(card) {
  const node = card.node, nc = buildCard(dev(card.id));
  Object.assign(card, nc, {node});
  node.innerHTML = nc.svg;
  $('#links').innerHTML = linksSvg(); focusSel();
}
function bindCanvas() {
  const svg = $('#svg'), pts = new Map();
  let mode = null, start = null, card = null, moved = false, pinch = null;
  let lastRz = {id: 0, t: 0};
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
    const cn = e.target.closest('.card'), rz = e.target.closest('.rz');
    moved = false; start = [e.clientX, e.clientY];
    if (rz && cn && !ro() && dev(+rz.dataset.rz)) { card = cards.get(+cn.dataset.id); mode = 'size'; start.push(card.w, card.h); card.node = cn; }
    else if (cn) { card = cards.get(+cn.dataset.id); mode = 'card'; start.push(card.x, card.y); card.node = cn; card.hit = e.target; }
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
    else if (mode === 'size') {
      const d = dev(card.id);
      d.meta = {...(d.meta || {}), w: Math.max(card.minW, Math.round(start[2] + dx / cam.k)), h: Math.max(card.minH, Math.round(start[3] + dy / cam.k))};
      resizeCard(card);
    }
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
    if (mode === 'size') {
      const d = dev(card.id);
      if (d && moved) {
        const c = cards.get(d.id);        // gleich hoch wie der Inhalt = Höhe wieder automatisch
        if (d.meta.h <= c.minH + 4) d.meta.h = null;
        api('PUT', '/api/devices/' + d.id, {meta: {w: d.meta.w, h: d.meta.h}}).catch(er => toast(er.message, true));
      }
      if (d && !moved) {                  // zweimal kurz hintereinander angetippt: zurück zur automatischen Größe
        const now = Date.now();
        if (lastRz.id === d.id && now - lastRz.t < 450 && (d.meta.w || d.meta.h)) {
          d.meta = {...d.meta, w: null, h: null}; resizeCard(card);
          api('PUT', '/api/devices/' + d.id, {meta: {w: null, h: null}}).catch(er => toast(er.message, true));
        }
        lastRz = {id: d.id, t: now};
      }
      mode = null; return;
    }
    if (mode === 'card' && moved) {
      const d = dev(card.id);
      if (!d) saveRoomPos(card.room, card.x, card.y);
      else { d.x = card.x; d.y = card.y; }
      if (d && !ro()) api('POST', '/api/positions/save', [{id: card.id, x: card.x, y: card.y}]).catch(er => toast(er.message, true));
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
    `<button class="btn" data-act="editDevice" data-id="${id}">Bearbeiten</button>${d.ip ? `<button class="btn" data-act="ipamShow" data-ip="${esc(d.ip)}">IPAM</button>` : ''}<button class="btn" data-act="newLink" data-id="${id}">Verbinden</button><button class="btn" data-act="newLink" data-id="${id}" data-kind="wlan">WLAN-Verbindung</button><button class="btn" data-act="newLink" data-id="${id}" data-kind="api">API-Verbindung</button>` +
    `<button class="btn" data-act="addAddr" data-id="${id}">+ Adresse</button><button class="btn" data-act="merge" data-id="${id}">Zusammenführen</button>` +
    `<button class="btn" data-act="newDevice" data-parent="${id}">+ Kind</button>${d.type === 'group' ? `<button class="btn" data-act="groupAdd" data-id="${id}">Geräte hinzufügen</button>` : ''}` +
    `<button class="btn bad" data-act="delDevice" data-id="${id}">${d.type === 'group' ? 'Bereich auflösen' : 'Löschen'}</button></div>` +
    `<dl class="facts">${fact('IP', d.ip && `<span class="mono">${esc(d.ip)}</span>`)}${fact('Hostname', d.hostname && `<span class="mono">${esc(d.hostname)}</span>`)}` +
    fact('MAC', d.mac && `<span class="mono">${esc(d.mac)}</span>${d.vendor ? ' · ' + esc(d.vendor) : ''}`) +
    fact('Netzwerk', v && `<span style="color:${esc(v.color)}">${esc(v.vid != null ? vtag(v) + ' · ' + v.name : v.name)}</span>`) +
    fact('Raum', roomOf(d) !== NOROOM && esc(roomOf(d)) + (d.room ? '' : ' <span class="faint">(übernommen)</span>')) +
    fact('Modell', esc(d.model)) + fact('System', esc(d.os)) + fact('Beschreibung', esc(d.note)) +
    fact('Vernetzung', (d.meta || {}).proto && LK[d.meta.proto] && `<span style="color:${LK[d.meta.proto].col}">${esc(LK[d.meta.proto].label)}</span>${d.parent_id && dev(d.parent_id) ? ' über ' + esc(dev(d.parent_id).name) : ''}`) +
    fact('Rack', rack && `${esc(rack.name)} · HE ${d.rack_u}${d.rack_height > 1 ? '–' + (d.rack_u + d.rack_height - 1) : ''}`) +
    fact('Rack', !rack && shelfOf(d) && `${esc((S.racks.find(r => r.id === shelfOf(d).rack_id) || {}).name)} · auf ${esc(shelfOf(d).name)} (HE ${shelfOf(d).rack_u})`) +
    fact('Offene Ports', (d.ports || []).length ? d.ports.map(p => `<span class="pill">${p}</span>`).join(' ') : '') +
    fact('Quelle', esc({manual: 'manuell', scan: 'Scan', import: 'Import'}[d.source] || d.source)) + '</dl>' + (isNet(d) ? ispSection(d) : '');
  h += `<h3>Notizen</h3>` + ((d.memo || '').trim() ? `<div class="memo">${esc(d.memo.trim())}</div>` : '<span class="muted" style="font-size:13px">keine</span>') +
    `<div class="acts"><button class="btn sm" data-act="editMemo" data-id="${id}">${(d.memo || '').trim() ? 'Bearbeiten' : 'Notiz schreiben'}</button>` +
    ((d.memo || '').trim() ? `<button class="btn sm" data-act="memoToggle" data-id="${id}" aria-pressed="${d.memo_show ? 'true' : 'false'}">${d.memo_show ? 'Auf der Karte ausblenden' : 'Auf der Karte einblenden'}</button>` : '') + '</div>';
  if (addrsOf(d).length) {
    const sub = t => `<span class="faint" style="flex-basis:100%;font-size:12px;padding-left:17px">${t}</span>`;
    h += `<h3>Adressen (${addrsOf(d).length + 1})</h3><div class="rowl" style="flex-wrap:wrap"><span class="dot ${m.up0 === true ? 'online' : m.up0 === false ? 'offline' : d.status}"></span>` +
      `<span class="mono">${esc(d.ip || '–')}</span>${m.primary_label ? `<b>${esc(m.primary_label)}</b>` : ''}<span style="margin-left:auto;display:flex;gap:4px;align-items:center"><span class="pill" style="color:var(--text)">Hauptadresse</span>` +
      `<button class="btn sm" data-act="editPrimary" data-id="${id}" aria-label="Bezeichnung und Notiz der Hauptadresse bearbeiten">✎</button></span>` +
      (d.mac ? sub(`<span class="mono">${esc(d.mac)}</span>${d.vendor ? ' · ' + esc(d.vendor) : ''}`) : '') + (m.primary_note ? sub(esc(m.primary_note)) : '') + '</div>' +
      addrsOf(d).map((a, n) => { const av = vlan(a.vlan_id);
        return `<div class="rowl" style="flex-wrap:wrap"><span class="dot ${a.up === true ? 'online' : a.up === false ? 'offline' : ''}"></span><span class="mono">${esc(a.ip || '–')}</span>` +
          `${a.label ? `<b>${esc(a.label)}</b>` : ''}${av ? `<span style="color:${esc(av.color)};font-size:12px">${esc(av.vid != null ? vtag(av) : av.name)}</span>` : ''}` +
          `<span style="margin-left:auto;display:flex;gap:4px"><button class="btn sm" data-act="addrPrimary" data-id="${id}" data-idx="${n}" title="Zur Hauptadresse machen">Als Hauptadresse</button>` +
          `<button class="btn sm" data-act="editAddr" data-id="${id}" data-idx="${n}" aria-label="Adresse bearbeiten">✎</button>` +
          `<button class="btn sm" data-act="delAddr" data-id="${id}" data-idx="${n}" aria-label="Adresse entfernen">✕</button></span>` +
          (a.mac ? sub(`<span class="mono">${esc(a.mac)}</span>${a.vendor ? ' · ' + esc(a.vendor) : ''}`) : '') + (a.note ? sub(esc(a.note)) : '') + '</div>'; }).join('');
  }
  if (d.type === 'shelf') h += `<h3>Auf diesem Boden (${onShelf(id).length})</h3>` + (onShelf(id).map(x => `<div class="rowl"><img src="${icon(x)}" width="18" height="18" alt=""><a href="#" data-act="show" data-id="${x.id}">${esc(x.name)}</a>` +
    `<button class="btn sm" style="margin-left:auto" data-act="shelfRemove" data-id="${x.id}" aria-label="Vom Boden nehmen">✕</button></div>`).join('') || '<span class="muted">leer</span>') +
    `<div class="acts"><button class="btn sm pri" data-act="shelfAdd" data-id="${id}">Gerät daraufstellen</button></div>`;
  if (d.type === 'patchpanel') h += `<dl class="facts">${fact('Ports', String((m.ports_n) || 24))}</dl><div class="acts"><button class="btn sm" data-act="ppPorts" data-id="${id}">Portanzahl ändern</button></div>`;
  if (ssidsOf(id).length) h += `<h3>WLANs (${ssidsOf(id).length})</h3>` + ssidsOf(id).map(w => { const wv = vlan(w.vlan_id);
    return `<div class="rowl"><b class="mono">${esc(w.ssid)}</b>${wv ? `<span style="color:${esc(wv.color)};font-size:12px">${esc(wv.vid != null ? vtag(wv) + ' · ' + wv.name : wv.name)}</span>` : ''}` +
      `<span class="muted" style="margin-left:auto;font-size:12px">${esc([w.band, w.security].filter(Boolean).join(' · '))}</span><button class="btn sm" data-act="editWlan" data-id="${w.id}">✎</button></div>`; }).join('');
  if ((m.hw || []).length + (m.hw_bmc || []).length) h += '<h3>Hardware</h3>' + [...(m.hw || []), ...(m.hw_bmc || [])].map(t => `<div class="tile"><img src="${iconUrl(t.icon || 'glyph-cpu')}" alt=""><div>` +
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
  { const cs = S.checks.filter(c => c.device_id === id);
    if (cs.length || (d.ip || d.url)) h += `<h3>Überwachung${cs.length ? ` (${cs.filter(c => c.status === 'up').length}/${cs.length} in Ordnung)` : ''}</h3>` +
      cs.map(c => `<div class="rowl" style="flex-wrap:wrap"><span class="dot ${c.enabled && !isNever(c) ? MONDOT[c.status] : ''}"></span><b>${esc(c.name)}</b>` +
        `<span class="muted" style="font-size:12px">${!c.enabled ? 'pausiert' : isNever(c) ? 'noch nie erreichbar' : c.status === 'down' ? 'ausgefallen seit ' + ago(c.since) : c.status === 'up' ? (c.last_ms != null ? Math.round(c.last_ms) + ' ms' : 'ok') : 'noch kein Ergebnis'}</span>` +
        `<button class="btn sm" style="margin-left:auto" data-act="editCheck" data-id="${c.id}" aria-label="Check bearbeiten">✎</button>` +
        (c.status === 'down' && c.last_error ? `<span class="faint" style="flex-basis:100%;font-size:12px;padding-left:17px">${esc(c.last_error)}</span>` : '') + '</div>').join('') +
      `<div class="acts"><button class="btn sm" data-act="newCheck" data-dev="${id}">+ Check</button></div>`; }
  if (integ.length) h += '<h3>Anbindungen</h3>' + integ.map(i => `<div class="rowl"><b>${esc(S.kinds[i.kind].label)}</b><span class="muted">${esc(i.last_status || 'noch nicht synchronisiert')}</span>` +
    `<button class="btn sm" style="margin-left:auto" data-act="sync" data-id="${i.id}">Sync</button></div>`).join('');
  if (links.length) h += '<h3>Verbindungen</h3>' + links.map(l => {
    const o = dev(l.a_id === id ? l.b_id : l.a_id), mp = l.a_id === id ? l.a_port : l.b_port, op = l.a_id === id ? l.b_port : l.a_port;
    return `<div class="rowl">${mp ? `<span class="mono">${esc(mp)}</span><span class="muted">→</span>` : ''}<a href="#" data-act="show" data-id="${o ? o.id : 0}">${esc(o ? o.name : '?')}</a>` +
      `${op ? `<span class="mono muted">${esc(op)}</span>` : ''}<span class="pill" style="margin-left:auto${LK[l.kind] && LK[l.kind].col ? ';color:' + LK[l.kind].col : ''}">${lkOf(l).style === 'arrow' ? lkName(l, id) + (l.note ? ' · ' + esc(l.note) : '') : l.kind === 'wlan' ? 'WLAN' + (wlan(l.wlan_id) ? ' · ' + esc(wlan(l.wlan_id).ssid) : '') : l.kind === 'logical' ? 'logisch' : LK[l.kind] && l.kind !== 'cable' ? esc(lkName(l, id)) + (l.note ? ' · ' + esc(l.note) : '') : esc(l.speed) + (l.trunk ? ' · Trunk' : '')}</span>` +
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
const BUILTIN_ICONS = ['type-server', 'type-hypervisor', 'type-switch', 'type-router', 'type-firewall', 'type-nas', 'type-ap', 'type-workstation', 'type-client',
  'type-iot', 'type-light', 'type-plug', 'type-sensor', 'type-thermostat', 'type-blind', 'type-lock', 'type-vacuum', 'type-camera', 'type-speaker', 'type-tv', 'type-group', 'type-printer', 'type-vm', 'type-container', 'type-app', 'type-service', 'type-internet', 'type-patchpanel', 'type-shelf', 'type-other',
  'glyph-cpu', 'glyph-ram', 'glyph-ssd', 'glyph-hdd', 'glyph-nic', 'glyph-gpu', 'glyph-shield', 'glyph-antenna'];
function iconHelp(inp) {
  // Hilfe unter dem Icon-Feld: Vorschau, Link zur Icon-Übersicht, eingebaute Symbole zum Antippen
  const box = document.createElement('div');
  box.className = 'iconhelp';
  box.innerHTML = `<div class="ihrow"><img alt="" width="30" height="30"><span>Name aus der <a href="https://dashboardicons.com" target="_blank" rel="noopener">Icon-Übersicht (dashboardicons.com) ↗</a> eintragen (klein, mit Bindestrichen), ` +
    `z. B. <span class="mono">proxmox</span>, <span class="mono">home-assistant</span>, <span class="mono">synology</span>. Leer = Symbol nach Gerätetyp.</span></div>` +
    ((S.icons || []).length ? `<details open><summary>Eigene Icons</summary><div class="ihgrid">${S.icons.map(i => `<button type="button" data-icon="${esc(i.name)}" title="${esc(i.name)}" aria-label="${esc(i.label)}"><img src="${iconUrl(i.name)}" alt="" width="22" height="22"></button>`).join('')}</div></details>` : '') +
    `<div class="ihup"><button type="button" class="btn sm" data-up>Eigenes Icon hochladen</button><input type="file" accept=".svg,.png,.webp,.jpg,.jpeg,image/svg+xml,image/png,image/webp,image/jpeg" hidden></div>` +
    `<details><summary>Eingebaute Symbole</summary><div class="ihgrid">${BUILTIN_ICONS.map(n => `<button type="button" data-icon="${n}" title="${n}" aria-label="${n}"><img src="/api/icon/${n}" alt="" width="22" height="22"></button>`).join('')}</div></details>`;
  inp.closest('label').after(box);
  const img = $('img', box);
  const prev = () => { const v = inp.value.trim().toLowerCase(); img.style.visibility = v ? 'visible' : 'hidden'; if (v) img.src = iconUrl(v); };
  let t; inp.addEventListener('input', () => { clearTimeout(t); t = setTimeout(prev, 400); });
  box.addEventListener('click', e => {
    const b = e.target.closest('[data-icon]'); if (b) { inp.value = b.dataset.icon; prev(); return; }
    if (e.target.closest('[data-up]')) $('input[type=file]', box).click();
  });
  $('input[type=file]', box).addEventListener('change', async e => {
    const f = e.target.files[0]; if (!f) return;
    try { const r = await uploadIcon(f); await load(true); inp.value = r.name; prev(); toast(`Icon „${r.name}“ hochgeladen und gesetzt`); }
    catch (er) { toast(er.message, true); }
    e.target.value = '';
  });
  inp.setAttribute('autocapitalize', 'none'); inp.setAttribute('spellcheck', 'false');
  prev();
}
function openForm(title, fields, val, onSave, extra, keepSel) {
  if (ro()) return;
  navBack = false; ipamBack = null;
  if (!keepSel) sel = null;
  openPanel(formHtml(title, fields, val, extra), 'form');
  if ($('[name=memo]', panel)) $('[name=memo]', panel).rows = 6;
  panel.querySelectorAll('form select').forEach(comboize);
  if ($('[name=icon]', panel)) iconHelp($('[name=icon]', panel));
  if ($('[name=room]', panel)) {   // vorhandene Räume als Vorschlagsliste
    $('[name=room]', panel).setAttribute('list', 'roomlist');
    $('form', panel).insertAdjacentHTML('beforeend', `<datalist id="roomlist">${allRooms().map(r => `<option value="${esc(r)}">`).join('')}</datalist>`);
  }
  $('form', panel).addEventListener('submit', e => {
    e.preventDefault();
    const data = {};
    for (const el of e.target.elements) if (el.name) data[el.name] = el.multiple ? [...el.selectedOptions].map(o => (o.value !== '' && !isNaN(+o.value) ? +o.value : o.value)) : el.type === 'checkbox' ? (el.checked ? 1 : 0) : el.value.trim();
    run(async () => { await onSave(data); if (sel) panelMode = 'device'; else closePanel(); }, 'Gespeichert');
  });
}
const vlanOpts = () => [['', '– keins –'], ...S.vlans.map(v => [v.id, v.vid != null ? `${vtag(v)} · ${v.name}` : v.name])];
const devOpts = (skip) => [['', '– keins –'], ...S.devices.filter(d => d.id !== skip && !['app', 'service'].includes(d.type) && !PASSIVE.has(d.type)).map(d => [d.id, d.name])];
function deviceForm(d) {
  const isNew = !d.id;
  openForm(isNew ? 'Neues Gerät' : esc(d.name), [
    ['name', 'Name'], [['type', 'Typ', 'select', typeOpts(d.type)], ['vlan_id', 'Netzwerk', 'select', vlanOpts()]],
    [['ip', 'IP-Adresse'], ['mac', 'MAC-Adresse']], [['hostname', 'Hostname'], ['url', 'Web-URL']],
    [['model', 'Modell'], ['os', 'System']], ['room', 'Raum', 'text', 'z. B. Wohnzimmer, Keller'], ['icon', 'Icon'],
    [['parent_id', 'Läuft auf / gehört zu', 'select', devOpts(d.id)], ['proto', 'Vernetzung (Smarthome)', 'select', [['', '– keine Angabe –'], ...Object.entries(LK).filter(([, v]) => v.home).map(([k, v]) => [k, v.label])]]],
    ['note', 'Kurzbeschreibung (eine Zeile auf der Karte)'],
    ['memo', 'Notizen', 'area'], ['memo_show', 'Notizen auf der Karte anzeigen', 'check'],
    [['rack_id', 'Rack', 'select', [['', '– keins –'], ...S.racks.map(r => [r.id, r.name])]], ['rack_u', 'unterste HE', 'number']],
    ['rack_height', 'Höhe in HE', 'number'],
  ], {...d, proto: (d.meta || {}).proto || ''}, async data => {
    if (!data.name) throw new Error('Name fehlt');
    if (data.rack_id && !data.rack_u) data.rack_u = 1;
    data.meta = {proto: data.proto || null}; delete data.proto;
    if (isNew) { const r = await api('POST', '/api/devices', data); sel = r.id; } else { await api('PUT', '/api/devices/' + d.id, data); sel = d.id; }
  }, '', true);
}
function linkForm(l) {
  const isNew = !l.id;
  openForm(isNew ? 'Neue Verbindung' : 'Verbindung', [
    [['a_id', 'Von (bei API: fragt ab)', 'select', devOpts().slice(1)], ['a_port', 'Port']], [['b_id', 'Nach (bei API: wird abgefragt)', 'select', devOpts().slice(1)], ['b_port', 'Port']],
    [['speed', 'Geschwindigkeit', 'select', Object.keys(SPEED_W).map(s => [s, s])], ['kind', 'Art', 'select', KINDS]],
    ['wlan_id', 'WLAN / SSID (nur bei Art „WLAN“)', 'select', [['', '– keins –'], ...S.wlans.map(w => [w.id, w.ssid])]],
    ['vlan_id', 'Access-VLAN', 'select', vlanOpts()], ['trunk', 'Trunk (mehrere getaggte VLANs)', 'check'], ['note', 'Notiz'],
  ], {kind: 'cable', ...l}, async data => {
    const k = lkOf(data);
    if (k.style !== 'line') { data.trunk = 0; if (data.kind !== 'logical') data.vlan_id = null; }
    if (data.kind !== 'wlan') data.wlan_id = null;
    if (isNew) await api('POST', '/api/links', data); else await api('PUT', '/api/links/' + l.id, data);
  }, isNew ? '' : `<button class="btn bad" type="button" data-act="delLink" data-id="${l.id}">Löschen</button>`, true);
  const f = $('form', panel), lab = n => { const x = $(`[name=${n}]`, f); return x && x.closest('label'); };
  const NOTE = {api: 'Protokoll, z. B. REST :8006, SNMP', mqtt: 'Topic oder Broker, z. B. zigbee2mqtt/#', zigbee: 'z. B. Kanal 15, Router/Endgerät', zwave: 'z. B. Node-ID',
    thread: 'z. B. Border Router, Netzwerkname', wan: 'z. B. Modem/ONT, Leitungs-ID, PPPoE', matter: 'z. B. Fabric, über Thread/WLAN', ble: 'z. B. Proxy, Reichweite', ir: 'z. B. Fernbedienungscode', usb: 'z. B. /dev/ttyUSB0', bus: 'z. B. Adresse, Baudrate'};
  const sync = () => {
    const kind = $('[name=kind]', f).value, k = LK[kind] || LK.cable, wire = k.style === 'line';
    for (const n of ['speed', 'trunk']) { const x = lab(n); if (x) x.hidden = !wire; }
    if (lab('vlan_id')) lab('vlan_id').hidden = !wire && kind !== 'logical';
    if (lab('wlan_id')) lab('wlan_id').hidden = kind !== 'wlan';
    for (const n of ['a_port', 'b_port']) { const x = lab(n); if (x) x.hidden = !(wire || k.style === 'bus' || kind === 'api'); }
    const a = lab('a_id'), b = lab('b_id');
    if (a) a.firstChild.textContent = k.style === 'arrow' ? (kind === 'mqtt' ? 'Von (sendet/abonniert)' : 'Von (fragt ab)') : k.home && k.style === 'radio' ? 'Von (Gerät)' : 'Von';
    if (b) b.firstChild.textContent = k.style === 'arrow' ? (kind === 'mqtt' ? 'Nach (Broker)' : 'Nach (wird abgefragt)') : k.home && k.style === 'radio' ? 'Nach (Bridge, Hub, Koordinator)' : 'Nach';
    const nt = $('[name=note]', f); if (nt) nt.placeholder = NOTE[kind] || '';
  };
  $('[name=kind]', f).addEventListener('change', sync); sync();
}
function showLink(id) { const l = S.links.find(x => x.id === id); if (l) linkForm(l); }

// ------------------------------------------------------------ Racks
const UH = 28;
function rackBlock(d, r) {
  const hh = d.rack_height || 1, pos = `top:${(r.units - (d.rack_u + hh - 1)) * UH + 1}px;height:${hh * UH - 2}px`;
  if (d.type === 'patchpanel') {
    const n = Math.min(96, Math.max(0, +(d.meta || {}).ports_n || 24)), perRow = hh > 1 && n > 24 ? Math.ceil(n / 2) : n;
    return `<div class="rdev ph pp" data-id="${d.id}" style="${pos}" title="${esc(d.name)} · ${n} Ports"><b>${esc(d.name)}</b>` +
      `<span class="pports" style="grid-template-columns:repeat(${perRow},1fr)">${'<i></i>'.repeat(n)}</span></div>`;
  }
  if (d.type === 'shelf') {
    const on = onShelf(d.id);
    return `<div class="rdev ph sh" data-id="${d.id}" style="${pos}"><b>${esc(d.name)}</b><span class="ip">${on.length ? esc(on.map(x => x.name).join(' · ')) : 'leer'}</span></div>`;
  }
  if (PASSIVE.has(d.type)) return `<div class="rdev ph ${d.type === 'blank' ? 'bl' : 'cm'}" data-id="${d.id}" style="${pos}"><b>${esc(d.name)}</b></div>`;
  return `<div class="rdev" data-id="${d.id}" style="--c:${esc(vcol(d.vlan_id))};${pos}">` +
    `<img src="${icon(d)}" alt=""><span class="dot ${d.status}"></span><b>${esc(d.name)}</b><span class="ip">${esc(d.ip || d.model || '')}</span></div>`;
}
function renderRacks() {
  const free = S.devices.filter(d => !d.parent_id && !d.rack_id && !shelfOf(d) && !['internet', 'client', 'iot', 'workstation', 'group', 'light', 'plug', 'sensor', 'thermostat', 'blind', 'lock', 'vacuum', 'camera', 'speaker', 'tv', 'smartphone', 'tablet'].includes(bt(d.type)));
  let h = `<div class="page" style="max-width:none"><div class="bar"><h2>Racks</h2><button class="btn pri" data-act="newRack">+ Rack</button>` +
    `<span class="muted">Ziehen verschiebt · freie Höheneinheit antippen zum Einbauen von Geräten, Patchpanels, Rackböden und Blenden</span></div>`;
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
      `<div class="rbody" data-rack="${r.id}" data-units="${r.units}" style="height:${r.units * UH + 4}px">${rows}${ds.map(d => rackBlock(d, r)).join('')}</div></div>`;
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
    const free = S.devices.filter(d => !d.parent_id && !d.rack_id && !shelfOf(d) && d.type !== 'group');
    // Erst die Art wählen (ohne Vorauswahl), dann erscheinen nur die dazu passenden Felder
    const WHAT = [['', '– bitte wählen –'], ...(free.length ? [['device', 'Vorhandenes Gerät']] : []), ['patchpanel', 'Patchpanel'], ['shelf', 'Rackboden'],
      ['blank', 'Blende'], ['cablemgmt', 'Kabelführung']];
    openForm(`Einbauen in HE ${u}`, [['what', 'Was soll hier rein?', 'select', WHAT], ['id', 'Gerät', 'select', free.map(d => [d.id, d.name])],
      ['pname', 'Bezeichnung', 'text', 'z. B. Patchpanel EG'], ['ports_n', 'Anzahl Ports', 'number'], ['rack_height', 'Höhe in HE', 'number']],
      {rack_height: 1, ports_n: 24, what: ''},
      async data => {
        if (!data.what) throw new Error('Bitte erst wählen, was eingebaut wird');
        const hh = Math.max(1, +data.rack_height || 1);
        if (u + hh - 1 > units || occupied(u, hh)) throw new Error('Dort ist nicht genug Platz');
        if (data.what === 'device') await api('PUT', '/api/devices/' + data.id, {rack_id: rid, rack_u: u, rack_height: hh});
        else await api('POST', '/api/devices', {name: data.pname || TYPES[data.what], type: data.what, rack_id: rid, rack_u: u, rack_height: hh,
          meta: data.what === 'patchpanel' ? {ports_n: Math.min(96, Math.max(1, +data.ports_n || 24))} : {}});
      });
    const f = n => $(`[name=${n}]`, panel), show = (n, on) => { f(n).closest('label').hidden = !on; };
    const sync = () => { const w = f('what').value; show('id', w === 'device'); show('pname', w && w !== 'device'); show('ports_n', w === 'patchpanel'); show('rack_height', !!w); };
    f('what').addEventListener('change', sync); sync();
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
    const base = {id: d.id, name: d.name, type: TYPES[d.type] || d.type, hostname: d.hostname || '', room: roomOf(d) === NOROOM ? '' : roomOf(d)};
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
    match(netQ, r.ip, r.name, r.hostname, r.type, r.room, r.mac, r.vendor, STATUS[r.status], (vlan(r.vlan_id) || {}).name, vtag(vlan(r.vlan_id))))
    .sort((a, b) => { const x = key(a), y = key(b); return (x < y ? -1 : x > y ? 1 : 0) * netSort.dir; });
}
function netTable() {
  const rows = netFiltered(), cols = [['status', 'Status'], ['ip', 'IP-Adresse'], ['name', 'Gerät'], ['hostname', 'Hostname'], ['type', 'Typ'], ['room', 'Raum'], ['mac', 'MAC'],
    ['vendor', 'Hersteller'], ['vlan', 'Netzwerk'], ['seen', 'Zuletzt gesehen']];
  return `<div class="muted" style="font-size:12.5px;margin-bottom:8px">${rows.length} ${rows.length === 1 ? 'Adresse' : 'Adressen'}</div><div class="tscroll"><table class="t sortable"><tr><th style="width:28px"><input type="checkbox" data-act="rowAll" aria-label="Alle auswählen"></th>` +
    cols.map(([k, l]) => `<th data-act="netSort" data-k="${k}" aria-sort="${netSort.k === k ? (netSort.dir > 0 ? 'ascending' : 'descending') : 'none'}">${l}${netSort.k === k ? (netSort.dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>' +
    (rows.map(r => { const v = vlan(r.vlan_id);
      return `<tr class="clk" ${r.find ? 'data-act="goFinds"' : `data-act="show" data-id="${r.id}"`}><td>${r.find ? '' : `<input type="checkbox" data-act="rowSel" data-id="${r.id}"${multi.has(r.id) ? ' checked' : ''} aria-label="${esc(r.name)} auswählen">`}</td><td><span class="dot ${r.status === 'pending' ? 'pending' : r.status}"></span> ${STATUS[r.status]}</td>` +
        `<td class="mono">${esc(r.ip)}</td><td>${r.find ? '<span class="muted">– noch nicht dokumentiert –</span>' : `<b>${esc(r.name)}</b>`}</td><td class="mono">${esc(r.hostname)}</td><td>${esc(r.type)}</td><td>${esc(r.room || '')}</td>` +
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
  const isNew = !w.id, aps = S.devices.filter(d => !['app', 'service', 'internet', 'container', 'vm', 'client', 'smartphone', 'tablet'].includes(bt(d.type)))
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
function vlanForm(v, after) {
  const isNew = !v.id;
  openForm(isNew ? 'Neues Netzwerk' : esc(v.name), [
    [['name', 'Name'], ['vid', 'VLAN-ID (leer = untagged)', 'number']], [['subnet', 'Subnetz (CIDR)', 'text', '192.168.178.0/24'], ['gateway', 'Gateway']],
    [['color', 'Farbe', 'color'], ['scan', 'Automatisch scannen', 'check']], ['note', 'Regel / Notiz'],
  ], isNew ? {color: '#58a6ff', scan: 1, ...v} : v, async data => {
    if (!data.name) throw new Error('Name fehlt');
    if (isNew) await api('POST', '/api/vlans', data); else await api('PUT', '/api/vlans/' + v.id, data);
    if (after) setTimeout(after, 0);
  }, isNew ? '' : `<button class="btn bad" type="button" data-act="delVlan" data-id="${v.id}">Löschen</button>`);
}

// ------------------------------------------------------------ Funde
function renderFinds() {
  const pend = S.discoveries.filter(d => d.state === 'pending'), ign = S.discoveries.filter(d => d.state === 'ignored');
  const card = d => {
    const g = d.guess || {}, v = vlan(d.vlan_id), titles = Object.entries(d.http || {}).filter(([, x]) => x.title).map(([p, x]) => `${p}: ${x.title}`);
    return `<div class="box find"><div class="hd"><img src="${iconUrl(g.icon || typeIcon(g.type || 'other'))}" width="26" height="26" alt="">` +
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

// ------------------------------------------------------------ Überwachung
const MONDOT = {up: 'online', down: 'offline', unknown: ''};
const KINDS_CHECK = {ping: 'Ping', tcp: 'TCP-Port', http: 'HTTP'};
let MON = null, monQ = '', monOpen = new Set();
function monBars(c) {
  const pad = Array(Math.max(0, 30 - c.last30.length)).fill(null), n = c.last30.length, bad = c.last30.filter(x => !x).length;
  return `<span class="bars" role="img" aria-label="${n ? `${n - bad} von ${n} letzten Prüfungen erfolgreich` : 'noch keine Prüfung'}">` +
    [...pad, ...c.last30].map(x => `<i class="${x == null ? '' : x ? 'ok' : 'bad'}"></i>`).join('') + '</span>';
}
function monRow(c) {
  const pct = c.up24 == null ? '' : (c.up24 === 100 ? '100' : c.up24.toFixed(1)) + ' %';
  return `<div class="mrow${c.enabled ? '' : ' paused'}" data-act="editCheck" data-id="${c.id}"><span class="dot ${c.enabled && !isNever(c) ? MONDOT[c.status] : ''}"></span>` +
    `<span class="mname"><b>${esc(c.device || c.name)}</b>${c.device ? ` <span class="muted">${esc(c.name)}</span>` : ''}</span>${monBars(c)}` +
    `<span class="mms mono">${!c.enabled ? 'Pause' : c.status === 'up' && c.last_ms != null ? Math.round(c.last_ms) + ' ms' : isNever(c) ? 'nie' : c.status === 'down' ? 'aus' : '–'}</span><span class="mpct mono" title="Verfügbarkeit in den letzten 24 Stunden">${pct}</span></div>`;
}
function monBody() {
  if (!MON) return '<div class="hint">lädt …</div>';
  const all = MON.checks, on = all.filter(c => c.enabled), down = on.filter(isProblem), never = on.filter(isNever), wait = on.filter(c => c.status === 'unknown');
  if (!all.length) return `<div class="hint"><b>Noch keine Überwachung.</b><br>HomeAtlas kann aus der Dokumentation Checks ableiten: einen Ping je Gerät mit IP, ` +
    `einen Port-Check je bekanntem Dienst (SSH, Proxmox, SMB …) und einen HTTP-Check je Weboberfläche.` +
    `<div class="acts"><button class="btn pri" data-act="genChecks">Aus Dokumentation erzeugen</button><button class="btn" data-act="newCheck">+ Check von Hand</button></div></div>`;
  const f = c => match(monQ, c.device, c.name, c.target, c.port, KINDS_CHECK[c.kind], MON.areas[c.area], c.status === 'down' ? 'ausgefallen problem' : '');
  let h = `<div class="mbanner ${down.length ? 'bad' : 'ok'}"><span class="dot ${down.length ? 'offline' : 'online'}"></span><b>${down.length ? `${down.length} ${down.length === 1 ? 'Problem' : 'Probleme'}` : 'Alles in Ordnung'}</b>` +
    `<span class="muted">${on.length - down.length - never.length - wait.length} von ${on.length} Checks in Ordnung${wait.length ? ` · ${wait.length} noch ohne Ergebnis` : ''}${all.length - on.length ? ` · ${all.length - on.length} pausiert` : ''}` +
    ` · Benachrichtigung ${MON.notify ? 'aktiv' : 'aus'}</span></div>` +
    (never.length ? `<div class="hint" style="margin:8px 0 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap"><span><b>${never.length} ${never.length === 1 ? 'Check war' : 'Checks waren'} noch nie erreichbar.</b> Das ist meist ein falsches Ziel oder ein Dienst, den es dort nicht gibt – kein Ausfall, deshalb auch keine Meldung.</span>` +
      `<button class="btn sm" data-act="delNever">Diese ${never.length} entfernen</button></div>` : '');
  if (down.filter(f).length) h += `<h3 class="faint">Was ist los</h3><div class="box mprob">` + down.filter(f).sort((a, b) => (a.since || 0) - (b.since || 0)).map(c =>
    `<div class="mrow" data-act="${c.device_id ? 'show' : 'editCheck'}" data-id="${c.device_id || c.id}"><span class="dot offline"></span><span class="mname"><b>${esc(c.device || c.name)}</b>` +
    `${c.device ? ` <span class="muted">${esc(c.name)}</span>` : ''}<br><span class="faint" style="font-size:12px">${esc(c.last_error || 'ausgefallen')}</span></span>` +
    `<span class="mms" style="width:auto;color:#ffb4ae">seit ${ago(c.since)}</span></div>`).join('') + '</div>';
  h += '<h3 class="faint">Bereiche</h3><div class="cards">';
  for (const [key, name] of Object.entries(MON.areas)) {
    const cs = all.filter(c => c.area === key), act = cs.filter(c => c.enabled && !isNever(c)), bad = act.filter(isProblem).length, known = act.filter(c => c.status !== 'unknown').length;
    if (!cs.length) continue;
    const shown = cs.filter(f).sort((a, b) => isProblem(b) - isProblem(a) || isNever(a) - isNever(b) || String(a.device).localeCompare(String(b.device)) || a.id - b.id);
    if (monQ.trim() && !shown.length) continue;
    const st = !known ? ['', 'noch keine Ergebnisse'] : !bad ? ['online', 'in Ordnung'] : bad === act.length ? ['offline', 'ausgefallen'] : ['warn', 'beeinträchtigt'];
    const open = monOpen.has(key) || monQ.trim() || shown.length <= 8, list = open ? shown : shown.slice(0, Math.max(6, bad));
    h += `<div class="box marea"><div class="mhead"><span class="dot ${st[0]}"></span><b>${esc(name)}</b><span class="muted">${st[1]}</span><span class="mono muted" style="margin-left:auto">${act.length - bad}/${act.length}</span></div>` +
      list.map(monRow).join('') + (shown.length > list.length ? `<button class="btn sm" style="margin-top:8px" data-act="monArea" data-k="${key}">alle ${shown.length} anzeigen</button>` : '') + '</div>';
  }
  h += '</div><h3 class="faint" style="margin-top:26px">Diese Woche</h3>';
  if (!MON.events.length) h += '<div class="hint">Keine Ausfälle in den letzten sieben Tagen.</div>';
  else {
    const day = t => new Date(t * 1000).toLocaleDateString('de-DE', {weekday: 'long', day: 'numeric', month: 'long'});
    let last = '';
    h += '<div class="box">' + MON.events.map(e => { const d = day(e.ts), head = d !== last ? `<div class="mday">${d}</div>` : ''; last = d;
      return head + `<div class="rowl"><span class="dot ${e.kind === 'up' ? 'online' : 'offline'}"></span><span class="mono muted" style="font-size:12px">${new Date(e.ts * 1000).toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'})}</span>` +
        `${e.device_id && dev(e.device_id) ? `<a href="#" data-act="show" data-id="${e.device_id}">${esc(e.text)}</a>` : esc(e.text)}</div>`; }).join('') + '</div>';
  }
  return h;
}
async function renderMonitor() {
  if (!$('#monbody')) {
    main.innerHTML = `<div class="page"><div class="bar"><h2>Überwachung</h2><button class="btn pri" data-act="genChecks">Aus Dokumentation erzeugen</button>` +
      `<button class="btn" data-act="newCheck">+ Check</button><a class="btn" href="/api/monitor/gatus.yaml" download title="Die Checks als Konfiguration für Gatus">Gatus-Export</a></div>` +
      `<div class="bar">${searchBox('monq', monQ, 'Suchen: Gerät, Check, Bereich …')}</div><div id="monbody">${monBody()}</div></div>`;
    $('#monq').addEventListener('input', e => { monQ = e.target.value; $('#monbody').innerHTML = monBody(); });
  }
  try { MON = await api('GET', '/api/monitor/overview'); } catch (e) { return; }
  if (view === 'monitor' && $('#monbody')) $('#monbody').innerHTML = monBody();
}
function checkForm(c) {
  const isNew = !c.id;
  openForm(isNew ? 'Neuer Check' : esc((c.device ? c.device + ' · ' : '') + c.name), [
    ['device_id', 'Gehört zu Gerät', 'select', devOpts()], ['kind', 'Prüfart', 'select', Object.entries(KINDS_CHECK)],
    ['target', 'Ziel (IP, Hostname oder bei HTTP die ganze Adresse)'], ['port', 'Port', 'number'], ['name', 'Bezeichnung (leer = automatisch)'],
    ['interval_s', 'Intervall in Sekunden (mindestens 15)', 'number'], ['enabled', 'Aktiv (abgewählt = pausiert)', 'check'],
  ], c, async data => { if (isNew) await api('POST', '/api/monitor/checks', data); else await api('PUT', '/api/monitor/checks/' + c.id, data); MON = null; },
  isNew ? '' : `<button class="btn" type="button" data-act="runCheck" data-id="${c.id}">Jetzt prüfen</button><button class="btn bad" type="button" data-act="delCheck" data-id="${c.id}">Löschen</button>` +
    (c.status === 'down' && c.last_error ? `<p class="muted" style="flex-basis:100%;font-size:12.5px;margin:6px 0 0">Letzter Fehler: ${esc(c.last_error)}</p>` : ''), !!sel);
  const f = n => $(`[name=${n}]`, panel), sync = () => { f('port').closest('label').hidden = f('kind').value !== 'tcp'; };
  f('kind').addEventListener('change', sync); sync();
  f('device_id').addEventListener('change', () => { const d = dev(+f('device_id').value); if (d && !f('target').value) f('target').value = f('kind').value === 'http' ? (d.url || '') : (d.ip || d.hostname || ''); });
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
      return `<div class="box"><div class="rowl" style="border:0;padding:0"><b>${esc(S.kinds[i.kind].label)}</b><span class="muted">${esc(i.name || i.config.host || i.config.url || (i.kind === 'docker' ? 'lokaler Docker' : '') || '')}</span>` +
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
const isLocal = ip => !!ip && ((S.local || {}).ips || []).includes(ip);
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
  const avail = (i.config || {})._available;   // Home Assistant: nach dem ersten Abruf die Integrationen zur Auswahl
  if (avail) {
    fields.splice(fields.length - 2, 0, ['c_integrations', 'Integrationen übernehmen (Mehrfachauswahl)', 'multi', Object.entries(avail).map(([n, cnt]) => [n, `${n} (${cnt})`])]);
    val.c_integrations = (i.config || {}).integrations || [];
  }
  for (const [key, , ph] of k.fields) val['c_' + key] = (i.config || {})[key] ?? ph ?? '';
  openForm((isNew ? 'Neu: ' : '') + esc(k.label), fields, val, async data => {
    const body = {kind: i.kind, name: data.name, device_id: data.device_id, enabled: data.enabled, config: {}};
    for (const key in data) if (key.startsWith('c_')) body.config[key.slice(2)] = data[key];
    if ((data.pick || '').startsWith('f:')) body.device_id = (await api('POST', `/api/discoveries/${data.pick.slice(2)}/approve`)).ids[0];   // Fund wird dabei übernommen
    const id = isNew ? (await api('POST', '/api/integrations', body)).id : (await api('PUT', '/api/integrations/' + i.id, body), i.id);
    const r = await api('POST', `/api/integrations/${id}/sync`);
    setTimeout(() => toast(r.status, r.status.startsWith('Fehler')), 50);
  }, k.help ? `<div class="hint" style="margin-top:12px;font-size:12.5px">${esc(k.help)}</div>` : '', !!i.device_id && sel === i.device_id);
  const pick = $('[name=pick]', panel);
  if (pick) pick.addEventListener('change', () => {
    const c = cands.find(x => x.v === pick.value), f = n => $(`[name=${n}]`, panel);
    if (!c) return;
    if (f('c_host')) f('c_host').value = i.kind === 'homeassistant' ? `http://${c.ip}:8123` : c.ip;
    if (f('c_url')) f('c_url').value = isLocal(c.ip) ? '' : `http://${c.ip}:2375`;   // HomeAtlas-Host selbst: über den Docker-Socket
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
    `<div class="acts" style="margin:0"><button class="btn">Passwort ändern</button></div></form></div>` +
    `<h3 class="faint" style="margin-top:24px">Gerätetypen &amp; Icons</h3><div class="box tsys"><div class="tprev">${S.types.filter(t => !t.hidden && !PASSIVE.has(t.key)).slice(0, 14).map(t => `<img src="${iconUrl(typeIcon(t.key))}" alt="" width="22" height="22" title="${esc(t.label)}">`).join('')}</div>` +
    `<p class="muted" style="margin:8px 0 12px;font-size:12.5px">${S.types.length} Typen, davon ${S.types.filter(t => t.custom).length} eigene · ${(S.icons || []).length} eigene Icons. Bezeichnung, Icon, Bereich und Erkennung anpassen, eigene Typen anlegen, Icons hochladen.</p>` +
    `<button class="btn" data-act="goTypes">Typen &amp; Icons verwalten</button></div>`;
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
    `<label>Benachrichtigung bei Ausfall: ntfy-Adresse oder Webhook (leer = aus)<input name="notify_url" value="${esc(s.notify_url || '')}" placeholder="https://ntfy.sh/mein-thema" autocomplete="off"></label>` +
    `<div class="acts" style="margin:0"><button class="btn pri">Speichern</button><button class="btn" type="button" data-act="testNotify">Testmeldung senden</button></div></form></div>` +
    `<h3 class="faint" style="margin-top:24px">Daten</h3><div class="box"><div class="acts" style="margin:0"><a class="btn" href="/api/export" download>Export (JSON)</a>` +
    `<button class="btn" data-act="pick" data-kind="restore">Export wiederherstellen</button><button class="btn" data-act="pick" data-kind="inventory">inventory.yaml importieren</button></div>` +
    `<p class="muted" style="margin:10px 0 0;font-size:12.5px">Der Export enthält die Zugangsdaten der Anbindungen. Der YAML-Import liest das Format von Goblinmine/homelab-diagram und legt die Einträge zusätzlich an. Wiederherstellen ersetzt alle Daten.</p></div>`;
  else if (S.role === 'write') h += `<h3 class="faint" style="margin-top:24px">Daten</h3><div class="box"><button class="btn" data-act="pick" data-kind="inventory">inventory.yaml importieren</button></div>`;
  main.innerHTML = h + `<p class="faint" style="font-size:12px;margin-top:18px">${S.devices.length} Geräte · ${S.links.length} Verbindungen · ${S.vlans.length} Netzwerke · ${S.racks.length} Racks<br><span class="mono">HomeAtlas ${esc(S.version)} · Build ${esc(S.build)}</span></p></div>`;
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
  close: () => { navBack = false; closePanel(); },
  ipamTab: d => { ipamTab = d.t; renderIpam(true); },
  ipamNet: d => { ipamNet = d.v === 'all' ? 'all' : +d.v; navDrawer(false); renderIpam(true); main.scrollTop = 0; },
  ipamMove: d => { const x = dev(+d.id); if (x && confirm(`${x.name}: Adresse von ${x.ip} auf ${d.ip} ändern?`)) run(async () => { await api('PUT', '/api/devices/' + x.id, {ip: d.ip}); await load(true); await loadIpam(false); }, 'Adresse übernommen'); },
  ipamNewNet: d => vlanForm({subnet: d.net, gateway: d.net.replace(/\.0\/24$/, '.1'), name: d.intf || ''}, async () => { await load(true); await loadIpam(true); }),
  ipamRefresh: () => { loadIpam(true); renderIpam(true); },
  ipamDnsFilter: d => { ipamDnsFilter = d.f; renderIpam(true); },
  ipamCellOpen: d => { if (view !== 'ipam') return; const [s] = ipamCell(d.ip); if (s && s.vlan_id !== ipamNet && ipamTab === 'addr') { ipamNet = s.vlan_id; renderIpam(true); } ipamCellPanel(d.ip); },
  ipamCopy: d => { (navigator.clipboard ? navigator.clipboard.writeText(d.v) : Promise.reject()).then(() => toast(d.v + ' kopiert'), () => toast(d.v)); },
  ipamPick: (d, el) => { const id = +d.id; el.checked ? ipamPick.add(id) : ipamPick.delete(id); renderIpam(true); },
  ipamPickAll: (d, el) => { if (el.checked) main.querySelectorAll('[data-act=ipamPick]').forEach(n => ipamPick.add(+n.dataset.id)); else ipamPick.clear(); renderIpam(true); },
  ipamDomSave: () => { const v = (ipamNames._dom ?? IPAM.domain).trim(); api('POST', '/api/settings/save', {dns_domain: v}).then(() => { IPAM.domain = v; toast('Domain gespeichert'); }, er => toast(er.message, true)); },
  ipamDnsAdd: () => {
    const dom = (ipamNames._dom ?? IPAM.domain).trim(), items = IPAM.missing.filter(m => ipamPick.has(m.id)).map(m => ({hostname: ipamSlug(ipamNames[m.id] ?? m.suggest), domain: dom, ip: m.ip, description: 'HomeAtlas: ' + m.name}));
    if (!items.length) return;
    if (!confirm(`${items.length} DNS-Einträge in ${SRC[IPAM.dns_target]} anlegen?\n\n` + items.slice(0, 12).map(i => `${i.hostname}${dom ? '.' + dom : ''} → ${i.ip}`).join('\n') + (items.length > 12 ? '\n…' : ''))) return;
    ipamWrite('/api/ipam/dns', {op: 'add', items}, `${items.length} DNS-Einträge angelegt`).then(ok => { if (ok) ipamPick.clear(); });
  },
  ipamDnsSet: d => { if (confirm(`DNS-Eintrag auf ${d.ip} ändern?`)) ipamWrite('/api/ipam/dns', {op: 'set', uuid: d.u, ip: d.ip}, 'DNS-Eintrag geändert'); },
  ipamDnsDel: d => { if (confirm(`DNS-Eintrag „${d.n}“ in der OPNsense löschen?`)) ipamWrite('/api/ipam/dns', {op: 'del', uuid: d.u}, 'DNS-Eintrag gelöscht'); },
  ipamDnsOne: d => {
    const [, c] = ipamCell(d.ip), back = () => ipamCellPanel(d.ip);
    openForm('DNS-Eintrag für ' + esc(d.ip), [[['hostname', 'Hostname'], ['domain', 'Domain']], ['description', 'Beschreibung']],
      {hostname: ipamSlug(ipamDevName(d.ip, c)), domain: ipamNames._dom ?? IPAM.domain, description: 'HomeAtlas'},
      async data => { if (await ipamWrite('/api/ipam/dns', {op: 'add', items: [{...data, ip: d.ip}]}, 'DNS-Eintrag angelegt')) setTimeout(back, 0); else throw new Error('nicht angelegt'); });
    ipamBack = back;
  },
  ipamResAdd: d => {
    const [, c] = ipamCell(d.ip), back = () => ipamCellPanel(d.ip);
    openForm('DHCP-Reservierung für ' + esc(d.ip), [['mac', 'MAC-Adresse'], ['hostname', 'Hostname'], ['description', 'Beschreibung']],
      {mac: d.mac, hostname: ipamSlug(ipamDevName(d.ip, c)), description: 'HomeAtlas'},
      async data => { if (await ipamWrite('/api/ipam/dhcp', {op: 'add', ip: d.ip, ...data, domain: ipamNames._dom ?? IPAM.domain}, `Reservierung in ${SRC[IPAM.dhcp_target]} angelegt`)) setTimeout(back, 0); else throw new Error('nicht angelegt'); },
      `<div class="hint" style="margin-top:12px;font-size:12.5px">Wird in ${SRC[IPAM.dhcp_target]} angelegt. Das Gerät bekommt die Adresse beim nächsten Erneuern seiner Lease.</div>`);
    ipamBack = back;
  },
  ipamResDel: d => { if (confirm(`DHCP-Reservierung für ${d.ip} löschen?`)) ipamWrite('/api/ipam/dhcp', {op: 'del', uuid: d.u}, 'Reservierung gelöscht'); },
  ipamNewDev: d => {
    const [s, c] = ipamCell(d.ip), mac = c && ((c.arp && c.arp.mac) || (c.lease && c.lease.mac) || (c.res && c.res.mac)) || '';
    deviceForm({type: 'other', ip: d.ip, mac, name: ipamDevName(d.ip, c), hostname: ipamDevName(d.ip, c), vlan_id: s ? s.vlan_id : '', rack_height: 1});
  },
  ipamShow: d => { const b = $('#side [data-view=ipam]'); b.click(); ipamTab = 'addr'; ipamCellIp = d.ip; const go = () => { if (IPAM) ACT.ipamCellOpen({ip: d.ip}); else setTimeout(go, 200); }; go(); },
  ispEdit: d => ispForm(dev(+d.id)),
  ispLink: d => {
    const net = dev(+d.id), cand = S.devices.filter(x => ['firewall', 'router'].includes(bt(x.type))).sort((a, b) => (bt(a.type) === 'router') - (bt(b.type) === 'router'));
    linkForm({kind: 'wan', a_id: cand.length ? cand[0].id : '', b_id: net.id});
  },
  typeEdit: d => typeForm(S.types.find(t => t.key === d.k)),
  typeNew: () => typeForm({}),
  typeDel: d => {
    const t = S.types.find(x => x.key === d.k), n = S.devices.filter(x => x.type === t.key).length;
    const msg = t.custom ? `Typ „${t.label}“ löschen?${n ? `\n${n} Gerät${n === 1 ? '' : 'e'} bekommen den Typ „${(TYPEDEF[t.base] || {}).label || t.base}“.` : ''}` : `„${t.label}“ auf den Standard zurücksetzen (Bezeichnung, Icon, Bereich, Erkennung)?`;
    if (confirm(msg)) run(async () => { await api('DELETE', '/api/types/' + encodeURIComponent(t.key)); await load(true); closePanel(); renderTypes(); }, t.custom ? 'Typ gelöscht' : 'Zurückgesetzt');
  },
  iconPick: () => { const f = document.createElement('input'); f.type = 'file'; f.multiple = true; f.accept = '.svg,.png,.webp,.jpg,.jpeg'; f.onchange = () => uploadFiles([...f.files]); f.click(); },
  iconDel: d => { if (confirm(`Icon „${d.n}“ löschen?${+d.u ? `\nEs wird ${d.u}× verwendet – dort erscheint wieder das Standard-Symbol.` : ''}`)) run(async () => { await api('DELETE', '/api/icons/' + encodeURIComponent(d.n)); await load(true); renderTypes(); }, 'Icon gelöscht'); },
  goTypes: () => { view = 'types'; document.querySelectorAll('#side button[data-view]').forEach(x => { const on = x.dataset.view === 'system'; x.classList.toggle('on', on); x.toggleAttribute('aria-current', on); }); $('#crumb').textContent = 'Gerätetypen & Icons'; closePanel(); render(); main.scrollTop = 0; },
  navEdit: () => navEditPanel(),
  newNav: () => navForm({}),
  editNav: d => navForm(S.navlinks.find(l => l.id === +d.id)),
  delNav: d => { const l = S.navlinks.find(x => x.id === +d.id); if (confirm(`Link „${l.label}“ aus dem Menü entfernen?`)) run(async () => { await api('DELETE', '/api/navlinks/' + l.id); await load(true); navEditPanel(); }); },
  cancel: () => { if (ipamBack) { const b = ipamBack; ipamBack = null; b(); } else if (navBack) { navBack = false; navEditPanel(); } else if (sel && dev(sel)) showDevice(sel); else closePanel(); },
  show: d => { const x = dev(+d.id); if (x) showDevice(x.id); },
  goFinds: () => $('#tabs [data-view="finds"]').click(),
  fit: fitView,
  relayout: () => {
    if (!confirm('Alle Karten neu anordnen? Deine Positionen gehen verloren.')) return;
    if (viewMode === 'rooms') { try { localStorage.removeItem('homeatlas.roompos'); } catch (e) { /* egal */ } } else for (const c of cards.values()) { c.x = null; c.d.x = null; }
    renderTopo(); fitView();
  },
  viewMode: d => { viewMode = d.m; closePanel(); renderTopo(); fitView(); },
  vfilter: d => { vfilter = vfilter === +d.id ? null : +d.id; renderTopo(); },
  newDevice: d => deviceForm({type: d.parent ? 'container' : 'server', parent_id: d.parent || '', rack_height: 1}),
  editDevice: d => deviceForm(dev(+d.id)),
  delDevice: d => { const x = dev(+d.id), n = kidsOf(x.id).length; if (confirm(x.type === 'group' ? `Bereich „${x.name}“ auflösen? Die ${n} Geräte darin bleiben erhalten.` : `„${x.name}“${n ? ` samt ${n} enthaltenen Einträgen` : ''} löschen?`)) { closePanel(); run(() => api('DELETE', '/api/devices/' + x.id)); } },
  addAddr: d => { const x = dev(+d.id); sel = x.id; openForm('Weitere Adresse', [[['ip', 'IP-Adresse'], ['mac', 'MAC-Adresse']],
    ['label', 'Bezeichnung (z. B. eth1, Storage-Netz)'], ['note', 'Notiz', 'area'], ['vlan_id', 'Netzwerk (leer = automatisch nach Subnetz)', 'select', vlanOpts()]], {},
    data => api('POST', `/api/devices/${x.id}/addrs`, data), '', true); },
  editAddr: d => { const x = dev(+d.id), a = addrsOf(x)[+d.idx]; sel = x.id; openForm(`Adresse ${esc(a.ip || a.mac)}`, [[['ip', 'IP-Adresse'], ['mac', 'MAC-Adresse']],
    ['label', 'Bezeichnung (z. B. eth1, Storage-Netz)'], ['note', 'Notiz', 'area'], ['vlan_id', 'Netzwerk (leer = automatisch nach Subnetz)', 'select', vlanOpts()]], a,
    data => api('PUT', `/api/devices/${x.id}/addrs/${d.idx}`, data), '', true); },
  editPrimary: d => { const x = dev(+d.id), m = x.meta || {}; sel = x.id; openForm(`Hauptadresse ${esc(x.ip || x.mac || '')}`,
    [['label', 'Bezeichnung (z. B. eth0, Verwaltung)'], ['note', 'Notiz', 'area']], {label: m.primary_label, note: m.primary_note},
    data => api('PUT', '/api/devices/' + x.id, {meta: {primary_label: data.label || null, primary_note: data.note || null}}), '', true); },
  editMemo: d => { const x = dev(+d.id); sel = x.id; openForm(`Notizen zu ${esc(x.name)}`, [['memo', 'Notizen', 'area'], ['memo_show', 'Auf der Karte anzeigen', 'check']],
    {memo: x.memo, memo_show: x.memo_show}, data => api('PUT', '/api/devices/' + x.id, data), '', true); },
  memoToggle: d => { const x = dev(+d.id); run(() => api('PUT', '/api/devices/' + x.id, {memo_show: x.memo_show ? 0 : 1})); },
  addrPrimary: d => run(() => api('POST', `/api/devices/${d.id}/addrs/${d.idx}/primary`), 'Hauptadresse gewechselt'),
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
    const lines = [['Status', 'IP', 'Gerät', 'Hostname', 'Typ', 'Raum', 'MAC', 'Hersteller', 'VLAN', 'Netzwerk'].map(q).join(';'),
      ...netFiltered().map(r => { const v = vlan(r.vlan_id) || {}; return [STATUS[r.status], r.ip, r.name, r.hostname, r.type, r.room || '', r.mac, r.vendor, v.vid ?? '', v.name || ''].map(q).join(';'); })];
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(['\ufeff' + lines.join('\r\n')], {type: 'text/csv'})); a.download = 'homeatlas-adressen.csv'; a.click();
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
      [['type', 'Typ', 'select', [...keep, ...typeOpts()]], ['vlan_id', 'Netzwerk', 'select', [...keep, ['none', '– keins –'], ...S.vlans.map(v => [v.id, v.vid != null ? `${vtag(v)} · ${v.name}` : v.name])]]],
      ['parent_id', 'Läuft auf / gehört zu', 'select', [...keep, ['none', '– eigenständig –'], ...S.devices.filter(d => !multi.has(d.id) && !['app', 'service'].includes(d.type)).map(d => [d.id, d.name])]],
      [['model', 'Modell (leer = unverändert)'], ['os', 'System (leer = unverändert)']], ['room', 'Raum (leer = unverändert, „-“ = Raum entfernen)'], ['icon', 'Icon (leer = unverändert)'], ['note', 'Notiz (leer = unverändert)'],
    ], {}, async data => {
      const patch = {};
      for (const [k, v] of Object.entries(data)) if (v !== '') patch[k] = v === 'none' || (k === 'room' && v === '-') ? '' : v;
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
  shelfAdd: d => {
    const sh = dev(+d.id), free = S.devices.filter(x => !x.parent_id && !x.rack_id && !shelfOf(x) && !PASSIVE.has(x.type) && x.type !== 'group');
    if (!free.length) return toast('Kein freies Gerät vorhanden');
    sel = sh.id;
    openForm(`Auf „${esc(sh.name)}“ stellen`, [['dev', 'Gerät', 'select', free.map(x => [x.id, x.name])]], {}, data => api('PUT', '/api/devices/' + data.dev, {meta: {shelf: sh.id}}), '', true);
  },
  shelfRemove: d => run(() => api('PUT', '/api/devices/' + d.id, {meta: {shelf: null}})),
  ppPorts: d => { const n = prompt('Anzahl der Ports (1–96):', (dev(+d.id).meta || {}).ports_n || 24); if (n) run(() => api('PUT', '/api/devices/' + d.id, {meta: {ports_n: Math.min(96, Math.max(1, +n || 24))}})); },
  newGroup: () => openForm('Neuer Bereich', [['name', 'Name (z. B. Smarthome-Lampen)'], ['note', 'Beschreibung'], ['vlan_id', 'Netzwerk (für die Rahmenfarbe)', 'select', vlanOpts()], ['icon', 'Icon']],
    {icon: 'type-group'}, async data => { if (!data.name) throw new Error('Name fehlt'); sel = (await api('POST', '/api/devices', {...data, type: 'group'})).id; }, '', true),
  groupAdd: d => {
    const g = dev(+d.id), cand = S.devices.filter(x => !x.parent_id && x.id !== g.id && x.type !== 'group' && !PASSIVE.has(x.type) && x.type !== 'internet');
    if (!cand.length) return toast('Keine eigenständigen Geräte vorhanden');
    sel = g.id;
    openForm(`Zu „${esc(g.name)}“ hinzufügen`, [['ids', 'Geräte (Mehrfachauswahl)', 'multi', cand.map(x => [x.id, x.name + (x.ip ? ' · ' + x.ip : '')])]], {ids: []},
      async data => { if (!data.ids.length) throw new Error('Kein Gerät gewählt'); for (const id of data.ids) await api('PUT', '/api/devices/' + id, {parent_id: g.id}); }, '', true);
  },
  bulkGroup: () => {
    const ids = [...multi].filter(id => dev(id).type !== 'group'), groups = S.devices.filter(x => x.type === 'group' && !multi.has(x.id));
    openForm(`${ids.length} Geräte gruppieren`, [['target', 'Bereich', 'select', [['new', '＋ Neuer Bereich'], ...groups.map(g => [g.id, g.name])]],
      ['gname', 'Name des neuen Bereichs', 'text', 'z. B. Smarthome-Lampen']], {target: groups.length ? groups[0].id : 'new'},
      async data => {
        let gid = +data.target;
        if (data.target === 'new') { if (!data.gname) throw new Error('Name für den neuen Bereich fehlt'); gid = (await api('POST', '/api/devices', {name: data.gname, type: 'group', icon: 'type-group'})).id; }
        let fail = 0;
        for (const id of ids) await api('PUT', '/api/devices/' + id, {parent_id: gid}).catch(() => { fail++; });
        multi.clear(); selMode = false;
        if (fail) throw new Error(`${fail} Geräte ließen sich nicht verschieben`);
      });
    const f = n => $(`[name=${n}]`, panel), sync = () => { f('gname').closest('label').hidden = f('target').value !== 'new'; };
    f('target').addEventListener('change', sync); sync();
  },
  delNever: () => { if (confirm('Alle Checks entfernen, die noch nie erreichbar waren?')) { MON = null; run(async () => { const r = await api('DELETE', '/api/monitor/never'); setTimeout(() => toast(`${r.removed} Checks entfernt`), 50); }); } },
  monArea: d => { monOpen.add(d.k); $('#monbody').innerHTML = monBody(); },
  newCheck: d => { const x = d.dev ? dev(+d.dev) : null; checkForm({device_id: x ? x.id : '', kind: 'ping', target: x ? (x.ip || x.hostname || '') : '', interval_s: 60, enabled: 1}); },
  editCheck: d => { const c = (MON && MON.checks.find(x => x.id === +d.id)) || S.checks.find(x => x.id === +d.id); if (c) checkForm({...c, device: (dev(c.device_id) || {}).name}); },
  delCheck: d => { if (confirm('Check samt Verlauf löschen?')) { closePanel(); MON = null; run(() => api('DELETE', '/api/monitor/checks/' + d.id)); } },
  runCheck: async d => { try { toast('Prüfe …'); const r = await api('POST', `/api/monitor/checks/${d.id}/run`); toast(r.last_error ? 'Fehlgeschlagen: ' + r.last_error : `In Ordnung${r.last_ms != null ? ' · ' + Math.round(r.last_ms) + ' ms' : ''}`, !!r.last_error); load(true); } catch (e) { toast(e.message, true); } },
  genChecks: async () => {
    let p; try { p = await api('GET', '/api/monitor/plan'); } catch (e) { return toast(e.message, true); }
    const total = Object.values(p.new).reduce((a, b) => a + b, 0);
    if (!total) return toast('Für alle dokumentierten Geräte gibt es schon Checks');
    const on = new Set(['network', 'servers', 'storage', 'apps']);
    openForm('Checks aus der Dokumentation', Object.entries(p.areas).filter(([k]) => p.new[k]).map(([k, n]) => ['a_' + k, `${n} · ${p.new[k]} ${p.new[k] === 1 ? 'neuer Check' : 'neue Checks'}`, 'check']),
      Object.fromEntries(Object.keys(p.areas).map(k => ['a_' + k, on.has(k) ? 1 : 0])),
      async data => { const areas = Object.keys(data).filter(k => data[k]).map(k => k.slice(2)); const r = await api('POST', '/api/monitor/generate', {areas}); MON = null; setTimeout(() => toast(`${r.created} Checks angelegt – erste Ergebnisse in wenigen Sekunden`), 50); },
      '<p class="muted" style="flex-basis:100%;font-size:12.5px;margin:6px 0 0">Je Gerät mit IP ein Ping, je bekanntem Dienst-Port ein Port-Check, je Weboberfläche ein HTTP-Check. Vorhandene Checks bleiben unverändert; Clients und Rack-Platzhalter werden nie überwacht.</p>');
  },
  testNotify: async () => { try { await api('POST', '/api/monitor/test-notify'); toast('Testmeldung gesendet'); } catch (e) { toast(e.message, true); } },
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
    const cfg = s ? {...s.config} : {};
    if (d.kind === 'docker' && x && isLocal(x.ip)) cfg.url = '';   // der Host, auf dem HomeAtlas läuft: Socket statt Netzwerk-API
    integForm({kind: d.kind, device_id: x ? x.id : '', name: x ? x.name : '', config: cfg});
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
document.addEventListener('keydown', e => { if (e.key === 'Escape') navDrawer(false); });
// ------------------------------------------------------------ Internetzugang (ISP)
function ispSection(d) {
  const i = ispOf(d), L = liveOf(d), f = (k, v) => v ? `<dt>${k}</dt><dd>${v}</dd>` : '';
  const pub = L && L.wan_ip ? `<span class="mono">${esc(L.wan_ip)}</span>${L.nat ? ' <span class="muted">(privat – Router/Modem davor macht NAT)</span>' : L.cgnat ? ' <span class="muted">(CGNAT-Bereich)</span>' : ''}` : i.ip ? `<span class="mono">${esc(i.ip)}</span>` : '';
  const st = L ? `<span class="dot ${L.status === 'down' || L.status === 'force_down' ? 'offline' : 'online'}"></span> ${esc(L.text || L.status)} · ${esc(liveTxt(L))}` +
    `<span class="muted"> · ${esc(i.gateway || '')}${L.monitor ? ', prüft ' + esc(L.monitor) : ''} · ${ago(L.at)}</span>` : '';
  const empty = !i.provider && !i.access && !L;
  let h = `<h3>Internetzugang</h3>`;
  if (empty) h += `<p class="muted" style="font-size:12.5px;margin:0 0 8px">Anbieter, Zugangsart, Bandbreite und öffentliche Adresse eintragen. Mit OPNsense-Anbindung kommen Zustand, Latenz und WAN-Adresse von selbst.</p>`;
  else h += `<dl class="facts">${f('Anbieter', esc(i.provider || ''))}${f('Zugang', i.access && ACCESS[i.access] ? esc(ACCESS[i.access][0]) : '')}` +
    f('Bandbreite', i.down || i.up ? `↓ ${mbit(+i.down || 0)} · ↑ ${mbit(+i.up || 0)}` : '') + f('Zustand', st) + f('Öffentl. IPv4', pub) +
    f('IPv4', i.ip4 ? esc(IP4MODE[i.ip4] || i.ip4) : '') + f('IPv6', [i.ip6 ? esc(i.ip6) : '', L && L.wan_ip6 ? `<span class="mono">${esc(L.wan_ip6)}</span>` : ''].filter(Boolean).join(' · ')) +
    f('DynDNS', i.dyndns ? `<span class="mono">${esc(i.dyndns)}</span>` : '') + f('Modem / ONT', esc(i.modem || '')) +
    f('Kundennr.', i.customer ? `<span class="mono">${esc(i.customer)}</span>` : '') + f('Hotline', i.hotline ? `<a href="tel:${esc(i.hotline.replace(/[^\d+]/g, ''))}">${esc(i.hotline)}</a>` : '') +
    f('Vertrag', esc([i.contract_end ? 'Laufzeit bis ' + i.contract_end : '', i.cost ? i.cost + ' € / Monat' : ''].filter(Boolean).join(' · '))) + '</dl>';
  if (!ro()) h += `<div class="acts"><button class="btn sm" data-act="ispEdit" data-id="${d.id}">${empty ? 'Anschluss eintragen' : 'Anschluss bearbeiten'}</button>` +
    (S.links.some(l => l.kind === 'wan' && (l.a_id === d.id || l.b_id === d.id)) ? '' : `<button class="btn sm" data-act="ispLink" data-id="${d.id}">WAN-Verbindung anlegen</button>`) + '</div>';
  return h;
}
function ispForm(d) {
  const i = ispOf(d), gws = S.gateways || [];
  openForm('Internetzugang · ' + esc(d.name), [
    [['provider', 'Anbieter', 'text', 'z. B. Telekom, Vodafone, Deutsche Glasfaser'], ['access', 'Zugang', 'select', [['', '–'], ...Object.entries(ACCESS).map(([k, v]) => [k, v[0]])]]],
    [['down', 'Download (Mbit/s)', 'number'], ['up', 'Upload (Mbit/s)', 'number']],
    [['ip4', 'IPv4', 'select', [['', '–'], ...Object.entries(IP4MODE)]], ['ip', 'Öffentliche IPv4 (bei statisch)', 'text', 'z. B. 203.0.113.10']],
    [['ip6', 'IPv6-Präfix', 'text', 'z. B. /56 delegiert'], ['dyndns', 'DynDNS-Name', 'text', 'z. B. home.example.de']],
    ['gateway', 'OPNsense-Gateway (Zustand, Latenz, WAN-Adresse)', 'select', [['', gws.length ? '– keins –' : '– keine OPNsense-Anbindung –'], ...gws.map(g => [g.name, `${g.name}${g.address ? ' · ' + g.address : ''}`])]],
    ['modem', 'Modem / ONT', 'text', 'z. B. FRITZ!Box 5590 Fiber im Bridge-Modus'],
    [['customer', 'Kundennummer'], ['hotline', 'Hotline / Störung', 'text', 'z. B. 0800 330 1000']],
    [['contract_end', 'Mindestlaufzeit bis', 'text', 'z. B. 03/2027'], ['cost', 'Kosten € / Monat', 'text']],
  ], i, async data => {
    for (const k of ['down', 'up']) data[k] = data[k] ? +data[k] : null;
    await api('PUT', '/api/devices/' + d.id, {meta: {isp: data}, ...(d.model || !data.provider ? {} : {})});
    sel = d.id;
  }, '', true);
}
// ------------------------------------------------------------ Gerätetypen & Icons
let typeQ = '';
const AREA_LABEL = {network: 'Netzwerk', servers: 'Server', storage: 'Speicher', apps: 'Dienste', smarthome: 'Smarthome', clients: 'Endgeräte', other: 'Sonstiges'};
const fileB64 = f => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = () => no(new Error('Datei nicht lesbar')); r.readAsDataURL(f); });
const iconName = fn => fn.replace(/\.[a-z0-9]+$/i, '').toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40);
async function uploadIcon(file, name) {
  if (!/\.(svg|png|webp|jpe?g)$/i.test(file.name)) throw new Error(`${file.name}: nur SVG, PNG, WebP oder JPG`);
  if (file.size > 512 * 1024) throw new Error(`${file.name}: größer als 512 KB`);
  const data = await fileB64(file), body = {name: name || iconName(file.name), data};
  try { return await api('POST', '/api/icons', body); }
  catch (e) {
    if (!/gibt es schon/.test(e.message) || !confirm(`${e.message}. Ersetzen?`)) throw e;
    return api('POST', '/api/icons', {...body, replace: 1});
  }
}
async function uploadFiles(files) {
  let last = null, n = 0;
  for (const f of files) { try { last = await uploadIcon(f); n++; } catch (e) { toast(e.message, true); } }
  if (n) { await load(true); toast(n === 1 ? `Icon „${last.name}“ hochgeladen` : `${n} Icons hochgeladen`); if (view === 'types') renderTypes(); }
  return last;
}
function renderTypes() {
  const can = !ro(), q = fold(typeQ.trim());
  const list = S.types.filter(t => !['patchpanel', 'shelf', 'blank', 'cablemgmt'].includes(t.key) || q).filter(t => !q || fold(`${t.label} ${t.key} ${t.default_label || ''}`).includes(q));
  const used = {}; for (const d of S.devices) used[d.type] = (used[d.type] || 0) + 1;
  const tile = t => `<button class="ttile${t.hidden ? ' hid' : ''}" ${can ? `data-act="typeEdit" data-k="${esc(t.key)}"` : ''} title="${esc(t.label)} (${esc(t.key)})">` +
    `<img src="${iconUrl(typeIcon(t.key))}" alt="" width="34" height="34"><b>${esc(t.label)}</b><span class="mono">${esc(t.key)}</span>` +
    `<em>${used[t.key] ? used[t.key] + ' Gerät' + (used[t.key] === 1 ? '' : 'e') : 'nicht verwendet'}</em>` +
    `<i class="tags">${t.custom ? `<span class="tg c">eigener · wie ${esc((TYPEDEF[t.base] || {}).label || t.base)}</span>` : t.changed ? '<span class="tg">angepasst</span>' : ''}` +
    `${t.hidden ? '<span class="tg">ausgeblendet</span>' : ''}${(t.rules.vendor.length + t.rules.hostname.length) ? '<span class="tg r">Erkennung</span>' : ''}</i></button>`;
  let h = `<div class="page tpage"><div class="bar"><h2>Gerätetypen &amp; Icons</h2>${can ? '<button class="btn pri" data-act="typeNew">+ Eigener Typ</button><button class="btn" data-act="iconPick">Icons hochladen</button>' : ''}</div>` +
    `<p class="muted tintro">Jeder Typ hat Bezeichnung, Icon, Bereich (Überwachung, Übersichten) und optional Stichwörter, an denen der Scan ihn erkennt. ` +
    `Eigene Typen verhalten sich wie ihre Vorlage – etwa ob sie ins Rack passen oder als Endgerät gelten.</p>` +
    `<input class="inp tsearch" id="typeq" type="search" placeholder="Typ suchen …" value="${esc(typeQ)}" aria-label="Typ suchen">`;
  for (const [a, label] of Object.entries(AREA_LABEL)) {
    const ts = list.filter(t => t.area === a);
    if (ts.length) h += `<h3 class="tarea">${label} <span class="muted">${ts.length}</span></h3><div class="tgrid">${ts.map(tile).join('')}</div>`;
  }
  if (!list.length) h += '<div class="hint">Kein Typ passt zur Suche.</div>';
  const icons = S.icons || [];
  h += `<h3 class="tarea">Eigene Icons <span class="muted">${icons.length}</span></h3>` +
    `<div class="idrop${can ? '' : ' ro'}" id="idrop">${icons.map(i => `<div class="itm"><img src="${iconUrl(i.name)}" alt="" width="40" height="40">` +
      `<b title="${esc(i.name)}">${esc(i.label)}</b><span class="mono">${esc(i.name)}</span><em>${i.used ? i.used + '× verwendet' : 'nicht verwendet'} · ${i.kind.toUpperCase()}</em>` +
      (can ? `<button class="btn sm bad" data-act="iconDel" data-n="${esc(i.name)}" data-u="${i.used}" aria-label="${esc(i.label)} löschen">×</button>` : '') + '</div>').join('')}` +
    (can ? `<button class="itm add" data-act="iconPick"><span>+</span><b>Hochladen</b><em>SVG, PNG, WebP, JPG · bis 512 KB<br>oder Dateien hierher ziehen</em></button>` : '') + '</div>' +
    `<p class="muted" style="font-size:12.5px;margin-top:10px">Ein hochgeladenes Icon heißt <span class="mono">up-name</span> und steht in jedem Icon-Feld zur Auswahl – ` +
    `bei Typen, Geräten und Links im Menü. SVG-Dateien werden beim Hochladen von Skripten und externen Verweisen bereinigt.</p></div>`;
  main.innerHTML = h;
  const z = $('#idrop');
  if (can && z) {
    z.addEventListener('dragover', e => { e.preventDefault(); z.classList.add('over'); });
    z.addEventListener('dragleave', () => z.classList.remove('over'));
    z.addEventListener('drop', e => { e.preventDefault(); z.classList.remove('over'); uploadFiles([...e.dataTransfer.files]); });
  }
  $('#typeq').addEventListener('input', e => { typeQ = e.target.value; const pos = e.target.selectionStart; renderTypes(); const n = $('#typeq'); n.focus(); n.setSelectionRange(pos, pos); });
}
function typeForm(t) {
  const isNew = !t.key, bases = S.types.filter(x => !x.custom && !x.special).map(x => [x.key, x.label]).sort((a, b) => a[1].localeCompare(b[1], 'de'));
  const n = t.key ? S.devices.filter(d => d.type === t.key).length : 0;
  const extra = isNew ? '' : t.custom ? `<button class="btn bad" type="button" data-act="typeDel" data-k="${esc(t.key)}">Typ löschen</button>`
    : t.changed ? `<button class="btn" type="button" data-act="typeDel" data-k="${esc(t.key)}">Auf Standard zurücksetzen</button>` : '';
  openForm(isNew ? 'Eigener Gerätetyp' : esc(t.label), [
    ['label', isNew ? 'Bezeichnung' : `Bezeichnung${t.custom ? '' : ` (Standard: ${esc(t.default_label)})`}`, 'text', 'z. B. Smartwatch, USV, Wärmepumpe'],
    ['icon', 'Icon'],
    ...(isNew || t.custom ? [['base', 'Verhält sich wie', 'select', bases]] : []),
    ['area', 'Bereich', 'select', Object.entries(AREA_LABEL)],
    ['vendor', 'Erkennung: Hersteller enthält (durch Komma getrennt)', 'text', 'z. B. apple, samsung'],
    ['hostname', 'Erkennung: Hostname enthält (durch Komma getrennt)', 'text', 'z. B. iphone, watch'],
    ...(isNew ? [] : [['hidden', 'In der Typ-Auswahl ausblenden', 'check']]),
  ], {base: 'other', area: 'other', ...t, icon: t.icon || '', vendor: (t.rules || {vendor: []}).vendor.join(', '), hostname: (t.rules || {hostname: []}).hostname.join(', ')}, async data => {
    if (!data.label) throw new Error('Bezeichnung fehlt');
    const body = {label: data.label, icon: data.icon.trim().toLowerCase(), area: data.area, rules: {vendor: data.vendor, hostname: data.hostname}};
    if ('hidden' in data) body.hidden = data.hidden;
    if (data.base) body.base = data.base;
    if (isNew) await api('POST', '/api/types', body); else await api('PUT', '/api/types/' + encodeURIComponent(t.key), body);
    await load(true); setTimeout(() => { if (view === 'types') renderTypes(); }, 0);
  }, `${extra}${!isNew && n ? `<p class="muted" style="font-size:12.5px;margin-top:12px">${n} Gerät${n === 1 ? '' : 'e'} mit diesem Typ.</p>` : ''}` +
    `<p class="muted" style="font-size:12.5px;margin-top:8px">Bereich: wo der Typ in Überwachung und Übersichten einsortiert wird. Erkennung: trifft ein Stichwort, schlägt der Scan diesen Typ vor (eigene Typen zuerst).</p>`);
  const ic = $('[name=icon]', panel); if (ic && !ic.value) ic.placeholder = `leer = ${typeIcon(t.key || 'other')}`;
  const base = $('[name=base]', panel);
  if (base && isNew) base.addEventListener('change', () => { const a = $('[name=area]', panel); if (a && TYPEDEF[base.value]) { a.value = TYPEDEF[base.value].area; a.dispatchEvent(new Event('change')); } });
}
// ------------------------------------------------------------ Auswahlfelder mit Suche
// Lange Auswahllisten bekommen ein Eingabefeld: Tippen grenzt ein (ohne Groß-/Kleinschreibung und Akzente),
// Pfeiltasten wählen, Enter übernimmt. Das eigentliche <select> bleibt im Formular und trägt den Wert.
const fold = s => (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
let comboSeq = 0;
function comboize(sel) {
  if (sel.dataset.combo || sel.options.length < 8) return;
  sel.dataset.combo = 1;
  if (sel.multiple) return multiFilter(sel);
  const id = 'cb' + (++comboSeq), wrap = document.createElement('div'), inp = document.createElement('input'), list = document.createElement('div');
  wrap.className = 'combo';
  Object.assign(inp, {type: 'text', className: 'cbin', autocomplete: 'off', spellcheck: false, placeholder: 'Tippen zum Suchen …'});
  inp.setAttribute('role', 'combobox'); inp.setAttribute('aria-expanded', 'false'); inp.setAttribute('aria-controls', id); inp.setAttribute('aria-autocomplete', 'list');
  list.className = 'cblist'; list.id = id; list.setAttribute('role', 'listbox'); list.hidden = true;
  sel.parentNode.insertBefore(wrap, sel); wrap.append(sel, inp, list);
  sel.classList.add('cbsel'); sel.tabIndex = -1; sel.setAttribute('aria-hidden', 'true');
  const label = () => (sel.selectedOptions[0] || {}).textContent || '';
  let items = [], act = 0;
  inp.value = label();
  const mark = (t, q) => { if (!q) return esc(t); const i = fold(t).indexOf(q); return i < 0 ? esc(t) : esc(t.slice(0, i)) + '<mark>' + esc(t.slice(i, i + q.length)) + '</mark>' + esc(t.slice(i + q.length)); };
  const draw = q => {
    q = fold(q.trim());
    items = [...sel.options].filter(o => !q || fold(o.textContent).includes(q));
    act = Math.max(0, items.indexOf(sel.selectedOptions[0]));
    list.innerHTML = items.slice(0, 200).map((o, i) => `<div role="option" id="${id}-${i}" data-i="${i}" class="${i === act ? 'act' : ''}${o.selected ? ' cur' : ''}${o.value === '' ? ' none' : ''}" aria-selected="${o.selected}">${mark(o.textContent, q)}</div>`).join('') +
      (items.length > 200 ? `<div class="more">… ${items.length - 200} weitere – genauer suchen</div>` : '') + (items.length ? '' : '<div class="more">Kein Treffer</div>');
    list.hidden = false; inp.setAttribute('aria-expanded', 'true'); move(0);
  };
  const move = d => {
    if (!items.length) return;
    act = (act + d + Math.min(items.length, 200)) % Math.min(items.length, 200);
    list.querySelectorAll('[role=option]').forEach(n => n.classList.toggle('act', +n.dataset.i === act));
    const n = list.querySelector(`[data-i="${act}"]`); if (n) { n.scrollIntoView({block: 'nearest'}); inp.setAttribute('aria-activedescendant', n.id); }
  };
  const close = () => { list.hidden = true; inp.setAttribute('aria-expanded', 'false'); inp.removeAttribute('aria-activedescendant'); };
  const choose = o => { if (!o) return; sel.value = o.value; inp.value = o.textContent; close(); sel.dispatchEvent(new Event('change', {bubbles: true})); };
  inp.addEventListener('focus', () => { inp.select(); draw(''); });
  inp.addEventListener('input', () => draw(inp.value));
  inp.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); if (list.hidden) draw(''); else move(e.key === 'ArrowDown' ? 1 : -1); }
    else if (e.key === 'Enter') { if (!list.hidden) { e.preventDefault(); choose(items[act]); } }
    else if (e.key === 'Escape') { if (!list.hidden) { e.preventDefault(); e.stopPropagation(); inp.value = label(); close(); } }
    else if (e.key === 'Tab' && !list.hidden && inp.value.trim() && fold(inp.value) !== fold(label())) choose(items[act]);
  });
  list.addEventListener('mousedown', e => { const n = e.target.closest('[role=option]'); if (n) { e.preventDefault(); choose(items[+n.dataset.i]); } });
  inp.addEventListener('blur', () => setTimeout(() => { close(); inp.value = label(); }, 120));
  sel.addEventListener('change', () => { if (document.activeElement !== inp) inp.value = label(); });
}
function multiFilter(sel) {
  const inp = document.createElement('input'), cnt = document.createElement('small');
  Object.assign(inp, {type: 'search', className: 'cbin mf', placeholder: 'In der Liste suchen …', autocomplete: 'off', spellcheck: false});
  inp.setAttribute('aria-label', 'Liste filtern');
  cnt.className = 'mfc muted';
  sel.parentNode.insertBefore(inp, sel); sel.after(cnt);
  sel.size = Math.min(10, Math.max(5, sel.options.length));
  const count = () => { const n = sel.selectedOptions.length; cnt.textContent = n ? `${n} ausgewählt` : ''; };
  inp.addEventListener('input', () => { const q = fold(inp.value.trim()); for (const o of sel.options) o.hidden = !!q && !fold(o.textContent).includes(q) && !o.selected; });
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') e.preventDefault(); });
  sel.addEventListener('change', count); count();
}
// ------------------------------------------------------------ IPAM & DNS (Daten aus der OPNsense, Abgleich mit der Dokumentation)
let IPAM = null, ipamAt = 0, ipamLoading = false, ipamErr = '', ipamTab = 'addr', ipamNet = null, ipamDnsFilter = 'all', ipamCellIp = null;
const ipamPick = new Set(), ipamNames = {};
const ipamCan = () => !ro() && IPAM && IPAM.write;
async function loadIpam(refresh) {
  if (ipamLoading) return;
  ipamLoading = true;
  try {
    IPAM = await api(refresh ? 'POST' : 'GET', refresh ? '/api/ipam/refresh' : '/api/ipam'); ipamAt = Date.now(); ipamErr = '';
    if (refresh && IPAM.sync_status) toast(IPAM.sync_status, IPAM.sync_status.startsWith('Fehler'));
  } catch (e) { ipamErr = e.message; if (refresh) toast(e.message, true); }
  ipamLoading = false;
  if (view === 'ipam') { renderIpam(true); if (panelMode === 'ipam' && ipamCellIp) ipamCellPanel(ipamCellIp); }
}
async function ipamWrite(url, body, msg) {
  try { IPAM = await api('POST', url, body); ipamAt = Date.now(); toast(msg); }
  catch (e) { toast(e.message, true); return false; }
  renderIpam(true);
  if (panelMode === 'ipam' && ipamCellIp) ipamCellPanel(ipamCellIp);
  return true;
}
const ipamCell = ip => { for (const s of IPAM.subnets) { const c = s.cells.find(x => x.ip === ip); if (c) return [s, c]; } return [IPAM.subnets.find(s => ip2int(ip) - ip2int(s.first) >= 0 && ip2int(ip) - ip2int(s.first) < s.size), null]; };
const SRC = {unbound: 'Unbound', dnsmasq: 'Dnsmasq', kea: 'Kea', isc: 'ISC DHCP'};
function ipamClass(c, off, s) {
  if (!c) return off === 0 || off === s.size - 1 ? 'x' : '';
  const k = [];
  if (c.issues.some(i => i[0] !== 'moved')) k.push('bad'); else if (c.moved) k.push('mv');
  if (c.gw) k.push('gw'); else if (c.devs.length) k.push('doc'); else if (c.undoc) k.push('unk'); else if (c.dns.length) k.push('dnsonly');
  if (c.res) k.push('r');
  if (c.dns.length && (c.devs.length || c.gw)) k.push('d');
  return k.join(' ');
}
function renderIpam(force) {
  const a = document.activeElement;
  if (!force && main.querySelector('.ipam') && a && main.contains(a) && a.matches('input,select')) return;   // nicht beim Tippen neu zeichnen
  if ((!IPAM && !ipamErr) || (Date.now() - ipamAt > 60000 && !ipamLoading && IPAM)) loadIpam(false);
  if (!IPAM) { main.innerHTML = `<div class="page ipam"><h2>IPAM &amp; DNS</h2><div class="hint">${ipamErr ? esc(ipamErr) : 'Lade Daten …'}</div></div>`; return; }
  const I = IPAM;
  if (!I.source) {
    main.innerHTML = `<div class="page ipam"><h2>IPAM &amp; DNS</h2><div class="hint">Adressen, DNS-Einträge und DHCP kommen direkt aus der OPNsense. ` +
      `Richte dafür zuerst die Anbindung ein.${ro() ? '' : ' <button class="btn pri" data-act="newInteg" data-kind="opnsense" style="margin-left:8px">OPNsense anbinden</button>'}</div></div>`;
    return;
  }
  if (ipamNet !== 'all' && !I.subnets.some(s => s.vlan_id === ipamNet)) ipamNet = 'all';
  renderIpamNav();
  const svc = (k, label, extra) => I.services[k] ? `<span class="pill ${I.services[k] === 'running' ? 'on' : ''}" title="${esc(label)}: ${esc(I.services[k])}"><i></i>${label}${extra ? ' · ' + extra : ''}</span>` : '';
  const hints = I.records.filter(r => ['moved', 'orphan', 'dup'].includes(r.status)).length;
  let h = `<div class="page ipam"><div class="ihead"><div><h2>IPAM &amp; DNS</h2><div class="muted isrc">OPNsense „${esc(I.source.name)}“ · Stand ${I.fetched ? ago(I.fetched) : 'noch nie gelesen'}` +
    `${I.write ? ' · <span class="wr">Schreiben erlaubt</span>' : ' · nur lesen'}</div></div><div class="iact"><div class="seg">` +
    `<button class="btn${ipamTab === 'addr' ? ' on' : ''}" data-act="ipamTab" data-t="addr">Adressen</button>` +
    `<button class="btn${ipamTab === 'dns' ? ' on' : ''}" data-act="ipamTab" data-t="dns">DNS${hints + I.missing.length ? ` <span class="cnt">${hints + I.missing.length}</span>` : ''}</button></div>` +
    `<button class="btn" data-act="ipamRefresh"${ipamLoading ? ' disabled' : ''}>${ipamLoading ? 'Lese …' : 'Neu einlesen'}</button></div></div>`;
  h += '<div class="isvc">' + svc('unbound', 'Unbound', I.dns_target === 'unbound' ? I.counts.dns + ' Einträge' : '') + svc('dnsmasq', 'Dnsmasq', '') + svc('kea', 'Kea DHCP', '') +
    `<span class="pill">${I.counts.reservations} Reservierungen</span><span class="pill">${I.counts.leases} Leases</span><span class="pill">ARP ${I.counts.arp}</span>` +
    Object.entries(I.errors).map(([k, v]) => `<span class="pill err" title="${esc(v)}">⚠ ${esc(k)}</span>`).join('') + '</div>';
  if (!I.write && !ro()) h += `<div class="hint ro">Nur lesen. Zum Anlegen und Ändern von DNS-Einträgen und Reservierungen in der <a href="#" data-act="editInteg" data-id="${I.source.id}">OPNsense-Anbindung</a> den Haken „Änderungen … erlauben“ setzen.</div>`;
  h += ipamNetBar(I) + (ipamTab === 'dns' ? ipamDnsHtml(I) : ipamNet === 'all' ? ipamOverviewHtml(I) : ipamAddrHtml(I));
  main.innerHTML = h + '</div>';
}
function ipamAddrHtml(I) {
  if (!I.subnets.length) return '<div class="hint">Keine Netze mit Subnetz dokumentiert. Unter <b>Netzwerke</b> beim VLAN das Subnetz eintragen (z. B. 192.168.10.0/24).</div>';
  let h = '';
  const s = I.subnets.find(x => x.vlan_id === ipamNet);
  const first = ip2int(s.first), byOff = new Map(s.cells.map(c => [c.off, c]));
  const poolTxt = s.pools.map(p => `${p.start.split('.').slice(-1)}–${p.end.split('.').slice(-1)}`).join(', ');
  const tile = (k, v, sub, cls) => `<div class="itile${cls ? ' ' + cls : ''}"><span>${k}</span><b>${v}</b>${sub ? `<small>${sub}</small>` : ''}</div>`;
  h += `<div class="itiles" style="--c:${esc(s.color || '#8d9aab')}">` + tile('Belegt', `${s.used}<i>/${s.hosts}</i>`, Math.round(s.used / Math.max(1, s.hosts) * 100) + ' %') +
    tile('Dokumentiert', s.documented, s.gateway ? 'Gateway ' + esc(s.gateway) : '') + tile('Nicht dokumentiert', s.undoc, 'im Netz gesehen', s.undoc ? 'warn' : '') +
    tile('DHCP-Bereich', s.pool_size || '–', poolTxt ? '.' + esc(poolTxt) : 'keiner gefunden') + tile('Konflikte', s.conflicts.length, s.conflicts.length ? 'siehe unten' : 'keine', s.conflicts.length ? 'bad' : 'ok') +
    `<div class="itile next"><span>Nächste freie Adresse</span><b>${s.next_free ? esc(s.next_free) : '–'}</b><small>außerhalb des DHCP-Bereichs</small>` +
    (s.next_free ? `<button class="btn sm" data-act="ipamCopy" data-v="${esc(s.next_free)}">Kopieren</button>` : '') + '</div></div>';
  if (s.size <= 1024) {
    const pools = s.pools.map(p => [ip2int(p.start) - first, ip2int(p.end) - first]);
    let g = '';
    for (let off = 0; off < s.size; off++) {
      const c = byOff.get(off), ip = int2ip(first + off), pool = pools.some(([a, b]) => off >= a && off <= b);
      const tip = c ? [ip, ...c.devs.map(d => d.name), c.gw ? 'Gateway' : '', c.res ? 'Reservierung ' + (c.res.hostname || c.res.mac) : '', c.lease && !c.devs.length ? 'Lease ' + (c.lease.hostname || c.lease.mac) : '',
        c.arp && !c.devs.length ? 'ARP ' + c.arp.mac : '', ...c.dns, ...c.issues.map(i => '⚠ ' + i[1])].filter(Boolean).join('\n') : ip + (off === 0 ? '\nNetzadresse' : off === s.size - 1 ? '\nBroadcast' : pool ? '\nfrei · DHCP-Bereich' : '\nfrei');
      g += `<button class="ic ${ipamClass(c, off, s)}${pool ? ' p' : ''}${ipamCellIp === ip ? ' sel' : ''}" data-act="ipamCellOpen" data-ip="${ip}" title="${esc(tip)}">${s.size > 256 ? ip.split('.').slice(-2).join('.') : ip.split('.')[3]}</button>`;
    }
    h += `<div class="igrid${s.size > 256 ? ' wide' : ''}" style="--c:${esc(s.color || '#58a6ff')}">${g}</div>`;
  } else {
    h += '<table class="t"><tr><th>Adresse</th><th>Gerät</th><th>DHCP</th><th>DNS</th><th>Hinweis</th></tr>' + s.cells.map(c =>
      `<tr><td><a href="#" data-act="ipamCellOpen" data-ip="${c.ip}">${c.ip}</a></td><td>${c.devs.map(d => esc(d.name)).join(', ') || (c.gw ? 'Gateway' : '–')}</td>` +
      `<td>${c.res ? 'Reservierung' : c.lease ? 'Lease' : ''}</td><td>${c.dns.map(esc).join(', ')}</td><td>${c.issues.map(i => esc(i[1])).join('; ') || (c.undoc ? 'nicht dokumentiert' : '')}</td></tr>`).join('') + '</table>';
  }
  h += '<div class="ilegend"><span><i class="ic doc"></i>dokumentiert</span><span><i class="ic unk"></i>nicht dokumentiert</span><span><i class="ic gw"></i>Gateway</span>' +
    '<span><i class="ic r"></i>DHCP-Reservierung</span><span><i class="ic dnsonly"></i>nur DNS</span><span><i class="ic p"></i>DHCP-Bereich</span><span><i class="ic mv"></i>Gerät umgezogen</span><span><i class="ic bad"></i>Konflikt</span></div>';
  const undoc = s.cells.filter(c => c.undoc);
  if (s.conflicts.length || undoc.length) {
    h += '<div class="iissues">';
    for (const k of s.conflicts) {
      const c = s.cells.find(x => x.ip === k.ip);
      h += `<div class="iss${k.kind === 'moved' ? '' : ' bad'}"><a href="#" data-act="ipamCellOpen" data-ip="${k.ip}">${k.ip}</a><span>${esc(k.text)}</span>` +
        (k.kind === 'moved' && !ro() && c && c.moved ? `<button class="btn sm" data-act="ipamMove" data-id="${c.moved.id}" data-ip="${k.ip}">Adresse übernehmen</button>` : '') + '</div>';
    }
    for (const c of undoc) {
      const who = (c.lease && c.lease.hostname) || (c.arp && c.arp.hostname) || (c.res && c.res.hostname) || '';
      h += `<div class="iss"><a href="#" data-act="ipamCellOpen" data-ip="${c.ip}">${c.ip}</a><span>Nicht dokumentiert${who ? ': ' + esc(who) : ''} · ${esc((c.arp || c.lease || c.res).mac || '')}` +
        `${c.lease && !c.res ? ' · per DHCP' : ''}</span>${ro() ? '' : `<button class="btn sm" data-act="ipamNewDev" data-ip="${c.ip}">Als Gerät anlegen</button>`}</div>`;
    }
    h += '</div>';
  }
  return h;
}
// Netz-Leiste (alle Tabs) und Seitenmenü-Unterpunkte: Übersicht + je Netz
function ipamNetBar(I) {
  if (!I.subnets.length) return '';
  const chip = s => {
    const pct = Math.round(s.used / Math.max(1, s.hosts) * 100), bad = s.conflicts.filter(k => k.kind !== 'moved').length;
    return `<button class="inet${s.vlan_id === ipamNet ? ' on' : ''}" data-act="ipamNet" data-v="${s.vlan_id}" style="--c:${esc(s.color || '#8d9aab')}"><b>${esc(s.name)}</b>` +
      `<span>${esc(s.subnet)}</span><i class="u"><i style="width:${pct}%"></i></i><em>${s.used}/${s.hosts}${bad ? ` · <span class="bad">⚠ ${bad}</span>` : ''}${s.undoc ? ` · <span class="unk">${s.undoc} unbekannt</span>` : ''}</em></button>`;
  };
  const tot = I.subnets.reduce((a, s) => a + s.used, 0), bad = I.subnets.reduce((a, s) => a + s.conflicts.filter(k => k.kind !== 'moved').length, 0);
  return `<div class="inets"><button class="inet all${ipamNet === 'all' ? ' on' : ''}" data-act="ipamNet" data-v="all"><b>Alle Netze</b><span>${I.subnets.length}</span>` +
    `<i class="u"></i><em>${tot} belegt${bad ? ` · <span class="bad">⚠ ${bad}</span>` : ''}</em></button>${I.subnets.map(chip).join('')}</div>`;
}
function renderIpamNav() {
  const host = $('#ipamsub');
  if (!host) return;
  if (view !== 'ipam' || !IPAM || !IPAM.subnets.length) { if (host.innerHTML) host.innerHTML = ''; return; }
  const item = (v, label, sub, color, badge) => `<button class="${ipamNet === v ? 'on' : ''}" data-act="ipamNet" data-v="${v}" title="${esc(label)} ${esc(sub)}">` +
    `<i style="background:${esc(color)}"></i><span class="nl">${esc(label)}</span>${badge ? `<em class="nl">${badge}</em>` : ''}</button>`;
  const h = item('all', 'Übersicht', '', 'var(--faint)', '') + IPAM.subnets.map(s => {
    const bad = s.conflicts.filter(k => k.kind !== 'moved').length;
    return item(s.vlan_id, s.name, s.subnet, s.color || '#8d9aab', bad ? `<b>⚠ ${bad}</b>` : `${Math.round(s.used / Math.max(1, s.hosts) * 100)} %`);
  }).join('');
  if (host.innerHTML !== h) host.innerHTML = h;
}
function ipamOverviewHtml(I) {
  if (!I.subnets.length) return ipamAddrHtml(I);
  const mini = s => {
    if (s.size > 256) return '';
    const first = ip2int(s.first), byOff = new Map(s.cells.map(c => [c.off, c])), pools = s.pools.map(p => [ip2int(p.start) - first, ip2int(p.end) - first]);
    let g = '';
    for (let off = 0; off < s.size; off++) g += `<i class="${ipamClass(byOff.get(off), off, s)}${pools.some(([a, b]) => off >= a && off <= b) ? ' p' : ''}"></i>`;
    return `<div class="mini">${g}</div>`;
  };
  let h = '<div class="iover">' + I.subnets.map(s => {
    const bad = s.conflicts.filter(k => k.kind !== 'moved').length, mv = s.conflicts.length - bad, pct = Math.round(s.used / Math.max(1, s.hosts) * 100);
    return `<button class="icard" data-act="ipamNet" data-v="${s.vlan_id}" style="--c:${esc(s.color || '#8d9aab')}">` +
      `<div class="ict"><b>${esc(s.name)}</b>${s.vid != null ? `<span class="vid">VLAN ${s.vid}</span>` : ''}<span class="mono">${esc(s.subnet)}</span></div>` +
      `${mini(s)}<div class="icbar"><i style="width:${pct}%"></i></div>` +
      `<div class="icstats"><span><b>${s.used}</b>/${s.hosts} belegt</span><span><b>${s.documented}</b> dokumentiert</span>` +
      `${s.undoc ? `<span class="unk"><b>${s.undoc}</b> unbekannt</span>` : ''}${bad ? `<span class="bad"><b>${bad}</b> Konflikte</span>` : ''}${mv ? `<span class="unk"><b>${mv}</b> umgezogen</span>` : ''}</div>` +
      `<div class="icfoot"><span>DHCP ${s.pool_size ? s.pool_size + ' Adressen' : '–'}</span><span>frei: <b class="mono">${s.next_free ? esc(s.next_free) : '–'}</b></span></div></button>`;
  }).join('') + '</div>';
  if (I.outside.length) {
    h += `<h3 class="imh">Adressen außerhalb der dokumentierten Netze</h3><p class="muted" style="margin:-4px 0 10px;font-size:12.5px">Die Firewall kennt Geräte in diesen Bereichen, ` +
      'in HomeAtlas gibt es dafür aber kein Netz mit Subnetz. Meist ein vergessenes VLAN.</p><div class="iissues">' + I.outside.map(o =>
        `<div class="iss"><a class="mono">${esc(o.subnet)}</a><span>${o.count} ${o.count === 1 ? 'Adresse' : 'Adressen'}${o.intf ? ' · Schnittstelle ' + esc(o.intf) : ''} · z. B. ${o.examples.map(esc).join(', ')}</span>` +
        (ro() ? '' : `<button class="btn sm" data-act="ipamNewNet" data-net="${esc(o.subnet)}" data-intf="${esc(o.intf || '')}">Netz anlegen</button>`) + '</div>').join('') + '</div>';
  }
  return h;
}
const DNS_ST = {ok: ['passt', 'ok'], moved: ['Adresse veraltet', 'warn'], orphan: ['kein Gerät', ''], dup: ['doppelt', 'bad'], off: ['deaktiviert', ''], other: ['', '']};
function ipamDnsHtml(I) {
  const hints = I.records.filter(r => ['moved', 'orphan', 'dup'].includes(r.status));
  const rows = ipamDnsFilter === 'hints' ? hints : I.records;
  const can = ipamCan();
  let h = `<div class="dnsbar"><div class="seg"><button class="btn${ipamDnsFilter === 'all' ? ' on' : ''}" data-act="ipamDnsFilter" data-f="all">Alle Einträge (${I.records.length})</button>` +
    `<button class="btn${ipamDnsFilter === 'hints' ? ' on' : ''}" data-act="ipamDnsFilter" data-f="hints">Hinweise (${hints.length})</button></div>` +
    `<label class="dom">Domain für neue Einträge <input id="ipamDom" value="${esc(ipamNames._dom ?? I.domain)}" placeholder="z. B. home.lan" spellcheck="false"></label>` +
    `${S.role === 'admin' ? '<button class="btn sm" data-act="ipamDomSave">als Standard</button>' : ''}<span class="muted">Ziel: ${I.dns_target ? SRC[I.dns_target] : 'kein DNS-Dienst erkannt'}</span></div>`;
  const netOf = ip => { if (!ip || !/^\d+\.\d+\.\d+\.\d+$/.test(ip)) return null; const n = ip2int(ip); return I.subnets.find(x => n - ip2int(x.first) >= 0 && n - ip2int(x.first) < x.size) || null; };
  const groups = [...I.subnets.filter(x => ipamNet === 'all' || x.vlan_id === ipamNet).map(x => [x, rows.filter(r => netOf(r.value) === x)]),
    ...(ipamNet === 'all' ? [[null, rows.filter(r => !netOf(r.value))]] : [])].filter(([, rs]) => rs.length);
  if (!I.records.length) h += '<div class="hint">Die OPNsense liefert keine DNS-Einträge (Unbound: Host-Overrides, Dnsmasq: Hosts).</div>';
  else if (!groups.length) h += '<div class="hint">In diesem Netz gibt es keine DNS-Einträge' + (ipamDnsFilter === 'hints' ? ' mit Hinweis' : '') + '.</div>';
  else h += '<div class="tw"><table class="t idns"><tr><th>Status</th><th>Name</th><th>Typ</th><th>Ziel</th><th>Gerät</th><th>Quelle</th><th></th></tr>' + groups.map(([net, rs]) =>
    `<tr class="grp"><td colspan="7" style="--c:${esc(net ? net.color || '#8d9aab' : 'var(--faint)')}"><i></i>${net ? `${esc(net.name)} <span class="mono">${esc(net.subnet)}</span>` : 'Ohne dokumentiertes Netz'}<span class="muted"> · ${rs.length}</span></td></tr>` + rs.map(r => {
    const [t, cls] = DNS_ST[r.status] || ['', ''];
    const act = !can || !r.uuid ? '' : (r.status === 'moved' ? `<button class="btn sm pri" data-act="ipamDnsSet" data-u="${esc(r.uuid)}" data-ip="${esc(r.suggest.ip)}">auf ${esc(r.suggest.ip)} ändern</button>` : '') +
      `<button class="btn sm bad" data-act="ipamDnsDel" data-u="${esc(r.uuid)}" data-n="${esc(r.fqdn)}" aria-label="${esc(r.fqdn)} löschen">Löschen</button>`;
    const dev = r.devs.length ? r.devs.map(d => `<a href="#" data-act="show" data-id="${d.id}">${esc(d.name)}</a>`).join(', ') : r.suggest ? `<span class="muted">${esc(r.suggest.name)} hat ${esc(r.suggest.ip)}</span>` : '<span class="muted">–</span>';
    return `<tr class="${r.status}"><td>${t ? `<span class="st ${cls}">${t}</span>` : ''}</td><td class="mono">${esc(r.fqdn)}</td><td>${esc(r.rr)}</td>` +
      `<td class="mono">${r.rr === 'A' && r.value ? `<a href="#" data-act="ipamCellOpen" data-ip="${esc(r.value)}">${esc(r.value)}</a>` : esc(r.value)}</td><td>${dev}</td><td>${SRC[r.src] || r.src}</td><td class="ra">${act}</td></tr>`;
  }).join('')).join('') + '</table></div>';
  const missing = I.missing.filter(m => ipamNet === 'all' || (netOf(m.ip) || {}).vlan_id === ipamNet);
  h += `<h3 class="imh">Geräte ohne DNS-Eintrag <span class="muted">(${missing.length})</span></h3>`;
  if (!missing.length) return h + '<div class="hint">Jedes dokumentierte Gerät mit IP-Adresse' + (ipamNet === 'all' ? '' : ' in diesem Netz') + ' hat einen DNS-Eintrag.</div>';
  for (const id of [...ipamPick]) if (!missing.some(m => m.id === id)) ipamPick.delete(id);
  h += '<div class="tw"><table class="t imiss"><tr>' + (can ? `<th><input type="checkbox" data-act="ipamPickAll"${ipamPick.size === missing.length ? ' checked' : ''} aria-label="alle auswählen"></th>` : '') +
    '<th>Gerät</th><th>Adresse</th><th>Name im DNS</th><th>Hinweis</th></tr>' + missing.map(m =>
      `<tr>${can ? `<td><input type="checkbox" data-act="ipamPick" data-id="${m.id}"${ipamPick.has(m.id) ? ' checked' : ''} aria-label="${esc(m.name)} auswählen"></td>` : ''}` +
      `<td><a href="#" data-act="show" data-id="${m.id}">${esc(m.name)}</a></td><td class="mono">${esc(m.ip)}</td>` +
      `<td>${can ? `<input class="iname" data-id="${m.id}" value="${esc(ipamNames[m.id] ?? m.suggest)}" spellcheck="false">` : esc(m.suggest)}<span class="muted">.${esc(ipamNames._dom ?? I.domain)}</span></td>` +
      `<td class="muted">${m.dhcp_name ? `meldet sich per DHCP als „${esc(m.dhcp_name)}“` : ''}</td></tr>`).join('') + '</table></div>';
  if (can) h += `<div class="ibulk"><button class="btn pri" data-act="ipamDnsAdd"${ipamPick.size ? '' : ' disabled'}>${ipamPick.size ? `${ipamPick.size} DNS-Einträge anlegen` : 'Geräte auswählen'}</button>` +
    `<span class="muted">Legt A-Einträge in ${I.dns_target ? SRC[I.dns_target] : '–'} an und lädt den Dienst neu.</span></div>`;
  return h;
}
function ipamCellPanel(ip) {
  ipamCellIp = ip;
  const [s, c] = ipamCell(ip), can = ipamCan();
  const row = (k, v) => v ? `<div class="kv"><span>${k}</span><div>${v}</div></div>` : '';
  const mac = c && ((c.devs.length && (dev(c.devs[0].id) || {}).mac) || (c.arp && c.arp.mac) || (c.lease && c.lease.mac) || (c.res && c.res.mac)) || '';
  let h = `<div class="phead"><h2 class="mono">${esc(ip)}</h2>${closeBtn}</div>`;
  h += `<p class="muted" style="margin:0 0 12px">${s ? `${esc(s.name)} · ${esc(s.subnet)}` : 'außerhalb der dokumentierten Netze'}${c && c.pool ? ' · im DHCP-Bereich' : ''}</p>`;
  if (!c) h += '<div class="hint">Frei – kein Gerät, keine Reservierung, kein DNS-Eintrag und nicht im Netz gesehen.</div>';
  else {
    h += row('Gerät', c.devs.map(d => `<a href="#" data-act="show" data-id="${d.id}">${esc(d.name)}</a>${d.primary ? '' : ` <span class="muted">(weitere Adresse${d.label ? ': ' + esc(d.label) : ''})</span>`}`).join('<br>') || (c.gw ? 'Gateway des Netzes' : '<span class="muted">nicht dokumentiert</span>'));
    h += row('DNS', c.dns.map(esc).join('<br>') || '<span class="muted">kein Eintrag</span>');
    h += row('Reservierung', c.res ? `${esc(c.res.mac)}${c.res.hostname ? ' · ' + esc(c.res.hostname) : ''} <span class="muted">(${SRC[c.res.src]})</span>` +
      (can && c.res.uuid ? ` <button class="btn sm bad" data-act="ipamResDel" data-u="${esc(c.res.uuid)}" data-ip="${esc(ip)}">Löschen</button>` : '') : '');
    h += row('Lease', c.lease ? `${esc(c.lease.mac)}${c.lease.hostname ? ' · ' + esc(c.lease.hostname) : ''} · ${c.lease.static ? 'fest' : 'dynamisch'}${c.lease.active ? '' : ' · abgelaufen'}` : '');
    h += row('ARP', c.arp ? `${esc(c.arp.mac)}${c.arp.vendor ? ' · ' + esc(c.arp.vendor) : ''}${c.arp.hostname ? ' · ' + esc(c.arp.hostname) : ''}${c.arp.intf ? ' · ' + esc(c.arp.intf) : ''}` : '');
    h += c.issues.map(i => `<div class="iss bad" style="margin-top:8px"><span>${esc(i[1])}</span></div>`).join('');
  }
  const acts = [];
  if (!ro() && c && c.moved) acts.push(`<button class="btn pri" data-act="ipamMove" data-id="${c.moved.id}" data-ip="${esc(ip)}">${esc(c.moved.name)} auf diese Adresse setzen</button>`);
  if (!ro() && (!c || !c.devs.length) && !(c && c.gw) && !(c && c.moved)) acts.push(`<button class="btn" data-act="ipamNewDev" data-ip="${esc(ip)}">Als Gerät anlegen</button>`);
  if (can && IPAM.dns_target && (!c || !c.dns.length)) acts.push(`<button class="btn" data-act="ipamDnsOne" data-ip="${esc(ip)}">DNS-Eintrag anlegen</button>`);
  if (can && IPAM.dhcp_target && c && !c.res && mac && !c.gw) acts.push(`<button class="btn" data-act="ipamResAdd" data-ip="${esc(ip)}" data-mac="${esc(mac)}">DHCP-Reservierung anlegen</button>`);
  if (acts.length) h += `<div class="acts" style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">${acts.join('')}</div>`;
  if (!can && !ro() && c && !IPAM.write) h += '<p class="muted" style="font-size:12.5px;margin-top:14px">DNS-Einträge und Reservierungen lassen sich anlegen, sobald in der OPNsense-Anbindung Änderungen erlaubt sind.</p>';
  openPanel(h, 'ipam');
  main.querySelectorAll('.ic.sel').forEach(n => n.classList.remove('sel'));
  const n = main.querySelector(`.ic[data-ip="${ip}"]`); if (n) n.classList.add('sel');
}
const ipamDevName = (ip, c) => { const x = c && c.devs[0] && dev(c.devs[0].id); return x ? (x.hostname || x.name) : (c && ((c.lease && c.lease.hostname) || (c.arp && c.arp.hostname) || (c.res && c.res.hostname))) || ''; };
const ipamSlug = s => (s || '').toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss').split('.')[0].replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 63);
main.addEventListener('input', e => {
  if (e.target.id === 'ipamDom') { ipamNames._dom = e.target.value.trim(); main.querySelectorAll('.imiss .muted').forEach(n => { if (n.textContent.startsWith('.')) n.textContent = '.' + ipamNames._dom; }); }
  else if (e.target.classList.contains('iname')) ipamNames[+e.target.dataset.id] = e.target.value.trim();
});
// ---------- eigene Links im Seitenmenü: mit oder ohne Kategorie, Kategorien einklappbar (je Browser gemerkt)
const NAV_LINK_ICO = '<svg class="ni" viewBox="0 0 24 24" aria-hidden="true"><path d="M10 14a4 4 0 0 0 5.700 0l3-3a4 4 0 0 0-5.700-5.700l-1 1M14 10a4 4 0 0 0-5.700 0l-3 3a4 4 0 0 0 5.700 5.700l1-1"/></svg>';
const navClosed = v => { try { if (v === undefined) return JSON.parse(localStorage.getItem('homeatlas.navgrp') || '[]'); localStorage.setItem('homeatlas.navgrp', JSON.stringify(v)); } catch (e) { /* ohne Speicher bleibt alles offen */ } return []; };
const navGroups = () => { const g = new Map(); for (const l of S.navlinks || []) { const k = l.grp || ''; if (!g.has(k)) g.set(k, []); g.get(k).push(l); } return [...g.entries()].sort((a, b) => (a[0] === '') - (b[0] === '') || a[0].localeCompare(b[0])); };
function renderNavLinks() {
  const closed = navClosed(), link = l => `<a href="${esc(l.url)}" target="_blank" rel="noopener noreferrer" title="${esc(l.label)} – ${esc(l.url)}">` +
    (l.icon ? `<img src="${iconUrl(l.icon)}" alt="">` : NAV_LINK_ICO) + `<span class="nl">${esc(l.label)}</span>` +
    '<svg class="ext ni" viewBox="0 0 24 24" aria-hidden="true"><path d="M14 5h5v5M19 5l-8 8M11 7H6v11h11v-5"/></svg></a>';
  let h = '';
  for (const [g, ls] of navGroups().sort((a, b) => (b[0] === '') - (a[0] === ''))) {
    if (!g) { h += ls.map(link).join(''); continue; }
    const open = !closed.includes(g);
    h += `<button class="grp" data-grp="${esc(g)}" aria-expanded="${open}"><span>${esc(g)}</span><span class="cnt">${ls.length}</span>` +
      `<svg class="chev ni" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg></button><div class="sub"${open ? '' : ' hidden'}>${ls.map(link).join('')}</div>`;
  }
  if (S.role !== 'read') h += `<button class="tool" data-act="navEdit" title="Links im Menü bearbeiten"><svg class="ni" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg><span class="nl">${(S.navlinks || []).length ? 'Links bearbeiten' : 'Link hinzufügen'}</span></button>`;
  if ($('#navlinks').innerHTML !== h) $('#navlinks').innerHTML = h;
}
$('#navlinks').addEventListener('click', e => {
  const g = e.target.closest('.grp');
  if (g) { const c = new Set(navClosed()), k = g.dataset.grp; c.has(k) ? c.delete(k) : c.add(k); navClosed([...c]); renderNavLinks(); }
  else if (e.target.closest('a,.tool')) navDrawer(false);
});
function navEditPanel() {
  const row = l => `<div class="rowl">${l.icon ? `<img src="${iconUrl(l.icon)}" alt="">` : NAV_LINK_ICO}<div style="min-width:0;flex:1"><b>${esc(l.label)}</b><small>${esc(l.url)}</small></div>` +
    `<button class="btn sm" data-act="editNav" data-id="${l.id}">Ändern</button><button class="btn sm danger" data-act="delNav" data-id="${l.id}" aria-label="${esc(l.label)} löschen">×</button></div>`;
  sel = null;
  openPanel(`<div class="phead"><h2>Links im Menü</h2>${closeBtn}</div><div class="navedit"><p class="muted" style="margin:0 0 10px">Schnellzugriff auf Weboberflächen, z. B. Radarr oder das IPMI. ` +
    `Links mit derselben Kategorie stehen im Menü als aufklappbare Gruppe; sie öffnen in einem neuen Tab.</p><button class="btn pri" data-act="newNav">+ Link</button>` +
    (navGroups().sort((a, b) => (b[0] === '') - (a[0] === '')).map(([g, ls]) => `<h3>${g ? esc(g) : 'Ohne Kategorie'}</h3>` + ls.map(row).join('')).join('') || '<div class="hint" style="margin-top:12px">Noch keine Links.</div>') + '</div>', 'nav');
}
let navBack = false, ipamBack = null;
function navForm(l) {
  const isNew = !l.id, withUrl = S.devices.filter(d => d.url && /^https?:\/\//i.test(d.url)).sort((a, b) => a.name.localeCompare(b.name));
  openForm(isNew ? 'Neuer Link' : esc(l.label), [
    ...(isNew && withUrl.length ? [['pick', 'Aus einem Gerät übernehmen', 'select', [['', '– von Hand eintragen –'], ...withUrl.map(d => [d.id, `${d.name} · ${d.url}`])]]] : []),
    ['label', 'Bezeichnung', 'text', 'z. B. Radarr'], ['url', 'Adresse', 'url', 'https://…'], ['grp', 'Kategorie (leer = direkt im Menü)', 'text', 'z. B. Medien, Verwaltung'],
    ['icon', 'Icon'], ['sort', 'Reihenfolge (kleinere Zahl steht weiter oben)', 'number'],
  ], {sort: 0, ...l}, async data => {
    delete data.pick;
    if (!data.label || !data.url) throw new Error('Bezeichnung und Adresse fehlen');
    data.sort = +data.sort || 0;
    if (isNew) await api('POST', '/api/navlinks', data); else await api('PUT', '/api/navlinks/' + l.id, data);
    await load(true); navBack = false; setTimeout(navEditPanel, 0);
  });
  const f = $('form', panel), groups = navGroups().map(g => g[0]).filter(Boolean);
  $('[name=grp]', f).setAttribute('list', 'navgrplist');
  f.insertAdjacentHTML('beforeend', `<datalist id="navgrplist">${groups.map(g => `<option value="${esc(g)}">`).join('')}</datalist>`);
  navBack = true;
  if ($('[name=pick]', f)) $('[name=pick]', f).addEventListener('change', e => {
    const d = dev(+e.target.value); if (!d) return;
    $('[name=label]', f).value = d.name; $('[name=url]', f).value = d.url; $('[name=icon]', f).value = d.icon || '';
    $('[name=icon]', f).dispatchEvent(new Event('input', {bubbles: true}));
  });
}
const READ_OK = new Set(['goTypes', 'ipamTab', 'ipamNet', 'ipamDnsFilter', 'ipamCellOpen', 'ipamCopy', 'ipamShow', 'monArea', 'viewMode', 'close', 'cancel', 'show', 'goFinds', 'fit', 'vfilter', 'svgExport', 'logout', 'netMode', 'netSort', 'netCsv', 'jump']);
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
