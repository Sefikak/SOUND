"use strict";
window.__errors = [];  // tanılama: yakalanmamış hatalar
addEventListener("error", e => __errors.push(`${e.message} @${e.lineno}`));
addEventListener("unhandledrejection", e => __errors.push("promise: " + (e.reason && e.reason.message || e.reason)));
/* SOUND arayüzü. Python tarafı: window.pywebview.api (webapp.py → Api). Python'dan gelen bildirimler: SOUND.receive */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const clock = s => { s = Math.max(0, Math.floor(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
const longTime = s => { const m = Math.floor((s || 0) / 60), h = Math.floor(m / 60); return h ? `${h} sa ${m % 60} dk` : `${m} dk`; };
const short = (s, n) => (s = String(s ?? "")).length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;
const num = n => n == null ? "" : n >= 1e9 ? (n / 1e9).toFixed(1).replace(".0", "") + " Mr" : n >= 1e6 ? (n / 1e6).toFixed(1).replace(".0", "") + " Mn" : n >= 1e3 ? Math.round(n / 1e3) + " B" : String(n);
const sleep = ms => new Promise(r => setTimeout(r, ms));
let api = null;

/* ---------- simgeler ---------- */
const svg = (body, attrs = 'fill="currentColor"') => `<svg viewBox="0 0 24 24" ${attrs}>${body}</svg>`;
const stroke = (body, w = 2.2) => svg(body, `fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"`);
const I = {
  play: svg('<path d="M7 4.5v15l13-7.5z"/>'),
  pause: svg('<path d="M6 4h4.5v16H6zm7.5 0H18v16h-4.5z"/>'),
  prev: svg('<path d="M6 5h2v14H6zM20 5v14L9 12z"/>'),
  next: svg('<path d="M16 5h2v14h-2zM4 5v14l11-7z"/>'),
  shuffle: stroke('<path d="M3 7h3c5 0 7 10 12 10h3m0 0-3-3m3 3-3 3M3 17h3c1.6 0 2.8-1 3.8-2.4M21 7h-3c-1.6 0-2.8 1-3.8 2.4M21 7l-3-3m3 3-3 3"/>', 2),
  repeat: stroke('<path d="M17 3l3 3-3 3M4 11V9a3 3 0 0 1 3-3h13M7 21l-3-3 3-3m13-2v2a3 3 0 0 1-3 3H4"/>', 2),
  repeatOne: stroke('<path d="M17 3l3 3-3 3M4 11V9a3 3 0 0 1 3-3h13M7 21l-3-3 3-3m13-2v2a3 3 0 0 1-3 3H4"/><path d="M11 10.5 12.5 9.5v5" stroke-width="1.8"/>', 2),
  heart: svg('<path d="M12 21s-8-5-8-11.5A4.5 4.5 0 0 1 12 6.6a4.5 4.5 0 0 1 8 2.9C20 16 12 21 12 21z"/>'),
  heartO: stroke('<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>', 2),
  download: stroke('<circle cx="12" cy="12" r="9"/><path d="M12 7.5v8m-3.5-3.5 3.5 3.5 3.5-3.5"/>', 1.8),
  downloaded: svg('<circle cx="12" cy="12" r="10"/><path d="M12 7v8m-3.5-3.5L12 15l3.5-3.5" fill="none" stroke="#121212" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'),
  more: svg('<circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/>'),
  close: stroke('<path d="M6 6l12 12M18 6 6 18"/>', 2.2),
  plus: stroke('<path d="M12 5v14M5 12h14"/>', 2.4),
  queue: stroke('<path d="M4 6h12M4 12h12M4 18h8M18 15v6l4-3z"/>', 2),
  volume: stroke('<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16 9a4 4 0 0 1 0 6m2.5-8.5a7.5 7.5 0 0 1 0 11"/>', 2),
  volumeLow: stroke('<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16 9a4 4 0 0 1 0 6"/>', 2),
  mute: stroke('<path d="M4 9v6h4l5 4V5L8 9z"/><path d="m16 9 5 6m0-6-5 6"/>', 2),
  folder: svg('<path d="M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
  note: svg('<path d="M9 18V5l11-2v13" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>'),
  chevron: stroke('<path d="m9 6 6 6-6 6"/>', 2.4),
  down: stroke('<path d="m6 9 6 6 6-6"/>', 2.4),
  refresh: stroke('<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>', 2.2),
  search: stroke('<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>', 2.2),
  video: stroke('<rect x="3" y="5" width="14" height="14" rx="2"/><path d="m17 10 4-3v10l-4-3"/>', 2),
  music: stroke('<path d="M9 18V5l11-2v13"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>', 2),
  undo: stroke('<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>', 2.4),
  minus: stroke('<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>', 2),
  radio: stroke('<circle cx="12" cy="12" r="2"/><path d="M16.2 7.8a6 6 0 0 1 0 8.4M7.8 16.2a6 6 0 0 1 0-8.4M19 5a10 10 0 0 1 0 14M5 19A10 10 0 0 1 5 5"/>', 2),
  user: stroke('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>', 2),
  external: stroke('<path d="M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>', 2),
  check: stroke('<path d="m5 12 5 5 9-10"/>', 2.6),
  spinner: stroke('<path d="M12 3a9 9 0 1 0 9 9" />', 2.6).replace("<svg", '<svg class="spin"'),
};
const PH = "data:image/svg+xml;utf8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#282828"/></svg>');
const TILE_COLORS = ["#6d4ae0", "#0f766e", "#b45309", "#be185d", "#1d4ed8", "#7c3aed", "#047857", "#c2410c", "#9333ea", "#0e7490"];

function tileColor(key) {
  let h = 0;
  for (const c of String(key)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return TILE_COLORS[h % TILE_COLORS.length];
}
function tile(key, size, icon, color, radius = 6) {
  color = color || tileColor(key);
  return `<div class="tile" style="width:${size}px;height:${size}px;border-radius:${radius}px;background:linear-gradient(135deg, color-mix(in srgb, ${color} 80%, white), ${color} 45%, color-mix(in srgb, ${color} 55%, black))">${icon}</div>`;
}
function videoId(item) {
  if (!item) return null;
  if (item.kind === "playlist") { const m = /\/vi\/([\w-]{11})\//.exec(item.thumbnail || ""); return m && m[1]; }
  return item.id;
}
const squareArt = item => item && /googleusercontent\.com|ggpht\.com/.test(item.thumbnail || "");
const thumb = item => {
  const v = item && item.kind !== "playlist" ? item.id : null;
  if (v) return `/thumb/${v}` + (squareArt(item) ? `?src=${encodeURIComponent(item.thumbnail)}` : "");
  if (squareArt(item)) return item.thumbnail;  // YouTube Music albümü
  const pv = videoId(item);
  return pv ? `/thumb/${pv}` : (item && item.thumbnail) || PH;
};
const bigThumb = item => squareArt(item) ? item.thumbnail.replace(/=w\d+-h\d+/, "=w800-h800") : `https://i.ytimg.com/vi/${videoId(item)}/hqdefault.jpg`;
document.addEventListener("error", e => {
  const img = e.target;
  if (img.tagName !== "IMG" || img.dataset.failed) return;
  img.dataset.failed = 1;
  img.classList.remove("hq");
  img.src = img.dataset.fallback || PH;
}, true);

/* ---------- durum ---------- */
const S = {
  lib: null, favSet: new Set(), dl: { progress: {}, active: [], failed: [] },
  home: { sections: [], loading: false, error: null },
  page: { kind: "home", ref: null }, back: [], fwd: [],
  search: { query: "", loading: false, tracks: [], videos: [], albums: [], artists: [], error: null, token: 0 },
  artists: {}, artistErrors: {},
  lists: {}, views: {}, playlists: {}, playlistErrors: {}, plShown: {},
  expanded: new Set(JSON.parse(localStorage.getItem("expanded") || "[]")),
  signature: null, sideSignature: null, info: {}, infoLoading: new Set(),
  panelOpen: false, panelMode: "cover", browsers: [], session: {}, settings: {},
};
const SORTS = [["custom", "Varsayılan sıra"], ["title", "Ada göre"], ["artist", "Sanatçıya göre"], ["duration", "Süreye göre"], ["recent", "Son eklenen"]];

const L = {
  t: id => S.lib.tracks[id],
  fav: id => S.favSet.has(id),
  dl: id => !!(S.lib.tracks[id] && S.lib.tracks[id].file),
  video: id => S.lib.tracks[id] && S.lib.tracks[id].video_file,
  favTracks: () => S.lib.favorites.map(L.t).filter(Boolean),
  dlTracks: () => Object.values(S.lib.tracks).filter(t => t.file).sort((a, b) => (b.downloaded_at || 0) - (a.downloaded_at || 0)),
  album: id => S.lib.albums[id],
  albumTracks: id => (S.lib.albums[id]?.tracks || []).map(L.t).filter(Boolean),
  albums: folder => Object.entries(S.lib.albums).filter(([, a]) => (a.folder || null) === folder).sort((a, b) => a[1].created - b[1].created),
  allAlbums: () => Object.entries(S.lib.albums).sort((a, b) => a[1].name.localeCompare(b[1].name, "tr")),
  folders: () => Object.entries(S.lib.folders).sort((a, b) => a[1].created - b[1].created),
  albumBySource: src => (Object.entries(S.lib.albums).find(([, a]) => a.source === src) || [])[0],
  recent: () => S.lib.recent.map(L.t).filter(Boolean),
};
const plain = t => ({ id: t.id, title: t.title, artist: t.artist, duration: t.duration, thumbnail: t.thumbnail, url: t.url });
const dlKey = (id, kind) => kind === "video" ? `${id}:video` : id;
const busy = key => key in S.dl.progress;

/* ---------- bildirim, menü, pencereler ---------- */
let toastTimer = null;
function toast(message, error = false) {
  const el = $("#toast");
  el.textContent = message;
  el.className = "show" + (error ? " error" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.className = error ? "error" : "", 2800);
}

let openMenus = [];
function closeMenus() { openMenus.forEach(m => m.remove()); openMenus = []; }
function menu(items, x, y, level = 0) {
  if (level === 0) closeMenus();
  openMenus.slice(level).forEach(m => m.remove());
  openMenus = openMenus.slice(0, level);
  const el = document.createElement("div");
  el.className = "menu";
  items.forEach(item => {
    if (item === "-") { el.appendChild(document.createElement("hr")); return; }
    const row = document.createElement("div");
    row.className = "mi" + (item.danger ? " danger" : "") + (item.checked ? " checked" : "");
    row.innerHTML = `<span>${esc(item.label)}</span>${item.sub ? I.chevron : ""}`;
    if (item.sub) {
      row.addEventListener("mouseenter", () => {
        $$(".mi.open", el).forEach(m => m.classList.remove("open"));
        row.classList.add("open");
        const r = row.getBoundingClientRect();
        menu(item.sub, r.right - 2, r.top - 4, level + 1);
      });
    } else {
      row.addEventListener("mouseenter", () => { $$(".mi.open", el).forEach(m => m.classList.remove("open")); openMenus.slice(level + 1).forEach(m => m.remove()); openMenus = openMenus.slice(0, level + 1); });
      row.addEventListener("click", e => { e.stopPropagation(); closeMenus(); item.act && item.act(); });
    }
    el.appendChild(row);
  });
  document.body.appendChild(el);
  const r = el.getBoundingClientRect();
  x = Math.max(8, x);
  if (x + r.width > innerWidth - 8) x = level ? x - r.width - (openMenus[level - 1]?.offsetWidth || 0) + 4 : innerWidth - r.width - 8;
  if (y + r.height > innerHeight - 8) y = Math.max(8, innerHeight - r.height - 8);
  el.style.left = x + "px";
  el.style.top = y + "px";
  openMenus.push(el);
  return el;
}
const menuAt = (items, el) => { const r = el.getBoundingClientRect(); menu(items, r.left, r.bottom + 4); };
document.addEventListener("pointerdown", e => { if (openMenus.length && !e.target.closest(".menu")) closeMenus(); }, true);
addEventListener("blur", closeMenus);

function modal(html, setup, cls = "") {
  return new Promise(resolve => {
    const back = document.createElement("div");
    back.id = "modal";
    if (cls) back.className = cls;
    back.innerHTML = `<div class="dialog">${html}</div>`;
    document.body.appendChild(back);
    const done = value => { back.remove(); document.removeEventListener("keydown", key, true); resolve(value); };
    const key = e => { if (e.key === "Escape") { e.stopPropagation(); done(null); } };
    document.addEventListener("keydown", key, true);
    back.addEventListener("pointerdown", e => { if (e.target === back) done(null); });
    setup($(".dialog", back), done);
  });
}
function ask(title, label, value = "") {
  return modal(`<h3>${esc(title)}</h3><p>${esc(label)}</p><input class="text" value="${esc(value)}" maxlength="80">
    <div class="row-btns"><button class="textbtn" data-x="cancel">Vazgeç</button><button class="pill fill" data-x="ok">Kaydet</button></div>`,
    (box, done) => {
      const input = $("input", box);
      input.focus(); input.select();
      const ok = () => { const v = input.value.trim(); done(v || null); };
      input.addEventListener("keydown", e => { if (e.key === "Enter") ok(); });
      $('[data-x="ok"]', box).onclick = ok;
      $('[data-x="cancel"]', box).onclick = () => done(null);
    });
}
function confirmBox(title, text, yes = "Sil") {
  return modal(`<h3>${esc(title)}</h3><p>${esc(text)}</p>
    <div class="row-btns"><button class="textbtn" data-x="no">Vazgeç</button><button class="pill accent" data-x="yes">${esc(yes)}</button></div>`,
    (box, done) => {
      $('[data-x="yes"]', box).onclick = () => done(true);
      $('[data-x="no"]', box).onclick = () => done(false);
      $('[data-x="yes"]', box).focus();
    });
}

/* ---------- YouTube hesabı ---------- */
let accountOpen = false;
async function openAccount(reason = null, onConnected = null) {
  if (accountOpen) return;
  accountOpen = true;
  const status = await api.auth_status();
  await modal(`<h3>YouTube hesabını bağla</h3>${reason ? `<p class="reason">${esc(reason)}</p>` : ""}
    <p>Yaş doğrulaması isteyen şarkılar için YouTube'a giriş yaptığın tarayıcıyı seç. Hesabının yaşı YouTube'da doğrulanmış olmalı.
    Oturum bilgileri bu bilgisayarda kalır ve yalnızca YouTube'a gönderilir.</p>
    <div class="browsers">${S.browsers.map(([k, n]) => `<button class="pill" data-b="${k}">${esc(n)}</button>`).join("")}</div>
    <button class="pill" data-x="file">cookies.txt dosyası seç…</button>
    <small style="margin-top:6px">cookies.txt: tarayıcına “Get cookies.txt LOCALLY” eklentisini kur, youtube.com'da giriş yapmışken dışa aktar ve buradan seç.</small>
    <div class="status">${esc(status)}</div>
    <div class="row-btns"><button class="textbtn" data-x="clear">Bağlantıyı kaldır</button><button class="pill fill" data-x="close">Kapat</button></div>`,
    (box, done) => {
      const st = $(".status", box);
      const show = (text, cls = "") => { st.textContent = text; st.className = "status " + cls; };
      const finish = (res, name) => {
        if (!res) return;
        if (res.ok) {
          show(`✓ ${name} bağlandı. ${res.message}`, "ok");
          toast("YouTube hesabı bağlandı");
          if (onConnected) setTimeout(() => { done(true); onConnected(); }, 800);
        } else show(`${name}: ${res.message}`, "err");
      };
      $$("[data-b]", box).forEach(b => b.onclick = async () => {
        const name = b.textContent;
        show(`${name} kontrol ediliyor…`);
        finish(await api.auth_browser(b.dataset.b), name);
      });
      $('[data-x="file"]', box).onclick = async () => finish(await api.auth_file(), "cookies.txt");
      $('[data-x="clear"]', box).onclick = async () => show(await api.auth_clear());
      $('[data-x="close"]', box).onclick = () => done(null);
    });
  accountOpen = false;
}

/* ---------- ayarlar ---------- */
let settingsBox = null;
function toggleHTML(key, on) { return `<button class="switch ${on ? "on" : ""}" data-set="${key}"><i></i></button>`; }
async function openSettings() {
  let st = await api.settings();
  let ver = await api.app_version();
  await modal(`<h3>Ayarlar</h3><div id="setBody"></div>
    <div class="row-btns" style="margin-top:18px"><button class="pill fill" data-x="close">Kapat</button></div>`, (box, done) => {
    settingsBox = box;
    const mb = n => n >= 1024 ? (n / 1024).toFixed(1).replace(".0", "") + " GB" : Math.round(n) + " MB";
    const draw = () => {
      const s = st.settings;
      $("#setBody", box).innerHTML = `
        <div class="set-sec">Kişiselleştir</div>
        <div class="set-row"><div><b>Görünüm ve yerleşim</b><p>Renkler, alev, boyut, kenar çubuğunun ve düğmelerin yeri.</p></div><button class="pill" data-x="customize">Kişiselleştir</button></div>
        <div class="set-sec">Çalma</div>
        <div class="set-row"><div><b>Ekolayzır ve ses dengeleme</b><p>Sesi kendine göre ayarla; şarkılar arasındaki ses farkını gider.</p></div><button class="pill" data-x="audioFx">Aç</button></div>
        <div class="set-row"><div><b>Boşluksuz geçiş</b><p>Sıradaki şarkı önceden yüklenir, şarkılar arasında sessizlik olmaz.</p></div>${toggleHTML("gapless", s.gapless)}</div>
        <div class="set-row"><div><b>Şarkılar arası geçiş (crossfade)</b><p>Şarkı biterken sıradaki yavaşça açılır.</p></div>${toggleHTML("crossfade", s.crossfade)}</div>
        <div class="set-row"><div><b>Otomatik devam</b><p>Liste bitince benzer şarkılar çalmaya devam eder.</p></div>${toggleHTML("autoplay", s.autoplay !== false)}</div>
        <div class="set-row ${s.crossfade ? "" : "dim"}"><div><b>Geçiş süresi</b></div><div class="set-range"><input type="range" min="1" max="12" value="${s.crossfade_seconds}" data-range="crossfade_seconds" style="--v:${(s.crossfade_seconds - 1) / 11 * 100}%" ${s.crossfade ? "" : "disabled"}><span>${s.crossfade_seconds} sn</span></div></div>
        <div class="set-row"><div><b>En yüksek ses</b><p>Ses kaydırıcısı en sağdayken çıkacak ses. Kulaklıkta çok yüksek geliyorsa düşür.</p></div><div class="set-range"><input type="range" min="20" max="100" step="5" value="${s.max_volume ?? 100}" data-range="max_volume" data-unit="%" style="--v:${((s.max_volume ?? 100) - 20) / 80 * 100}%"><span>%${s.max_volume ?? 100}</span></div></div>
        <div class="set-sec">Depolama</div>
        <div class="set-row"><div><b>Dinleme önbelleği</b><p>Dinlediğin şarkılar burada saklanır; tekrar dinlemek anında başlar, internetsiz de çalar. Şu an ${mb(st.cache_bytes / 1048576)}.</p></div>
          <select data-select="cache_mb">${[500, 1000, 1500, 3000, 5000, 10000].map(v => `<option value="${v}" ${+s.cache_mb === v ? "selected" : ""}>${mb(v)}</option>`).join("")}</select></div>
        <div class="set-row"><div></div><button class="textbtn" data-x="clearCache">Önbelleği temizle</button></div>
        <div class="set-sec">İçe aktar</div>
        <div class="set-row"><div><b>YouTube Music</b><p>Hesabına giriş yap; kayıtlı listelerin albüm, beğendiğin şarkılar favori olarak eklenir. Zaten olanlar atlanır.</p></div><button class="pill" data-x="loginYtm">Giriş yap ve aktar</button></div>
        <div class="set-row"><div><b>Spotify</b><p>Hesap verisi dosyan ya da liste bağlantılarınla; beğenilenler ve listelerin YouTube Music'te bulunup eklenir.</p></div><button class="pill" data-x="importSpotify">Aktar</button></div>
        <div class="set-sec">Güncelleme</div>
        <div class="set-row"><div><b>Otomatik güncelle</b><p>${ver.git ? "GitHub'da yeni sürüm çıkınca SOUND kendini arka planda günceller; yeniden başlatınca etkin olur." : "Uygulama klasörü henüz bir GitHub deposuna bağlı değil."}</p></div>${toggleHTML("auto_update", s.auto_update !== false)}</div>
        <div class="set-row"><div><b>Sürüm</b><p>${esc(ver.version || "bilinmiyor")}${ver.pending ? " · yeni sürüm indirildi" : ""}</p></div>${ver.pending
          ? `<button class="pill accent" data-x="restart">Yeniden başlat</button>`
          : `<button class="pill" data-x="checkUpdate" ${ver.git ? "" : "disabled"}>Şimdi denetle</button>`}</div>
        <div class="set-sec">Hesap</div>
        <div class="set-row"><div><b>YouTube hesabı</b><p>Yaş doğrulaması isteyen şarkılar için.</p></div><button class="pill" data-x="account">Aç</button></div>`;
    };
    const save = async changes => { st = await api.update_settings(changes); S.settings = st.settings; setVolume(volPos, false); draw(); };
    box.addEventListener("click", async e => {
      const sw = e.target.closest("[data-set]");
      if (sw) {
        const k = sw.dataset.set, cur = k === "auto_update" ? st.settings[k] !== false : st.settings[k];
        return save({ [k]: !cur });
      }
      const x = e.target.closest("[data-x]")?.dataset.x;
      if (x === "close") done(null);
      else if (x === "clearCache") { st = await api.clear_cache(); draw(); toast("Önbellek temizlendi"); }
      else if (x === "account") { done(null); openAccount(); }
      else if (x === "customize") { done(null); openCustomize(); }
      else if (x === "audioFx") { done(null); openAudioFx(); }
      else if (x === "restart") api.restart_app();
      else if (x === "checkUpdate") {
        const b = e.target.closest("[data-x]");
        b.disabled = true; b.textContent = "Denetleniyor…";
        const r = await api.check_app_update();
        ver = await api.app_version(); draw();
        toast({ uptodate: "SOUND güncel", updated: "Yeni sürüm indirildi", dirty: "Yerelde kaydedilmemiş kod değişikliği var; güncelleme atlandı",
                diverged: "Yerelde gönderilmemiş değişiklikler var; güncelleme atlandı", unavailable: "GitHub deposu bağlı değil" }[r.status]
              || "Güncelleme denetlenemedi: " + (r.message || ""), !["uptodate", "updated"].includes(r.status));
      }
      else if (x === "loginYtm") { done(null); loginImport("ytmusic"); }
      else if (x === "importSpotify") { done(null); openSpotifyImport(); }
    });
    box.addEventListener("input", e => {
      const r = e.target.closest("[data-range]");
      if (r) {
        r.style.setProperty("--v", (r.value - r.min) / (r.max - r.min) * 100 + "%");
        r.nextElementSibling.textContent = r.dataset.unit === "%" ? "%" + r.value : r.value + " sn";
        if (r.dataset.range === "max_volume") { S.settings = { ...S.settings, max_volume: +r.value }; setVolume(volPos, false); }  // sürüklerken duyulsun
      }
    });
    box.addEventListener("change", e => {
      const r = e.target.closest("[data-range]"), sel = e.target.closest("[data-select]");
      if (r) save({ [r.dataset.range]: +r.value });
      if (sel) save({ [sel.dataset.select]: +sel.value });
    });
    settingsBox.refresh = async () => { st = await api.settings(); draw(); };
    draw();
  });
  settingsBox = null;
}

/* ---------- kişiselleştirme: renkler, alev, boyut, yerleşim, düğmeler ----------
   Ayarlar settings.ui içinde saklanır; açılışta beklemeden uygulanabilsin diye bir kopyası localStorage'da da durur. */
const UI_DEFAULTS = {
  accent: "#8b5cf6", bg: "dark", flame: "fire", glow: true,
  zoom: 100, radius: 10, side_w: 290, calm: false,
  side: "left", bar: "bottom", np: "left", ctrl: "center",
  shuffle_btn: true, repeat_btn: true, hist_btns: true, undo_btn: true,
};
const ACCENTS = [["#8b5cf6", "Mor"], ["#6366f1", "Çivit"], ["#3b82f6", "Mavi"], ["#06b6d4", "Camgöbeği"], ["#14b8a6", "Turkuaz"],
  ["#22c55e", "Yeşil"], ["#eab308", "Sarı"], ["#f97316", "Turuncu"], ["#ef4444", "Kırmızı"], ["#ec4899", "Pembe"], ["#d946ef", "Fuşya"]];
const BGS = {
  dark: ["Koyu", { bg: "#121212", black: "#000000", card: "#181818", raise: "#1f1f1f", raise2: "#232323", hover: "#262626" }],
  black: ["Siyah", { bg: "#050505", black: "#000000", card: "#0f0f0f", raise: "#161616", raise2: "#1a1a1a", hover: "#1d1d1d" }],
  gray: ["Gri", { bg: "#1e1e1e", black: "#0c0c0c", card: "#262626", raise: "#2c2c2c", raise2: "#303030", hover: "#353535" }],
  tint: ["Renkli", null],  // vurgu renginden türetilir
};
const FLAME_SETS = {
  fire: ["Ateş", null],
  accent: ["Vurgu rengi", null],
  ice: ["Buz", [[37, 99, 235], [34, 211, 238], [186, 245, 253]]],
  gold: ["Altın", [[194, 65, 12], [245, 158, 11], [254, 240, 138]]],
  toxic: ["Zehir", [[21, 128, 61], [132, 204, 22], [236, 252, 203]]],
  mono: ["Beyaz", [[82, 82, 91], [161, 161, 170], [244, 244, 245]]],
};
const FIRE = {
  l1: [[0, "rgba(124,58,237,.15)"], [0.25, "rgba(147,51,234,.6)"], [0.6, "rgba(236,72,153,.8)"], [1, "rgba(251,146,60,.9)"]],
  l2: [[0, "rgba(244,114,182,.2)"], [0.4, "rgba(244,114,182,.7)"], [1, "rgba(253,186,116,.95)"]],
  l3: [[0, "rgba(254,215,170,.3)"], [1, "rgba(255,251,235,1)"]],
  sp: ["#fff7ed", "#fdba74", "#f472b6"],
};
const WHITE = [255, 255, 255], BLACK = [0, 0, 0];
const hexRgb = h => { const n = parseInt(h.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; };
const mixRgb = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
const rgbHex = c => "#" + c.map(v => v.toString(16).padStart(2, "0")).join("");
const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
/* üç renkten (dip, gövde, uç) ateşle aynı katman düzeninde bir alev paleti */
function makeFlame([deep, mid, tip]) {
  const mid2 = mixRgb(mid, WHITE, 0.25), tip2 = mixRgb(tip, WHITE, 0.4);
  return {
    l1: [[0, rgba(deep, 0.15)], [0.25, rgba(deep, 0.6)], [0.6, rgba(mid, 0.8)], [1, rgba(tip, 0.9)]],
    l2: [[0, rgba(mid2, 0.2)], [0.4, rgba(mid2, 0.7)], [1, rgba(tip2, 0.95)]],
    l3: [[0, rgba(tip2, 0.3)], [1, "rgba(255,255,255,1)"]],
    sp: [rgbHex(mixRgb(tip, WHITE, 0.7)), rgbHex(tip), rgbHex(mid)],
  };
}
function buildFlame(key, accent) {
  if (key === "accent") { const a = hexRgb(accent); return makeFlame([mixRgb(a, BLACK, 0.3), a, mixRgb(a, WHITE, 0.55)]); }
  const c = FLAME_SETS[key]?.[1];
  return c ? makeFlame(c) : FIRE;
}
function flamePreview(key, accent) {
  const p = buildFlame(key, accent);
  return `linear-gradient(0deg, ${p.l3[1][1]} 0%, ${p.l2[2][1]} 22%, ${p.l1[2][1]} 55%, ${p.l1[1][1]} 82%, transparent 100%)`;
}
let flamePal = FIRE, appliedZoom = 100, appliedIcon = null, iconTimer = null;
const uiOpts = ui => {
  const u = { ...UI_DEFAULTS, ...(ui || {}) };
  if (!/^#[0-9a-f]{6}$/i.test(u.accent)) u.accent = UI_DEFAULTS.accent;
  u.accent = u.accent.toLowerCase();
  return u;
};
function applyUI(ui) {
  const u = uiOpts(ui), root = document.documentElement.style, app = $("#app"), body = document.body;
  const ar = hexRgb(u.accent), isDefault = u.accent === UI_DEFAULTS.accent;
  root.setProperty("--accent", u.accent);
  body.classList.toggle("tint-logo", !isDefault);  // logo da vurgu rengine bürünsün (varsayılan morda özgün resim)
  root.setProperty("--accent-light", isDefault ? "#b49bff" : rgbHex(mixRgb(ar, WHITE, 0.35)));
  root.setProperty("--accent-dark", isDefault ? "#6d28d9" : rgbHex(mixRgb(ar, BLACK, 0.25)));
  let bg = BGS[u.bg]?.[1];
  if (!bg) {
    const t = (base, p) => rgbHex(mixRgb(hexRgb(base), ar, p));
    bg = { bg: t("#121212", 0.07), black: t("#000000", 0.05), card: t("#181818", 0.08), raise: t("#1f1f1f", 0.1),
           raise2: t("#232323", 0.12), hover: t("#262626", 0.13) };
  }
  for (const [k, v] of Object.entries(bg)) root.setProperty(k === "hover" ? "--card-hover" : "--" + k, v);
  root.setProperty("--radius", u.radius + "px");
  root.setProperty("--side-w", u.side_w + "px");
  app.classList.toggle("side-right", u.side === "right");
  app.classList.toggle("bar-top", u.bar === "top");
  app.classList.toggle("np-right", u.np === "right");
  app.classList.toggle("ctrl-left", u.ctrl === "left");
  app.classList.toggle("ctrl-right", u.ctrl === "right");
  body.classList.toggle("hide-shuffle", !u.shuffle_btn);
  body.classList.toggle("hide-repeat", !u.repeat_btn);
  body.classList.toggle("hide-hist", !u.hist_btns);
  body.classList.toggle("hide-undo", !u.undo_btn);
  body.classList.toggle("hide-glow", !u.glow);
  body.classList.toggle("calm", !!u.calm);
  flamePal = buildFlame(u.flame, u.accent);
  // boyut: WebView'in kendi yakınlaştırması (CSS zoom menü konumlarını bozar)
  if (api && api.set_zoom && u.zoom !== appliedZoom) { appliedZoom = u.zoom; api.set_zoom(u.zoom / 100); }
  // uygulama ikonu (görev çubuğu, başlık): renk seçici sürüklenirken her adımda ikon üretmesin
  if (api && api.set_app_icon && u.accent !== appliedIcon) {
    appliedIcon = u.accent;
    clearTimeout(iconTimer);
    iconTimer = setTimeout(() => api.set_app_icon(u.accent), 400);
  }
  try { localStorage.setItem("sound.ui", JSON.stringify(u)); } catch { }
}
async function openCustomize() {
  let u = uiOpts(S.settings.ui), timer = null;
  const save = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => { S.settings = (await api.update_settings({ ui: u })).settings; }, 250);
  };
  const FMT = { zoom: v => "%" + v, radius: v => v + " px", side_w: v => v + " px" };
  await modal(`<h3>Kişiselleştir</h3><p style="margin-bottom:0">Değişiklikler hemen uygulanır ve kaydedilir.</p><div id="czBody"></div>
    <div class="row-btns" style="margin-top:18px"><button class="textbtn" data-x="reset">Varsayılana dön</button><button class="pill fill" data-x="close">Bitti</button></div>`,
    (box, done) => {
      const seg = (key, opts) => `<div class="seg">${opts.map(([v, label, chip]) =>
        `<button data-k="${key}" data-v="${v}" class="${u[key] === v ? "on" : ""}">${chip ? `<span class="chip" style="background:${chip};box-shadow:inset 0 0 0 1px #ffffff40"></span>` : ""}${label}</button>`).join("")}</div>`;
      const tog = key => `<button class="switch ${u[key] ? "on" : ""}" data-tog="${key}"><i></i></button>`;
      const range = (key, min, max, step) => `<div class="set-range"><input type="range" min="${min}" max="${max}" step="${step}" value="${u[key]}" data-rng="${key}" style="--v:${(u[key] - min) / (max - min) * 100}%"><span>${FMT[key](u[key])}</span></div>`;
      const row = (title, desc, ctrl) => `<div class="set-row"><div><b>${title}</b>${desc ? `<p>${desc}</p>` : ""}</div>${ctrl}</div>`;
      const draw = () => {
        const custom = !ACCENTS.some(([c]) => c === u.accent), ar = hexRgb(u.accent);
        $("#czBody", box).innerHTML = `
          <div class="set-sec">Renkler</div>
          ${row("Vurgu rengi", "Düğmeler, seçili öğeler, kaydırıcılar.", `<div class="cz-swatches">${ACCENTS.map(([c, n]) =>
            `<button class="cz-sw ${u.accent === c ? "on" : ""}" data-accent="${c}" title="${n}" style="background:${c}"></button>`).join("")}
            <label class="cz-sw custom ${custom ? "on" : ""}" title="Özel renk seç"><input type="color" data-color value="${u.accent}"></label></div>`)}
          ${row("Arka plan", "", seg("bg", Object.entries(BGS).map(([k, [n, c]]) => [k, n, c ? c.card : rgbHex(mixRgb([24, 24, 24], ar, 0.35))])))}
          <div class="set-row" style="border:0;padding-bottom:4px"><div><b>Alev rengi</b><p>İlerleme çubuğunda müziğe göre yanan alev.</p></div></div>
          <div class="cz-flames">${Object.entries(FLAME_SETS).map(([k, [n]]) =>
            `<button class="cz-flame ${u.flame === k ? "on" : ""}" data-k="flame" data-v="${k}"><i style="background:${flamePreview(k, u.accent)}"></i><span>${n}</span></button>`).join("")}</div>
          ${row("Kapak rengi parıltısı", "Sayfanın üstü açık albümün ya da şarkının kapak rengini alır.", tog("glow"))}
          <div class="set-sec">Görünüm</div>
          ${row("Arayüz boyutu", "Her şeyi büyütür ya da küçültür.", range("zoom", 80, 130, 5))}
          ${row("Köşe yuvarlaklığı", "", range("radius", 0, 20, 1))}
          ${row("Kenar çubuğu genişliği", "", range("side_w", 220, 400, 10))}
          ${row("Animasyonları azalt", "Geçiş ve açılma efektleri kapanır (alev çalışmaya devam eder).", tog("calm"))}
          <div class="set-sec">Yerleşim</div>
          ${row("Kenar çubuğu", "Menü ve kitaplık hangi tarafta dursun.", seg("side", [["left", "Solda"], ["right", "Sağda"]]))}
          ${row("Çalma çubuğu", "", seg("bar", [["bottom", "Altta"], ["top", "Üstte"]]))}
          ${row("Çalan şarkı bilgisi", "Kapak ve şarkı adı; ses ayarı karşı tarafa geçer.", seg("np", [["left", "Solda"], ["right", "Sağda"]]))}
          ${row("Çalma düğmeleri", "", seg("ctrl", [["left", "Sol"], ["center", "Orta"], ["right", "Sağ"]]))}
          <div class="set-sec">Düğmeler</div>
          ${row("Karıştır", "", tog("shuffle_btn"))}
          ${row("Tekrarla", "", tog("repeat_btn"))}
          ${row("Geri / ileri", "Üst çubuktaki sayfa geçmişi okları.", tog("hist_btns"))}
          ${row("Geri al (↶)", "Ctrl+Z gizliyken de çalışır.", tog("undo_btn"))}`;
      };
      const set = (k, v) => { u = { ...u, [k]: v }; applyUI(u); save(); draw(); };
      box.addEventListener("click", e => {
        const t = e.target.closest("[data-k],[data-tog],[data-accent],[data-x]");
        if (!t) return;
        if (t.dataset.k) set(t.dataset.k, t.dataset.v);
        else if (t.dataset.tog) set(t.dataset.tog, !u[t.dataset.tog]);
        else if (t.dataset.accent) set("accent", t.dataset.accent);
        else if (t.dataset.x === "close") done(null);
        else if (t.dataset.x === "reset") { u = { ...UI_DEFAULTS }; applyUI(u); save(); draw(); toast("Varsayılan görünüme dönüldü"); }
      });
      box.addEventListener("input", e => {
        const r = e.target.closest("[data-rng]");
        if (r) {
          const k = r.dataset.rng, v = +r.value;
          r.style.setProperty("--v", (v - r.min) / (r.max - r.min) * 100 + "%");
          r.nextElementSibling.textContent = FMT[k](v);
          u = { ...u, [k]: v };
          if (k !== "zoom") applyUI(u);  // boyut bırakınca uygulanır, sürüklerken pencere zıplamasın
        } else if (e.target.matches("[data-color]")) { u = { ...u, accent: e.target.value.toLowerCase() }; applyUI(u); }
      });
      box.addEventListener("change", e => {
        if (e.target.closest("[data-rng]")) { applyUI(u); save(); }
        else if (e.target.matches("[data-color]")) { save(); draw(); }
      });
      draw();
    }, "sheet");
}

/* ---------- içe aktarma ---------- */
async function startImport(source, links = "", files = []) {
  const res = await api.start_import(source, links, files);
  if (res.error) { toast(res.error, true); return false; }
  importProgress({ text: source === "ytmusic" ? "YouTube Music kitaplığın okunuyor…" : "Spotify listeleri okunuyor…" });
  return true;
}
async function loginImport(service, clientId = null) {
  const res = await api.login_import(service, clientId);
  if (res.setup) return spotifySetup();
  if (res.error) { toast(res.error, true); return; }
  toast(service === "spotify" ? "Spotify giriş penceresi açıldı; izin verince aktarma kendiliğinden başlar"
    : "Giriş penceresi açıldı; giriş yapınca aktarma kendiliğinden başlar");
}
/* Spotify resmi girişi bir "Client ID" ister: kullanıcı bir kez developer.spotify.com'da oluşturur */
function spotifySetup() {
  const redirect = "http://127.0.0.1:43117/callback";
  return modal(`<h3>Spotify girişi için bir kerelik kurulum</h3>
    <p>Spotify, hesabına bağlanan her uygulamadan bir “Client ID” istiyor. Spotify artık bunun için <b>Premium</b> hesap şartı koyuyor; Premium değilsen “Web API” kutusu seçilemez, o durumda dosya ya da bağlantıyla aktar.</p>
    <ol class="steps">
      <li><span class="link" data-x="dash">developer.spotify.com/dashboard</span>'a Spotify hesabınla gir, <b>Create app</b>'e bas.</li>
      <li>Ad ve açıklamaya istediğini yaz (ör. SOUND). <b>Redirect URI</b> olarak şunu ekle:
        <div class="copyline"><code>${redirect}</code><button class="textbtn" data-x="copy">Kopyala</button></div></li>
      <li><b>Web API</b>'yi işaretle, kaydet. Uygulamanın sayfasındaki <b>Client ID</b>'yi kopyala ve buraya yapıştır:</li>
    </ol>
    <input class="text" id="spClient" placeholder="Client ID" spellcheck="false" value="${esc(S.settings.spotify_client_id || "")}">
    <div class="row-btns"><button class="textbtn" data-x="cancel">Vazgeç</button><button class="pill fill" data-x="go">Giriş yap ve aktar</button></div>`,
    (box, done) => {
      const input = $("#spClient", box);
      input.focus();
      $('[data-x="dash"]', box).onclick = () => api.open_url("https://developer.spotify.com/dashboard");
      $('[data-x="copy"]', box).onclick = () => { navigator.clipboard.writeText(redirect); toast("Adres kopyalandı"); };
      $('[data-x="cancel"]', box).onclick = () => done(null);
      const go = async () => {
        const id = input.value.trim();
        if (!/^[0-9a-f]{32}$/i.test(id)) { toast("Client ID 32 karakterlik bir kod olmalı", true); return; }
        S.settings = (await api.update_settings({ spotify_client_id: id })).settings;
        done(true);
        loginImport("spotify", id);
      };
      $('[data-x="go"]', box).onclick = go;
      input.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
    });
}
function openSpotifyImport() {
  let files = [];
  return modal(`<h3>Spotify'dan aktar</h3>
    <p><b>Liste bağlantıları</b>: Spotify'da listede ⋯ › Paylaş › Bağlantıyı kopyala. Birden çok bağlantıyı alt alta yapıştırabilirsin.
    Spotify bu yolla liste başına en fazla 100 şarkı gösteriyor.</p>
    <textarea class="text" id="spLinks" rows="4" placeholder="https://open.spotify.com/playlist/…" spellcheck="false"></textarea>
    <p style="margin-top:14px"><b>Beğenilen şarkılar ve tüm listeler</b>: <span class="link" data-x="privacy">spotify.com › Hesap › Gizlilik</span> sayfasında
    “Hesap verileri”ni iste (birkaç gün içinde e-postayla gelir). Gelen <i>my_spotify_data.zip</i> dosyasını seç. Exportify'dan indirilen CSV dosyaları da olur.</p>
    <div style="display:flex;align-items:center;gap:10px"><button class="pill" data-x="files">Dosya seç…</button><span class="muted" id="spFiles">Dosya seçilmedi</span></div>
    <p style="margin-top:14px"><small>Spotify Premium ve geliştirici uygulaman varsa <span class="link" data-x="login">hesabınla giriş yapıp</span> doğrudan da aktarabilirsin.</small></p>
    <div class="row-btns"><button class="textbtn" data-x="cancel">Vazgeç</button><button class="pill fill" data-x="go">Aktar</button></div>`,
    (box, done) => {
      $("#spLinks", box).focus();
      $('[data-x="privacy"]', box).onclick = () => api.open_url("https://www.spotify.com/account/privacy/");
      $('[data-x="login"]', box).onclick = () => { done(null); loginImport("spotify"); };
      $('[data-x="files"]', box).onclick = async () => {
        files = await api.pick_import_files();
        $("#spFiles", box).textContent = files.length ? files.map(f => f.split(/[\\/]/).pop()).join(", ") : "Dosya seçilmedi";
      };
      $('[data-x="cancel"]', box).onclick = () => done(null);
      $('[data-x="go"]', box).onclick = async () => { if (await startImport("spotify", $("#spLinks", box).value, files)) done(true); };
    });
}
function importProgress(d) {
  let el = $("#importBox");
  if (!el) {
    el = document.createElement("div");
    el.id = "importBox";
    el.innerHTML = `<div class="ib-t"></div><div class="ib-bar"><i></i></div>`;
    document.body.appendChild(el);
  }
  if (d.finished) {
    el.remove();
    if (d.error && d.auth) openAccount(d.message, () => startImport("ytmusic"));
    else modal(`<h3>${d.error ? "Aktarılamadı" : "Aktarma tamamlandı"}</h3><p>${esc(d.message)}</p>
      ${d.error ? "" : `<small>Beğenmediysen üstteki ↶ düğmesiyle (Ctrl+Z) aktarmayı tamamen geri alabilirsin.</small>`}
      <div class="row-btns"><button class="pill fill" data-x="ok">Tamam</button></div>`, (box, done) => { $('[data-x="ok"]', box).onclick = () => done(null); });
    return;
  }
  $(".ib-t", el).textContent = d.text || "";
  const bar = $(".ib-bar i", el);
  bar.style.width = d.total ? `${Math.round(d.done / d.total * 100)}%` : "";
  el.classList.toggle("indet", !d.total);
}

/* ---------- uygulama güncellemesi: GitHub'dan yeni sürüm indirildi ---------- */
function showAppUpdate(d) {
  $("#updateBox")?.remove();
  const el = document.createElement("div");
  el.id = "updateBox";
  el.innerHTML = `<b>SOUND güncellendi</b>
    <p>${d.count > 1 ? d.count + " yenilik" : "Yeni sürüm"} indirildi. Yeniden başlatınca etkin olur.</p>
    ${d.notes?.length ? `<ul>${d.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
    ${d.packages === false ? `<p class="warn">Yeni paketler kurulamadı; internet bağlantısını kontrol et.</p>` : ""}
    <div class="row-btns"><button class="textbtn" data-x="later">Sonra</button><button class="pill accent" data-x="restart">Yeniden başlat</button></div>`;
  document.body.appendChild(el);
  $('[data-x="later"]', el).onclick = () => el.remove();
  $('[data-x="restart"]', el).onclick = () => { el.querySelector(".row-btns").innerHTML = "Yeniden başlatılıyor…"; api.restart_app(); };
}

/* ---------- renk ---------- */
const colorCache = {};
function coverColor(url) {
  if (colorCache[url]) return Promise.resolve(colorCache[url]);
  return new Promise(resolve => {
    const img = new Image();
    img.onload = () => {
      try {
        const c = document.createElement("canvas"); c.width = c.height = 10;
        const g = c.getContext("2d"); g.drawImage(img, 0, 0, 10, 10);
        const p = g.getImageData(0, 0, 10, 10).data;
        let r = 0, gg = 0, b = 0;
        for (let k = 0; k < p.length; k += 4) { r += p[k]; gg += p[k + 1]; b += p[k + 2]; }
        const n = p.length / 4;
        let [R, G, B] = [r / n, gg / n, b / n];
        const max = Math.max(R, G, B, 1), f = Math.min(1, 150 / max);  // çok parlak olmasın
        const color = `rgb(${R * f | 0},${G * f | 0},${B * f | 0})`;
        resolve(colorCache[url] = color);
      } catch { resolve(null); }
    };
    img.onerror = () => resolve(null);
    img.src = url;
  });
}
let glowFor = null;
function setGlow(color) {
  $("#glow").style.background = color ? `linear-gradient(180deg, ${color} 0%, color-mix(in srgb, ${color} 40%, var(--bg)) 45%, var(--bg) 100%)` : "transparent";
}
async function glowFrom(url, fallback) {
  glowFor = url;
  setGlow(fallback);
  const c = url && await coverColor(url);
  if (c && glowFor === url) setGlow(c);
}

/* ---------- liste öğeleri ---------- */
function registerList(key, tracks, ctx) { S.lists[key] = { tracks, ctx }; return key; }
function itemTrack(el) {
  const holder = el.closest("[data-list]");
  if (!holder) return null;
  const list = S.lists[holder.dataset.list];
  return list && list.tracks[+holder.dataset.i];
}

function rowHTML(key, i, t, right = null) {
  const inAlbum = S.lists[key]?.ctx?.kind === "album";
  return `<div class="row${inAlbum ? " has-rm" : ""}" data-list="${key}" data-i="${i}" data-tid="${esc(t.id)}">
    <div class="num"><span class="n">${i + 1}</span><span class="eq"><i></i><i></i><i></i></span><button class="rp" data-act="play">${I.play}</button></div>
    <img class="th" data-act="play" loading="lazy" src="${thumb(t)}">
    <div class="tt"><div class="t">${esc(t.title)}</div><div class="a">${esc(t.artist)}</div></div>
    <button class="rb heart" data-act="fav"></button><button class="rb dl" data-act="dl"></button>
    <div class="dur">${right != null ? esc(right) : t.duration ? clock(t.duration) : "–"}</div>
    ${inAlbum ? `<button class="rb rm" data-act="unalbum" title="Albümden çıkar">${I.minus}</button>` : ""}<button class="rb more" data-act="menu" title="Diğer">${I.more}</button></div>`;
}
function cardHTML(key, i, t) {
  return `<div class="card" data-list="${key}" data-i="${i}" data-tid="${esc(t.id)}" data-act="play">
    <div class="cover"><img loading="lazy" src="${thumb(t)}"></div><div class="ct">${esc(t.title)}</div>
    <div class="cfoot"><span>${esc(t.artist)}</span><div class="acts"><button class="cdl" data-act="dl"></button><button class="cfav heart" data-act="fav"></button><button class="pbtn" data-act="play">${I.play}</button></div></div></div>`;
}
function albumCardHTML(pl) {
  const k = "pl" + Object.keys(S.plShown).length;
  S.plShown[k] = pl;
  return `<div class="card" data-pl="${k}" data-act="plopen">
    <div class="cover"><img loading="lazy" src="${thumb(pl)}"></div><div class="ct">${esc(pl.title)}</div>
    <div class="cfoot"><span>${esc(pl.label || "Albüm")} · ${esc(pl.year || pl.artist)}</span><div class="acts"><button class="cdl" data-act="pldl"></button><button class="pbtn" data-act="plplay">${I.play}</button></div></div></div>`;
}
function artistCardHTML(a) {
  return `<div class="card circle" data-act="artist" data-aid="${esc(a.id || "")}" data-artist="${esc(a.name)}">
    <div class="cover">${a.thumbnail ? `<img loading="lazy" src="${esc(a.thumbnail)}">` : tile(a.id || a.name, 160, I.user, null, 80)}</div><div class="ct">${esc(a.name)}</div>
    <div class="cfoot"><span>${a.subscribers ? `${esc(a.subscribers)} abone` : "Sanatçı"}</span></div></div>`;
}
function skeletonCards(n = 8) {
  return `<div class="cards">${Array.from({ length: n }, () => '<div class="card skeleton"><div class="cover"></div><div class="ct"></div><div class="cfoot"><span></span></div></div>').join("")}</div>`;
}
function section(title, sub, body, link) {
  return `<div class="sec"><div><h2>${esc(title)}</h2>${sub ? `<p>${esc(sub)}</p>` : ""}</div>${link || ""}</div>${body}`;
}

function dlIcon(id, kind = "audio") {
  const key = dlKey(id, kind);
  if (kind === "audio" ? L.dl(id) : L.video(id)) return ["done", I.downloaded];
  if (busy(key)) {
    const p = S.dl.progress[key];
    return ["busy", p == null ? '<span class="ring wait"></span>' : `<span class="ring" style="--p:${(p * 100).toFixed(0)}"></span>`];
  }
  return ["none", I.download];
}
function setDlButton(btn, id, kind) {
  const [state, html] = dlIcon(id, kind);
  const key = dlKey(id, kind);
  if (state === "busy" && btn.dataset.state === "busy" && S.dl.progress[key] != null) {
    const ring = $(".ring", btn);
    if (ring && !ring.classList.contains("wait")) { ring.style.setProperty("--p", (S.dl.progress[key] * 100).toFixed(0)); return; }
  }
  if (btn.dataset.state !== state || state === "busy") { btn.innerHTML = html; btn.dataset.state = state; }
  btn.className = btn.className.replace(/\b(none|busy|done)\b/g, "").trim() + " " + state;
  btn.title = state === "done" ? "İndirildi" : state === "busy" ? "İndiriliyor — iptal için tıkla" : "İndir";
}

/* çalan şarkı, favori ve indirme durumlarını sayfayı yeniden çizmeden güncelle */
function refreshItems(root = document) {
  const cur = P.current && P.current.id, playing = P.isPlaying();
  for (const el of root.querySelectorAll("[data-tid]")) {
    const id = el.dataset.tid, isCur = id === cur;
    el.classList.toggle("current", isCur);
    el.classList.toggle("now", isCur && el.classList.contains("card"));
    el.classList.toggle("playing", isCur && playing);
    const heart = $(".heart", el);
    if (heart) {
      const on = L.fav(id);
      if (heart.dataset.on !== String(on)) { heart.dataset.on = on; heart.innerHTML = on ? I.heart : I.heartO; heart.classList.toggle("on", on); heart.title = on ? "Favorilerden çıkar" : "Favorilere ekle"; }
    }
    const dl = $(".dl, .cdl", el);
    if (dl) setDlButton(dl, id, "audio");
    const pb = $(".rp, .pbtn", el), want = isCur && playing ? "pause" : "play";
    if (pb && pb.dataset.icon !== want) { pb.dataset.icon = want; pb.innerHTML = I[want]; }
  }
  for (const el of root.querySelectorAll("[data-pl]")) {
    const pl = S.plShown[el.dataset.pl];
    if (!pl) continue;
    const src = `playlist:${pl.id}`, playing = P.source === src && P.isPlaying();
    const pb = $(".pbtn", el), want = playing ? "pause" : "play";
    if (pb && pb.dataset.icon !== want) { pb.dataset.icon = want; pb.innerHTML = I[want]; }
    const btn = $(".cdl", el), saved = L.albumBySource(pl.id);
    let state = "none", html = I.download;
    if (saved) {
      const tracks = L.albumTracks(saved), done = tracks.filter(t => L.dl(t.id)).length;
      if (tracks.length && done === tracks.length) { state = "done"; html = I.downloaded; }
      else if (tracks.some(t => busy(t.id))) { state = "busy"; html = `<span class="ring" style="--p:${(done / tracks.length * 100) | 0}"></span>`; }
    }
    if (btn && btn.dataset.html !== html) { btn.dataset.html = html; btn.innerHTML = html; btn.classList.toggle("done", state === "done"); btn.title = state === "done" ? "Tümü indirildi" : "Kaydet ve tümünü indir"; }
    el.classList.toggle("busy", state === "busy");
  }
  for (const el of root.querySelectorAll("[data-src]")) {
    const btn = $(".pbtn", el), want = P.source === el.dataset.src && P.isPlaying() ? "pause" : "play";
    if (btn && btn.dataset.icon !== want) { btn.dataset.icon = want; btn.innerHTML = I[want]; }
    el.classList.toggle("now", P.source === el.dataset.src && !!P.current);
  }
  const header = $("#heroPlay");
  if (header) {
    const active = P.source === header.dataset.source && P.current;
    const want = active && P.loading ? "spinner" : active && P.isPlaying() ? "pause" : "play";
    if (header.dataset.icon !== want) { header.dataset.icon = want; header.innerHTML = I[want]; }
  }
  const slot = $("#dlSlot");
  if (slot) { const html = downloadSlot(S.lists[slot.dataset.list]?.tracks || []); if (slot.dataset.html !== html) { slot.dataset.html = html; slot.innerHTML = html; } }
}

/* ---------- sayfalar ---------- */
function openPage(kind, ref = null, { push = true, keep = false } = {}) {
  const same = S.page.kind === kind && JSON.stringify(S.page.ref) === JSON.stringify(ref);
  if (push && !same) { S.back.push(S.page); S.fwd = []; }
  S.page = { kind, ref };
  renderSide();
  renderPage(keep || same);
}
function goBack() { if (!S.back.length) return; S.fwd.push(S.page); const p = S.back.pop(); openPage(p.kind, p.ref, { push: false }); }
function goForward() { if (!S.fwd.length) return; S.back.push(S.page); const p = S.fwd.pop(); openPage(p.kind, p.ref, { push: false }); }

function renderPage(keep = false) {
  const scroll = $("#scroll"), top = scroll.scrollTop;
  let { kind, ref } = S.page;
  if (kind === "album" && !L.album(ref)) { kind = "favorites"; ref = null; S.page = { kind, ref }; }
  S.lists = {};
  S.plShown = {};
  const page = $("#page");
  page.innerHTML = { home: pageHome, search: pageSearch, favorites: pageFavorites, downloads: pageDownloads, album: pageAlbum, playlist: pagePlaylist, artist: pageArtist, stats: pageStats }[kind](ref);
  S.signature = pageSignature();
  $$("#nav a").forEach(a => a.classList.toggle("on", a.dataset.page === kind));
  $("#backBtn").disabled = !S.back.length;
  $("#fwdBtn").disabled = !S.fwd.length;
  if (keep) scroll.scrollTop = top;
  else { scroll.scrollTop = 0; page.classList.remove("enter"); void page.offsetWidth; page.classList.add("enter"); }
  afterRender();
  refreshItems(page);
  onScroll();
}

function pageSignature() {
  const { kind, ref } = S.page, lib = S.lib;
  if (kind === "favorites") return lib.favorites.join();
  if (kind === "downloads") return [L.dlTracks().map(t => t.id).join(), S.dl.active.map(a => a.key).join(), S.dl.failed.map(f => f.key).join(),
    Object.values(lib.tracks).filter(t => t.video_file).map(t => t.id).join()].join("|");
  if (kind === "album") { const a = L.album(ref); return a && [a.name, a.folder, a.tracks.join()].join("|"); }
  if (kind === "playlist") return L.albumBySource(ref.id) || "";
  if (kind === "home") return [L.allAlbums().map(([id, a]) => id + a.name + (a.tracks[0] || "")).join(), lib.favorites.slice(0, 10).join(),
    L.dlTracks().slice(0, 10).map(t => t.id).join(), lib.recent.slice(0, 10).join()].join("|");
  return null;
}

let afterRender = () => {};
function greeting() { const h = new Date().getHours(); return h < 5 ? "İyi geceler" : h < 12 ? "Günaydın" : h < 18 ? "İyi günler" : "İyi akşamlar"; }

function pageHome() {
  afterRender = () => {
    const cur = P.current;
    glowFrom(cur ? thumb(cur) : null, "#3b2470");
    api.home().then(h => { S.home = h; });
  };
  const quick = [
    { title: "Favoriler", art: tile("fav", 64, I.heart, "#6d4ae0", 0), page: "favorites", tracks: L.favTracks(), src: "favorites", drop: "favorites" },
    { title: "İndirilenler", art: tile("dl", 64, stroke('<path d="M12 4v11m-5-5 5 5 5-5M5 20h14"/>', 2.4), "#0f766e", 0), page: "downloads", tracks: L.dlTracks(), src: "downloads" },
    ...Object.entries(S.lib.albums).sort((a, b) => b[1].created - a[1].created).slice(0, 4).map(([id, a]) => {
      const tracks = L.albumTracks(id);
      return { title: a.name, art: tracks[0] ? `<img src="${thumb(tracks[0])}">` : tile(id, 64, I.note, null, 0), page: "album", ref: id, tracks, src: `album:${id}`, drop: `album:${id}` };
    }),
  ];
  let html = `<div class="pad home-page"><div class="home-head"><h1 class="big">${greeting()}</h1>
    <button class="round-btn" data-act="homeRefresh" title="Önerileri yenile">${I.refresh}</button></div>
    <div class="quick">${quick.map((q, i) => {
      registerList(`quick${i}`, q.tracks, { kind: "collection", key: q.src });
      return `<div class="q" data-act="open" data-page="${q.page}" data-ref="${esc(q.ref || "")}" data-src="${esc(q.src)}" data-list="quick${i}" ${q.drop ? `data-drop="${q.drop}"` : ""}>
        ${q.art}<b>${esc(q.title)}</b>${q.tracks.length ? `<button class="pbtn" data-act="playAll">${I.play}</button>` : ""}</div>`;
    }).join("")}</div>`;

  const recent = L.recent().slice(0, 10);
  if (recent.length) html += section("Son dinlediklerin", null, cards("home:recent", recent));
  const sections = S.home.sections || [];
  if (sections.length) {
    for (const s of sections) {
      html += s.type === "albums" ? section(s.title, s.subtitle, `<div class="cards">${s.albums.slice(0, 10).map(albumCardHTML).join("")}</div>`)
        : section(s.title, s.subtitle, cards(`home:${s.key}`, s.tracks));
    }
  } else if (S.home.loading) html += section("Senin için hazırlanıyor…", null, skeletonCards());
  else if (S.home.error) html += `<div class="sec"><div><h2>Öneriler yüklenemedi</h2><p>${esc(S.home.error)} İndirdiğin şarkılar çevrimdışı da çalışır.</p></div></div>`;

  const artists = (S.lib.top_artists || []).slice(0, 10).filter(([, id]) => L.t(id));
  if (artists.length) html += section("En çok dinlediğin sanatçılar", null, `<div class="cards">${artists.map(([name, id]) =>
    `<div class="card circle" data-act="artist" data-artist="${esc(name)}"><div class="cover"><img loading="lazy" src="${thumb(L.t(id))}"></div><div class="ct">${esc(name)}</div><div class="cfoot"><span>Sanatçı</span></div></div>`).join("")}</div>`);
  const favs = L.favTracks().slice(0, 10);
  if (favs.length) html += section("Favorilerinden", null, cards("favorites", favs), `<span class="link" data-act="open" data-page="favorites">Tümünü göster</span>`);
  const dls = L.dlTracks().slice(0, 10);
  if (dls.length) html += section("Çevrimdışı hazır", "İnternetsiz dinleyebilirsin", cards("downloads", dls), `<span class="link" data-act="open" data-page="downloads">Tümünü göster</span>`);
  return html + "</div>";
}
function cards(key, tracks) {
  registerList(key + ":c", tracks, { kind: "home", key });
  return `<div class="cards">${tracks.slice(0, 10).map((t, i) => cardHTML(key + ":c", i, t)).join("")}</div>`;
}

function pageSearch() {
  const s = S.search;
  afterRender = () => setGlow(null);
  if (s.loading) return `<div class="pad">${section(`“${short(s.query, 40)}” aranıyor…`, null, skeletonCards())}</div>`;
  if (s.error) return `<div class="empty"><b>Arama yapılamadı</b><p>${esc(s.error)} İndirdiğin şarkıları internetsiz dinleyebilirsin.</p>
    <button class="pill" data-act="open" data-page="downloads">İndirilenlere git</button></div>`;
  if (s.tracks.length) {
    const key = registerList("search", s.tracks, { kind: "search", key: `search:${s.query}` });
    let html = "";
    if (s.artists.length) html += `<div class="pad">${section("Sanatçılar", null, `<div class="cards">${s.artists.map(artistCardHTML).join("")}</div>`)}</div>`;
    if (s.albums.length) html += `<div class="pad">${section("Albümler ve listeler", "Kapağa tıkla ya da sürükleyip kitaplığına bırak",
      `<div class="cards">${s.albums.slice(0, 10).map(albumCardHTML).join("")}</div>`)}</div>`;
    html += `<div class="actions" style="padding-top:26px"><button class="pbtn lg" id="heroPlay" data-act="playAll" data-list="${key}" data-source="search:${esc(s.query)}">${I.play}</button>
      <div><h2 style="font-size:23px;font-weight:800">Şarkılar</h2><div class="muted">“${esc(short(s.query, 40))}” için ${s.tracks.length} sonuç</div></div></div>`;
    html += thead() + `<div class="list">${s.tracks.map((t, i) => rowHTML(key, i, t)).join("")}</div>`;
    if (s.videos && s.videos.length) {
      const vkey = registerList("searchv", s.videos, { kind: "search", key: `videos:${s.query}` });
      html += `<div class="pad">${section("Videolar", "YouTube'dan: klipler, dizi sahneleri, canlı kayıtlar, cover'lar", "")}</div>`;
      html += thead() + `<div class="list">${s.videos.map((t, i) => rowHTML(vkey, i, t)).join("")}</div>`;
    }
    return html;
  }
  return `<div class="pad"><h1 class="big" style="margin-top:12px">Ne dinlemek istiyorsun?</h1>
    <p class="muted" style="margin-top:4px">Şarkı ya da sanatçı adını yukarıya yaz, Enter'a bas.</p>
    ${S.lib.recent_searches.length ? section("Son aramalar", null, `<div class="chips">${S.lib.recent_searches.map(q => `<span class="chip with-x" data-act="searchFor" data-q="${esc(q)}">${esc(q)}<span class="x" data-act="forget" data-q="${esc(q)}" title="Geçmişten sil">✕</span></span>`).join("")}</div>`,
      `<span class="link" data-act="forgetAll">Geçmişi temizle</span>`) : ""}</div>`;
}
const thead = (right = "Süre") => `<div class="thead"><div style="text-align:center">#</div><div class="c2">Başlık</div><div class="c6">${right}</div></div>`;

function pageFavorites() {
  return collection({
    label: "Çalma listesi", title: "Favoriler", tracks: L.favTracks(), ctx: { kind: "favorites", key: "favorites" },
    art: tile("fav", 210, I.heart, "#6d4ae0", 8), color: "#3b2a78",
    empty: ["Henüz favorin yok", "Beğendiğin şarkılardaki ♡ simgesine tıkla, burada toplansın."],
  });
}
function pageDownloads() {
  const tracks = L.dlTracks();
  return collection({
    label: "Çevrimdışı", title: "İndirilenler", tracks, ctx: { kind: "downloads", key: "downloads" },
    art: tile("dl", 210, stroke('<path d="M12 4v11m-5-5 5 5 5-5M5 20h14"/>', 2.4), "#0f766e", 8), color: "#134e48",
    empty: ["İndirilen şarkı yok", "Bir şarkının yanındaki indirme simgesine tıkla; internetsiz de dinleyebilirsin."],
    extraMeta: "", section: downloadsSection(),
    extraActions: `<button class="textbtn" data-act="openFolder">Klasörü aç</button>`,
  });
}
function pageAlbum(id) {
  const album = L.album(id), tracks = L.albumTracks(id), folder = album.folder && S.lib.folders[album.folder];
  return collection({
    label: "Albüm", title: album.name, tracks, ctx: { kind: "album", key: `album:${id}`, album: id },
    art: tracks[0] ? `<img class="art" src="${thumb(tracks[0])}">` : tile(id, 210, I.note, null, 8),
    glowUrl: tracks[0] && thumb(tracks[0]), color: tileColor(id), prefix: folder ? `${folder.name} · ` : "",
    menu: true, menuAct: "albumMenu", menuRef: id,
    empty: ["Bu albüm boş", "Arama sonuçlarından bir şarkıyı sürükleyip soldaki albüme bırak ya da ⋯ › Albüme ekle'yi kullan."],
  });
}
function pagePlaylist(pl) {
  const tracks = S.playlists[pl.id], error = S.playlistErrors[pl.id], saved = L.albumBySource(pl.id);
  if (!tracks && !error) loadPlaylist(pl).then(() => { if (S.page.kind === "playlist" && S.page.ref.id === pl.id) renderPage(true); });
  const key = `k${Object.keys(S.plShown).length}`;
  S.plShown[key] = pl;
  let extra = "";
  if (saved) extra = `<button class="pill ghost-accent" data-act="open" data-page="album" data-ref="${saved}">${I.check} Kitaplığında</button>`;
  else if (tracks) extra = `<button class="pill accent" data-act="plsave" data-pl="${key}">${I.plus} Kitaplığa kaydet</button>`;
  else if (error) extra = `<button class="pill" data-act="plretry" data-pl="${key}">Tekrar dene</button>`;
  return collection({
    label: "Albüm", title: pl.title, tracks: tracks || [], ctx: { kind: "playlist", key: `playlist:${pl.id}` },
    art: `<img class="art" src="${thumb(pl)}">`, glowUrl: thumb(pl), color: tileColor(pl.id), prefix: `${pl.artist} · `,
    extraActions: extra,
    empty: error ? ["Albüm yüklenemedi", error] : tracks ? ["Bu listede şarkı yok", ""] : ["Yükleniyor…", "Albümün şarkıları getiriliyor."],
  });
}

const artistKey = ref => ref.id || "n:" + (ref.name || "").toLocaleLowerCase("tr");
function pageArtist(ref) {
  const k = artistKey(ref), a = S.artists[k], error = S.artistErrors[k];
  if (!a && !error) {
    api.artist(ref).then(res => {
      if (res.error) S.artistErrors[k] = res.error;
      else { S.artists[k] = res; S.artists[res.id] = res; }
      if (S.page.kind === "artist" && artistKey(S.page.ref) === k) renderPage(true);
    });
    afterRender = () => setGlow(null);
    return `<div class="artist-hero"><div class="ah-in"><div class="label">Sanatçı</div><h1>${esc(ref.name || "")}</h1><div class="meta">Yükleniyor…</div></div></div>
      <div class="pad">${skeletonCards(6)}</div>`;
  }
  if (error) {
    afterRender = () => setGlow(null);
    return `<div class="empty"><b>Sanatçı sayfası açılamadı</b><p>${esc(error)}</p>
      <div style="display:flex;gap:10px">${ref.name ? `<button class="pill" data-act="searchFor" data-q="${esc(ref.name)}">${I.search} Şarkılarını ara</button>` : ""}
      <button class="pill" data-act="artistRetry" data-k="${esc(k)}">Tekrar dene</button></div></div>`;
  }
  afterRender = () => glowFrom(a.thumbnail, tileColor(a.id));
  const key = registerList("artist", a.songs, { kind: "artist", key: `artist:${a.id}` });
  const stats = [a.listeners && `${esc(a.listeners)} aylık dinleyici`, a.subscribers && `${esc(a.subscribers)} abone`].filter(Boolean).join(" · ");
  let html = `<div class="artist-hero${a.banner ? " has-banner" : ""}" ${a.banner ? `style="background-image:url(&quot;${esc(a.banner)}&quot;)"` : ""}>
    <div class="ah-in"><div class="label">Sanatçı</div><h1 style="font-size:${a.name.length < 16 ? 76 : a.name.length < 30 ? 52 : 36}px">${esc(a.name)}</h1>
    <div class="meta">${stats}</div></div></div>`;
  html += `<div class="actions" style="padding-top:22px">`;
  if (a.songs.length) html += `<button class="pbtn lg" id="heroPlay" data-act="playAll" data-list="${key}" data-source="artist:${esc(a.id)}">${I.play}</button>
    <button class="icon-btn" data-act="shuffleAll" data-list="${key}" title="Karışık çal">${I.shuffle}</button>`;
  if (a.radio) html += `<button class="pill" data-act="artistRadio" data-radio="${esc(a.radio)}" data-name="${esc(a.name)}">${I.radio} Sanatçı radyosu</button>`;
  html += `</div>`;
  if (a.songs.length) {
    const all = S.artistMore === a.id, shown = all ? a.songs : a.songs.slice(0, 10);
    html += `<div class="pad">${section("Popüler", null, "")}</div>` + thead() + `<div class="list">${shown.map((t, i) => rowHTML(key, i, t)).join("")}</div>`;
    if (a.songs.length > 10) html += `<div class="pad" style="padding-top:6px"><span class="link" data-act="artistMore" data-id="${esc(a.id)}">${all ? "Daha az göster" : "Daha fazla göster"}</span></div>`;
  }
  html += `<div class="pad">`;
  if (a.albums.length) html += section("Albümler", "Kapağa tıkla ya da sürükleyip kitaplığına bırak", `<div class="cards">${a.albums.map(albumCardHTML).join("")}</div>`);
  if (a.singles.length) html += section("Single'lar ve EP'ler", null, `<div class="cards">${a.singles.map(albumCardHTML).join("")}</div>`);
  if (a.related.length) html += section("Hayranları bunları da dinliyor", null, `<div class="cards">${a.related.map(artistCardHTML).join("")}</div>`);
  if (a.description) html += section("Hakkında", null, `<div class="about">${esc(a.description)}</div>`);
  return html + `</div>`;
}

/* ---------- dinleme istatistikleri ---------- */
const STAT_PERIODS = [["7", "Son 7 gün"], ["30", "Son 30 gün"], ["year", "Bu yıl"], ["all", "Tüm zamanlar"]];
const MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
const statNum = n => Math.round(n).toLocaleString("tr-TR");
function listenTime(seconds) {
  const m = Math.round(seconds / 60);
  if (m < 1) return seconds > 0 ? "1 dk'dan az" : "0 dk";
  const h = Math.floor(m / 60);
  return h ? `${statNum(h)} sa${m % 60 ? ` ${m % 60} dk` : ""}` : `${m} dk`;
}
function statBars(items, labelEvery) {
  /* tek seri, tek eksen: yükseklik dakika. Y ölçeği yuvarlak bir tepe değere oturur */
  const peakMin = Math.max(...items.map(x => x.seconds)) / 60;
  const step = [1, 2, 5, 10, 15, 30, 60, 120, 180, 300, 600, 1200, 3000, 6000].find(s => s * 3 >= peakMin) || Math.ceil(peakMin / 3);
  const top = Math.max(step, Math.ceil(peakMin / step) * step);
  let ticks = "";
  for (let v = step; v <= top; v += step) ticks += `<i style="bottom:${v / top * 100}%"><span>${listenTime(v * 60)}</span></i>`;
  return `<div class="st-chart"><div class="st-grid">${ticks}</div><div class="st-bars">${items.map((x, i) => {
    const pct = x.seconds / 60 / top * 100;
    return `<div class="st-col" data-tip="${esc(x.tip)}: ${esc(listenTime(x.seconds))}" aria-label="${esc(x.tip)}: ${esc(listenTime(x.seconds))}">
      <b ${x.seconds ? `style="height:max(3px,${pct}%)"` : ""}></b><span>${i % labelEvery === 0 ? esc(x.label) : ""}</span></div>`;
  }).join("")}</div></div>`;
}
function pageStats() {
  S.statsData = S.statsData || {};
  const period = S.statsPeriod || "30", d = S.statsData[period];
  afterRender = () => {
    setGlow(null);
    if (S.statsFresh === period) { S.statsFresh = null; return; }  // veri geldiği için yeniden çizildi
    api.stats(period).then(res => {
      S.statsData[period] = res;
      if (S.page.kind === "stats" && (S.statsPeriod || "30") === period) { S.statsFresh = period; renderPage(true); }
    });
  };
  const head = `<div class="pad st-head"><h1>İstatistikler</h1><div class="seg">${STAT_PERIODS.map(([k, n]) =>
    `<button data-act="statsPeriod" data-k="${k}" class="${k === period ? "on" : ""}">${n}</button>`).join("")}</div></div>`;
  if (!d) return head + `<div class="pad">${skeletonCards(6)}</div>`;
  if (!d.seconds) return head + `<div class="empty"><b>Bu dönemde dinleme yok</b><p>Şarkı dinledikçe süren, en sevdiğin şarkılar ve sanatçılar burada birikir.</p>
    ${period !== "all" ? `<button class="pill" data-act="statsPeriod" data-k="all">Tüm zamanlara bak</button>` : ""}</div>`;
  const stat = (value, label) => `<div class="st-tile"><b>${esc(String(value))}</b><span>${label}</span></div>`;
  let html = head + `<div class="pad"><div class="st-tiles">
    <div class="st-tile st-big"><b>${esc(listenTime(d.seconds))}</b><span>toplam dinleme</span></div>
    ${stat(statNum(d.plays), "dinleme")}${stat(statNum(d.tracks), "farklı şarkı")}${stat(statNum(d.artists), "farklı sanatçı")}${stat(statNum(d.streak) + " gün", "üst üste dinleme")}</div>`;
  const items = d.buckets.map(b => {
    if (d.monthly) { const [y, m] = b.key.split("-"); return { seconds: b.seconds, label: MONTHS[+m - 1].slice(0, 3), tip: `${MONTHS[+m - 1]} ${y}` }; }
    const [y, m, day] = b.key.split("-");
    return { seconds: b.seconds, label: `${+day} ${MONTHS[+m - 1].slice(0, 3)}`, tip: `${+day} ${MONTHS[+m - 1]}` };
  });
  const hasDated = items.some(x => x.seconds);
  if (hasDated) {
    html += section(d.monthly ? "Aylara göre dinleme" : "Günlere göre dinleme", null, statBars(items, items.length > 12 ? 5 : 1));
    const hours = d.hours.map((s, h) => ({ seconds: s, label: String(h).padStart(2, "0"), tip: `${String(h).padStart(2, "0")}:00–${String((h + 1) % 24).padStart(2, "0")}:00` }));
    html += section("Günün saatlerine göre", null, statBars(hours, 3));
  }
  if (d.seeded) html += `<p class="st-note">Toplamlara eski dinleme geçmişin de dahil. Tarihi bilinmediği için grafiklerde yer almıyor.</p>`;
  html += `</div>`;
  if (d.top_tracks.length) {
    const key = registerList("stats", d.top_tracks, { kind: "stats", key: `stats:${period}` });
    html += `<div class="pad">${section("En çok dinlediğin şarkılar", null, "")}</div>` + thead("Dinleme") +
      `<div class="list">${d.top_tracks.map((t, i) => rowHTML(key, i, t, statNum(t.plays) + " kez")).join("")}</div>`;
  }
  if (d.top_artists.length) html += `<div class="pad">` + section("En çok dinlediğin sanatçılar", null, `<div class="cards">${d.top_artists.map(a =>
    `<div class="card circle" data-act="artist" data-artist="${esc(a.name)}"><div class="cover"><img loading="lazy" src="${thumb(a)}"></div><div class="ct">${esc(a.name)}</div><div class="cfoot"><span>${esc(listenTime(a.seconds))}</span></div></div>`).join("")}</div>`) + `</div>`;
  return html;
}

function downloadSlot(tracks) {
  const missing = tracks.filter(t => !L.dl(t.id)), working = missing.filter(t => busy(t.id));
  if (working.length) return `<span class="state">${I.spinner} ${working.length < missing.length ? `İndiriliyor… (${tracks.length - missing.length}/${tracks.length} hazır)` : `${working.length} şarkı indiriliyor…`}</span>`;
  if (missing.length) return `<button class="pill" data-act="downloadAll">${stroke('<path d="M12 4v11m-5-5 5 5 5-5M5 20h14"/>', 2.4)} Tümünü indir (${missing.length})</button>`;
  return `<span class="state">${I.downloaded} Çevrimdışı dinlenebilir</span>`;
}

function collection(o) {
  const tracks = o.tracks, total = tracks.reduce((s, t) => s + (t.duration || 0), 0);
  const listKey = registerList("main", tracks, o.ctx);
  afterRender = () => {
    glowFrom(o.glowUrl, o.color);
    const input = $("#filterInput");
    if (input) {
      let timer = null;
      input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { view(o.ctx.key).query = input.value.trim(); fillList(); }, 150); });
      input.addEventListener("keydown", e => { if (e.key === "Escape") { input.value = ""; view(o.ctx.key).query = ""; fillList(); input.blur(); } });
    }
  };
  const meta = `${esc(o.prefix || "")}${tracks.length} şarkı${total ? " · " + longTime(total) : ""}`;
  let html = `<div class="hero">${o.art}<div style="min-width:0">
    <div class="label">${esc(o.label)}</div><h1 style="font-size:${o.title.length < 14 ? 72 : o.title.length < 28 ? 48 : 34}px">${esc(o.title)}</h1>
    <div class="meta">${meta}</div></div></div>`;
  html += `<div class="actions">`;
  if (tracks.length) {
    html += `<button class="pbtn lg" id="heroPlay" data-act="playAll" data-list="${listKey}" data-source="${esc(o.ctx.key)}">${I.play}</button>
      <button class="icon-btn" data-act="shuffleAll" data-list="${listKey}" title="Karışık çal">${I.shuffle}</button>
      <span id="dlSlot" data-list="${listKey}">${downloadSlot(tracks)}</span>`;
  }
  html += o.extraActions || "";
  if (o.menu) html += `<button class="icon-btn" data-act="${o.menuAct}" data-ref="${esc(o.menuRef)}" title="Diğer">${I.more}</button>`;
  html += `</div>${o.section || ""}`;
  if (tracks.length) {
    const v = view(o.ctx.key);
    html += `<div class="toolbar"><label class="filter">${I.search}<input id="filterInput" placeholder="Bu listede ara" value="${esc(v.query)}" spellcheck="false"></label>
      <button class="sort" data-act="sortMenu" data-key="${esc(o.ctx.key)}">${esc(Object.fromEntries(SORTS)[v.sort])} ${I.down}</button></div>`;
    html += thead() + `<div class="list" id="listBox">${listRows()}</div>`;
  } else {
    html += `<div class="empty"><b>${esc(o.empty[0])}</b><p>${esc(o.empty[1])}</p>${["search", "playlist"].includes(o.ctx.kind) ? "" : `<button class="pill" data-act="focusSearch">Şarkı ara</button>`}</div>`;
  }
  return html;
}
const view = key => S.views[key] || (S.views[key] = { query: "", sort: "custom" });
function shownTracks() {
  const list = S.lists.main, v = view(list.ctx.key);
  let shown = [...list.tracks];
  const q = v.query.toLocaleLowerCase("tr");
  if (q) shown = shown.filter(t => t.title.toLocaleLowerCase("tr").includes(q) || t.artist.toLocaleLowerCase("tr").includes(q));
  const by = { title: t => t.title.toLocaleLowerCase("tr"), artist: t => t.artist.toLocaleLowerCase("tr") + t.title.toLocaleLowerCase("tr") };
  if (by[v.sort]) shown.sort((a, b) => by[v.sort](a).localeCompare(by[v.sort](b), "tr"));
  else if (v.sort === "duration") shown.sort((a, b) => (a.duration || 0) - (b.duration || 0));
  else if (v.sort === "recent") shown.sort((a, b) => ((L.t(b.id) || {}).downloaded_at || 0) - ((L.t(a.id) || {}).downloaded_at || 0));
  return { shown, reorder: v.sort === "custom" && !q };
}
function listRows() {
  const { shown, reorder } = shownTracks(), main = S.lists.main;
  registerList("shown", shown, { ...main.ctx, reorder });
  if (!shown.length) return `<div class="empty"><p>“${esc(view(main.ctx.key).query)}” ile eşleşen şarkı yok</p></div>`;
  return shown.map((t, i) => rowHTML("shown", i, t)).join("");
}
function fillList() {
  const box = $("#listBox");
  if (!box) return;
  box.innerHTML = listRows();
  refreshItems(box);
}

function downloadsSection() {
  let html = "";
  const rows = [...S.dl.active.map(a => ({ ...a, failed: false })), ...S.dl.failed.filter(f => !S.dl.active.some(a => a.key === f.key)).map(f => ({ ...f, failed: true }))];
  if (rows.length) {
    const active = S.dl.active.length;
    html += `<div class="dlbox"><h3>${active ? `İndirmeler · ${active} sürüyor` : "İndirmeler"}${active > 1 ? `<button class="textbtn" data-act="cancelAll">Tümünü iptal et</button>` : ""}</h3>
      ${rows.map(r => `<div class="dlrow" data-key="${esc(r.key)}"><img src="${thumb(r.track)}"><div class="tt"><div class="t">${esc(r.track.title)} · ${r.kind === "video" ? "Video" : "Ses"}</div>
        <div class="a ${r.failed ? "err" : ""}" data-status>${r.failed ? "Hata: " + esc(r.error) : dlStatus(r.key)}</div></div>
        ${r.failed ? `<button class="pill" data-act="retry" data-key="${esc(r.key)}">Tekrar dene</button><button class="rb" data-act="dismiss" data-key="${esc(r.key)}">${I.close}</button>`
          : `<div class="bar-track"><i data-bar style="width:${(S.dl.progress[r.key] || 0) * 100}%"></i></div><button class="rb" data-act="cancel" data-key="${esc(r.key)}" title="İptal">${I.close}</button>`}</div>`).join("")}</div>`;
  }
  const videos = Object.values(S.lib.tracks).filter(t => t.video_file);
  if (videos.length) {
    html += `<div class="dlbox"><h3>Videolar · ${videos.length}</h3>${videos.map(t => `<div class="dlrow"><img src="${thumb(t)}"><div class="tt"><div class="t">${esc(t.title)}</div><div class="a">${esc(t.artist)}</div></div>
      <button class="pill" data-act="openVideo" data-id="${esc(t.id)}">${I.external} Aç</button><button class="textbtn" data-act="removeVideo" data-id="${esc(t.id)}">Sil</button></div>`).join("")}</div>`;
  }
  return html;
}
function dlStatus(key) {
  const p = S.dl.progress[key];
  return p == null ? "Sırada bekliyor" : p < 0.01 ? "YouTube'dan alınıyor…" : p >= 0.94 ? "Dönüştürülüyor…" : `%${(p * 100) | 0} indirildi`;
}

/* ---------- kenar çubuğu ---------- */
function renderSide() {
  const sig = JSON.stringify([S.lib.folders, Object.entries(S.lib.albums).map(([id, a]) => [id, a.name, a.folder, a.tracks.length, a.tracks[0]]),
    [...S.expanded], S.page.kind === "album" ? S.page.ref : null]);
  if (sig === S.sideSignature) return;
  S.sideSignature = sig;
  const folders = L.folders(), roots = L.albums(null), box = $("#libList");
  if (!folders.length && !roots.length) {
    box.innerHTML = `<div class="empty-lib"><b>İlk albümünü oluştur</b><p>Sevdiğin şarkıları albümlerde topla, albümleri klasörlerle düzenle.</p>
      <button class="pill fill" data-act="newAlbum">Albüm oluştur</button></div>`;
    return;
  }
  const albumItem = (id, a, sub) => {
    const tracks = L.albumTracks(id), on = S.page.kind === "album" && S.page.ref === id;
    return `<div class="li${sub ? " sub" : ""}${on ? " on" : ""}" data-act="open" data-page="album" data-ref="${id}" data-album="${id}" data-drop="album:${id}">
      ${tracks[0] ? `<img class="art" loading="lazy" src="${thumb(tracks[0])}">` : tile(id, 48, I.note)}
      <div class="li-text"><div class="li-t">${esc(a.name)}</div><div class="li-s">Albüm · ${a.tracks.length} şarkı</div></div></div>`;
  };
  let html = "";
  for (const [fid, f] of folders) {
    const albums = L.albums(fid), open = S.expanded.has(fid);
    html += `<div class="li${open ? " open" : ""}" data-act="folder" data-folder="${fid}">${tile(fid, 48, I.folder, "#3a3a3a")}
      <div class="li-text"><div class="li-t">${esc(f.name)}</div><div class="li-s">Klasör · ${albums.length} albüm</div></div>${I.chevron.replace("<svg", '<svg class="chev"')}</div>`;
    if (open) html += albums.length ? albums.map(([id, a]) => albumItem(id, a, true)).join("") : `<div class="folder-empty">Boş klasör</div>`;
  }
  html += roots.map(([id, a]) => albumItem(id, a, false)).join("");
  box.innerHTML = html;
}

/* ---------- çalar ---------- */
const AUDIO = [$("#audio"), document.createElement("audio")];
AUDIO[1].preload = "auto";
let A = AUDIO[0];  // şu an çalan; diğeri sıradaki şarkıyı önceden yükler (boşluksuz geçiş / crossfade)
const other = () => AUDIO[A === AUDIO[0] ? 1 : 0];
const onAudio = (name, fn) => AUDIO.forEach(el => el.addEventListener(name, e => { if (e.target === A) fn(e); }));
let masterVolume = 0.7;
const P = {
  queue: [], order: [], pos: -1, source: null, shuffle: false, repeat: "off", current: null,
  loading: false, token: 0, resumeAt: null, streams: {}, local: false, retried: false, countedPlay: null,

  isPlaying() { return this.loading || (!!A.src && !A.paused); },

  playList(tracks, index, source = null, shuffle = null) {
    if (!tracks.length) return;
    this.queue = tracks.map(plain);
    this.source = source;
    if (shuffle != null) this.shuffle = shuffle;
    this.buildOrder(index);
    this.playCurrent();
    queueChanged();
  },
  playCollection(tracks, source) {
    if (this.source === source && this.current) { this.toggle(); return; }
    this.playList(tracks, this.shuffle ? Math.floor(Math.random() * tracks.length) : 0, source);
  },
  buildOrder(start) {
    this.order = this.queue.map((_, i) => i);
    if (this.shuffle) {
      const rest = this.order.filter(i => i !== start);
      for (let i = rest.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [rest[i], rest[j]] = [rest[j], rest[i]]; }
      this.order = [start, ...rest];
      this.pos = 0;
    } else this.pos = start;
  },
  upcoming(limit = 40) {
    const out = [];
    for (let i = this.pos + 1; i < Math.min(this.order.length, this.pos + 1 + limit); i++) out.push([i, this.queue[this.order[i]]]);
    return out;
  },
  playNext(track) {
    if (!this.queue.length) return this.playList([track], 0);
    this.queue.push(plain(track));
    this.order.splice(this.pos + 1, 0, this.queue.length - 1);
    toast("Sıradaki şarkı olarak eklendi");
    queueChanged();
  },
  enqueue(track) {
    if (!this.queue.length) return this.playList([track], 0);
    this.queue.push(plain(track));
    this.order.push(this.queue.length - 1);
    toast("Kuyruğa eklendi");
    queueChanged();
  },
  jumpTo(index) { if (index >= 0 && index < this.order.length) { this.pos = index; this.playCurrent(); queueChanged(); } },
  removeAt(index) { if (index > this.pos && index < this.order.length) { this.order.splice(index, 1); queueChanged(); } },
  clearQueue() { this.order.splice(this.pos + 1); queueChanged(); },
  move(source, target, after) {
    if (source === target || !(source > this.pos && source < this.order.length)) return;
    const item = this.order.splice(source, 1)[0];
    if (target > source) target -= 1;
    this.order.splice(Math.max(target + (after ? 1 : 0), this.pos + 1), 0, item);
    queueChanged();
  },

  async playCurrent() {
    const track = this.queue[this.order[this.pos]];
    if (!track) return;
    const token = ++this.token;
    const sameTrack = this.current && this.current.id === track.id;
    this.current = track;
    this.retried = false;
    finishFade();
    const ready = this.prepared;
    if (ready && ready.id === track.id && ready.el.readyState >= 2 && !(this.resumeAt && this.resumeAt[0] === track.id)) {
      // sıradaki şarkı diğer oynatıcıda hazır: beklemeden geç (boşluksuz)
      const old = A;
      A = ready.el;
      this.prepared = null;
      this.local = ready.local;
      this.loading = false;
      loudnessFor(A, track.id);
      old.pause();
      A.volume = masterVolume;
      A.currentTime = 0;
      A.play().catch(() => {});
      unloadOther();
      playerChanged(!sameTrack);
      return;
    }
    this.prepared = null;
    unloadOther();
    A.pause();
    let start = 0;
    if (this.resumeAt && this.resumeAt[0] === track.id) start = this.resumeAt[1];
    this.resumeAt = null;
    const stored = L.t(track.id);
    if (stored && stored.file) {
      this.local = true;
      this.loading = false;
      this.load(`/music/${encodeURIComponent(stored.file)}`, start);
    } else {
      this.local = false;
      this.loading = true;
      playerChanged(!sameTrack);
      const res = await api.stream(track);
      if (token !== this.token) return;
      if (res.error) return this.failed(res, track);
      this.streams[track.id] = res;
      this.local = !!res.cached;
      if (res.alt) toast("Orijinal video engelli; aynı şarkının başka bir yüklemesi çalınıyor");
      this.load(res.audio, start);
      playerChanged();
      return;
    }
    playerChanged(!sameTrack);
  },
  load(src, start) {
    loudnessFor(A, this.current && this.current.id);
    A.volume = masterVolume;
    A.src = src;
    if (start > 1) {
      A.currentTime = start;  // meta veri gelmeden ayarlanırsa başlangıç konumu olur
      A.addEventListener("loadedmetadata", () => { if (A.currentTime < start - 1) A.currentTime = start; }, { once: true });
    }
    A.play().catch(() => {});
  },
  failed(res, track) {
    this.loading = false;
    if (res.age) {
      toast("Bu şarkı yaş doğrulaması istiyor", true);
      playerChanged();
      openAccount(`“${short(track.title, 50)}” için YouTube yaş doğrulaması istiyor.`, () => this.current && this.current.id === track.id && this.playCurrent());
      return;
    }
    if (res.unavailable && this.pos + 1 < this.order.length) {
      toast(`Atlandı: ${short(track.title, 40)} — ${res.error}`, true);
      this.next();
      return;
    }
    toast(`Şarkı yüklenemedi: ${res.error}`, true);
    playerChanged();
  },
  toggle() {
    if (this.loading) return;
    if (!this.current) return;
    finishFade();
    if (!A.src) { this.playCurrent(); return; }
    if (A.paused) {
      const s = this.streams[this.current.id];
      if (!this.local && s && s.expire && Date.now() / 1000 > s.expire - 60) {  // akış adresinin süresi dolmuş
        this.resumeAt = [this.current.id, A.currentTime];
        this.refreshStream();
        return;
      }
      A.play().catch(() => {});
    } else A.pause();
  },
  async refreshStream() {
    const track = this.current, token = ++this.token, at = this.resumeAt ? this.resumeAt[1] : A.currentTime;
    this.loading = true;
    playerChanged();
    const res = await api.stream(track, true);
    if (token !== this.token) return;
    if (res.error) return this.failed(res, track);
    this.streams[track.id] = res;
    this.resumeAt = null;
    this.load(res.audio, at);
  },
  next(auto = false) {
    if (!this.order.length) return;
    if (auto && this.repeat === "one") { A.currentTime = 0; A.play().catch(() => {}); return; }
    if (!auto) finishFade();
    if (this.pos + 1 < this.order.length) this.pos += 1;
    else if (this.repeat === "all") this.pos = 0;
    else { if (auto) { A.pause(); playerChanged(); } return; }
    this.playCurrent();
    queueChanged();
  },
  previous() {
    if (!this.order.length) return;
    if ((A.currentTime > 3 || this.pos === 0) && A.src) { A.currentTime = 0; return; }
    if (this.pos > 0) this.pos -= 1;
    this.playCurrent();
    queueChanged();
  },
  toggleShuffle() {
    this.shuffle = !this.shuffle;
    if (this.order.length) this.buildOrder(this.order[this.pos]);
    toast(this.shuffle ? "Karışık çalma açık" : "Karışık çalma kapalı");
    playerChanged();
    queueChanged();
  },
  cycleRepeat() {
    this.repeat = { off: "all", all: "one", one: "off" }[this.repeat];
    toast({ off: "Tekrar kapalı", all: "Liste tekrarlanacak", one: "Şarkı tekrarlanacak" }[this.repeat]);
    playerChanged();
  },
  nextTrack() {
    if (this.repeat === "one") return null;
    return this.pos + 1 < this.order.length ? this.queue[this.order[this.pos + 1]] : this.repeat === "all" && this.order.length ? this.queue[this.order[0]] : null;
  },
  /* şarkının sonuna yaklaşınca sıradakini diğer oynatıcıda yükle */
  async prepareNext() {
    const t = this.nextTrack();
    if (!t || (this.prepared && this.prepared.id === t.id) || this.preparing === t.id) return;
    this.preparing = t.id;
    const stored = L.t(t.id);
    let src, local = true;
    if (stored && stored.file) src = `/music/${encodeURIComponent(stored.file)}`;
    else {
      const res = await api.stream(plain(t));
      if (res.error) { this.preparing = null; return; }
      this.streams[t.id] = res;
      src = res.audio;
      local = !!res.cached;
    }
    this.preparing = null;
    if (this.nextTrack() !== t) return;
    const el = other();
    el.volume = 0;
    loudnessFor(el, t.id);
    el.src = src;
    el.load();
    this.prepared = { id: t.id, el, local };
  },
  prefetchNext() {
    const nextTrack = this.nextTrack();
    const wantVideo = !!nextTrack && S.panelOpen && S.panelMode === "video" && !L.video(nextTrack.id);
    if (nextTrack && (!L.dl(nextTrack.id) || wantVideo)) api.prefetch([nextTrack], wantVideo);
  },
  duration() { return (this.current && this.current.duration) || (isFinite(A.duration) ? A.duration : 0); },
  position() {
    if (!A.src && this.resumeAt && this.current && this.resumeAt[0] === this.current.id) return this.resumeAt[1];
    return this.loading ? 0 : A.currentTime || 0;
  },
};

onAudio("playing", () => {
  P.loading = false;
  if (P.current && P.countedPlay !== P.token) {
    P.countedPlay = P.token;
    api.played(P.current);
    loadLyrics(P.current);
    P.prefetchNext();
  }
  playerChanged();
  syncVideo();
});
onAudio("pause", () => { playerChanged(); syncVideo(); });
onAudio("seeked", syncVideo);
onAudio("ended", () => { listenEnd(); P.next(true); });
onAudio("waiting", () => { if (!A.paused) { $("#ppBtn").innerHTML = I.spinner; } });
onAudio("error", () => {
  if (!P.current || !A.getAttribute("src")) return;
  if (!P.local && !P.retried) {  // akış adresi geçersizleşmiş olabilir: yenisini al, kaldığı yerden devam
    P.retried = true;
    P.resumeAt = [P.current.id, A.currentTime];
    P.refreshStream();
    return;
  }
  P.loading = false;
  toast("Şarkı çalınamadı", true);
  playerChanged();
});

/* crossfade: şarkı bitmeden sıradaki yavaşça açılır, çalan yavaşça kısılır */
let fade = null;
function unloadOther() {
  const el = other();
  if (P.prepared && P.prepared.el === el) return;
  el.pause();
  if (el.getAttribute("src")) { el.removeAttribute("src"); el.load(); }
}
function finishFade() {
  if (!fade) return;
  const f = fade;
  fade = null;
  f.from.pause();
  f.from.removeAttribute("src");
  f.from.load();
  A.volume = masterVolume;
}
function startCrossfade(seconds) {
  const ready = P.prepared, nextIndex = P.pos + 1 < P.order.length ? P.pos + 1 : 0;
  P.prepared = null;
  const from = A;
  A = ready.el;
  P.pos = nextIndex;
  P.current = P.queue[P.order[P.pos]];
  P.token++;
  P.local = ready.local;
  P.retried = false;
  A.volume = 0;
  A.currentTime = 0;
  A.play().catch(() => {});
  fade = { from, start: performance.now(), ms: seconds * 1000 };
  playerChanged(true);
  queueChanged();
  // requestAnimationFrame değil zamanlayıcı: pencere simge durumundayken de geçiş tamamlansın
  const timer = setInterval(() => {
    if (!fade || fade.from !== from) { clearInterval(timer); return; }
    const p = Math.min(1, (performance.now() - fade.start) / fade.ms);
    from.volume = masterVolume * Math.cos(p * Math.PI / 2);  // eşit güçte geçiş
    A.volume = masterVolume * Math.sin(p * Math.PI / 2);
    if (p >= 1) { clearInterval(timer); finishFade(); }
  }, 40);
}
setInterval(() => {
  if (!P.current || !A.getAttribute("src") || A.paused || P.loading || fade) return;
  const st = S.settings, dur = isFinite(A.duration) ? A.duration : P.duration(), left = dur - A.currentTime;
  if (!dur || !(st.gapless || st.crossfade)) return;
  const cf = st.crossfade ? Math.max(1, +st.crossfade_seconds || 6) : 0;
  if (left < Math.max(cf + 10, 15)) P.prepareNext();
  if (cf && left <= cf && P.prepared && P.prepared.el.readyState >= 3 && P.nextTrack() && P.nextTrack().id === P.prepared.id) startCrossfade(Math.min(cf, left));
}, 250);

let lastPlayerState = "";
function playerChanged(trackChanged = false) {
  const t = P.current;
  const np = $("#np");
  if (t) {
    if (np.dataset.id !== t.id) {
      np.dataset.id = t.id;
      np.innerHTML = `<img src="${thumb(t)}" data-act="showPanel"><div class="tt"><div class="t" data-act="showPanel">${esc(t.title)}</div><div class="a"></div></div>
        <button class="rb heart" data-act="favCurrent"></button>`;
    }
    const a = $(".a", np);
    a.textContent = P.loading ? "Hazırlanıyor…" : t.artist;
    a.classList.toggle("loading", P.loading);
    const h = $(".heart", np), on = L.fav(t.id);
    h.innerHTML = on ? I.heart : I.heartO;
    h.classList.toggle("on", on);
    h.title = on ? "Favorilerden çıkar" : "Favorilere ekle";
  } else if (np.dataset.id !== "") {
    np.dataset.id = "";
    np.innerHTML = `<div class="tt"><div class="t" style="cursor:default">Henüz bir şey çalmıyor</div><div class="a">Bir şarkı ara ve çift tıkla</div></div>`;
  }
  $("#ppBtn").innerHTML = P.loading ? I.spinner : P.isPlaying() ? I.pause : I.play;
  $("#ppBtn").title = P.isPlaying() ? "Duraklat" : "Çal";
  $("#shuffleBtn").classList.toggle("on", P.shuffle);
  $("#repeatBtn").innerHTML = P.repeat === "one" ? I.repeatOne : I.repeat;
  $("#repeatBtn").classList.toggle("on", P.repeat !== "off");
  $("#t1").textContent = clock(P.duration());
  refreshItems();
  if (trackChanged) renderPanel();
  else renderPanelParts();
  const state = { track: t && plain(t), playing: !A.paused && !!A.src, loading: P.loading, shuffle: P.shuffle, repeat: P.repeat };
  const sig = JSON.stringify(state);
  if (sig !== lastPlayerState) { lastPlayerState = sig; api.player_state(state); }
}
function queueChanged() { renderQueue(); autoContinue(); }
/* kuyrukta son şarkıya gelinince benzer şarkılar (YouTube Music radyosu + YouTube Mix) sona eklenir */
function autoContinue() {
  const t = P.current;
  if (!t || S.settings.autoplay === false || P.repeat !== "off" || P.pos < P.order.length - 1 || P.autoFor === t.id) return;
  P.autoFor = t.id;
  api.radio(plain(t)).then(tracks => {
    if (!tracks || !tracks.length || !P.current || P.current.id !== t.id || P.pos < P.order.length - 1) return;
    const have = new Set(P.queue.map(x => x.id)), recent = new Set((S.lib.recent || []).slice(0, 15));
    const add = tracks.filter(x => !have.has(x.id) && !recent.has(x.id)).slice(0, 20);
    if (!add.length) return;
    const ended = A.ended;
    add.forEach(x => { P.queue.push(plain(x)); P.order.push(P.queue.length - 1); });
    renderQueue();
    if (ended) P.next(true);  // şarkı biz beklerken bittiyse hemen devam et
  });
}

/* ---------- ilerleme çubuğu: müziğe tepki veren alev perdesi ----------
   Çalınan kısım boyunca kesintisiz bir alev perdesi yanar. Hareketin tamamı şarkıdan gelir: perdenin her noktası
   bir ses frekansına bağlı (solda bas, başta tiz); ses yükselince o nokta uzar, susunca söner, vuruşta perde sıçrar.
   Renkler tabanda beyaz-altın, ortada pembe-eflatun, uçlarda mora dönüp söner. */
const flame = $("#flame"), fctx = flame.getContext("2d");
const parts = [];
let seeking = null, flameHover = false;
/* ses çözümleyici: iki <audio> da aynı çözümleyiciden geçer (kaynaklar hep aynı adresten: /stream, /cache, /music) */
let actx = null, analyser = null, freq = null;
const hookedAudio = new WeakSet();
function hookAudio() {
  try {
    if (!actx) {
      actx = new AudioContext();
      analyser = actx.createAnalyser();
      analyser.fftSize = 1024;
      analyser.smoothingTimeConstant = 0.5;
      analyser.connect(actx.destination);
      freq = new Uint8Array(analyser.frequencyBinCount);
      buildFx();
    }
    for (const el of AUDIO) if (!hookedAudio.has(el)) { hookLoudness(el, actx.createMediaElementSource(el)); hookedAudio.add(el); }
    if (actx.state === "suspended") actx.resume();
  } catch (e) { console.warn("ses çözümleyici", e); }
}
AUDIO.forEach(el => el.addEventListener("play", hookAudio));

/* ---------- ekolayzır ----------
   her oynatıcı → kendi dengeleme kazancı → fxIn → ön kazanç → 10 bant → sınırlayıcı → çözümleyici → hoparlör.
   Sınırlayıcı, ekolayzır da dengeleme de kapalıyken zincirden çıkar; ses hiç işlenmeden geçer. */
const EQ_FREQS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000];
const EQ_LABELS = ["31", "62", "125", "250", "500", "1K", "2K", "4K", "8K", "16K"];
const EQ_PRESETS = {
  flat: ["Düz", [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],
  bass: ["Bas", [6, 5, 4, 2, 0, 0, 0, 0, 0, 0]],
  treble: ["Tiz", [0, 0, 0, 0, 0, 0, 1, 3, 4, 5]],
  vocal: ["Vokal", [-2, -2, -1, 0, 2, 3, 3, 2, 0, -1]],
  pop: ["Pop", [-1, 0, 2, 3, 3, 1, 0, 0, 1, 1]],
  rock: ["Rock", [4, 3, 2, 0, -1, -1, 0, 2, 3, 4]],
  electronic: ["Elektronik", [5, 4, 1, 0, -2, 1, 0, 1, 4, 5]],
  acoustic: ["Akustik", [3, 3, 2, 1, 1, 1, 2, 2, 2, 1]],
  night: ["Gece", [3, 2, 1, 0, 0, 1, 1, 0, -1, -2]],
};
const eqOpts = () => {
  const e = S.settings.eq || {};
  return { on: !!e.on, preset: e.preset || "flat", gains: e.gains && e.gains.length === 10 ? e.gains : EQ_PRESETS.flat[1] };
};
let fxIn = null, fxPre = null, fxBands = [], fxLimiter = null, fxTail = null;
function makeBands(ctx) {
  return EQ_FREQS.map((f, i) => {
    const b = ctx.createBiquadFilter();
    b.type = i === 0 ? "lowshelf" : i === 9 ? "highshelf" : "peaking";
    b.frequency.value = f;
    b.Q.value = 1.41;  // bir oktav genişlik
    return b;
  });
}
/* eğri çizimi ve ön kazanç için, ses çalmıyorken de çalışan hesap düğümleri */
const eqProbe = makeBands(new OfflineAudioContext(1, 128, 48000));
const EQ_CURVE_HZ = Float32Array.from({ length: 160 }, (_, i) => 20 * Math.pow(1000, i / 159));
function eqResponse(gains) {
  const out = new Float32Array(EQ_CURVE_HZ.length), mag = new Float32Array(EQ_CURVE_HZ.length), phase = new Float32Array(EQ_CURVE_HZ.length);
  eqProbe.forEach((b, i) => {
    b.gain.value = gains[i];
    b.getFrequencyResponse(EQ_CURVE_HZ, mag, phase);
    for (let k = 0; k < out.length; k++) out[k] += 20 * Math.log10(mag[k]);
  });
  return out;
}
function buildFx() {
  fxIn = actx.createGain();
  fxPre = actx.createGain();
  fxBands = makeBands(actx);
  fxLimiter = actx.createDynamicsCompressor();
  fxLimiter.threshold.value = -1; fxLimiter.knee.value = 0; fxLimiter.ratio.value = 20;
  fxLimiter.attack.value = 0.003; fxLimiter.release.value = 0.15;
  fxIn.connect(fxPre);
  fxTail = fxBands.reduce((prev, band) => { prev.connect(band); return band; }, fxPre);
  fxLimiter.connect(analyser);
  applyFx();
}
function applyFx() {
  if (!actx || !fxIn) return;
  const eq = eqOpts(), gains = eq.on ? eq.gains : EQ_PRESETS.flat[1], t = actx.currentTime;
  fxBands.forEach((b, i) => b.gain.setTargetAtTime(gains[i], t, 0.03));
  // yükseltilen bantlar taşmasın: eğrinin en yüksek noktası kadar genel ses kısılır
  const peak = Math.max(0, ...eqResponse(gains));
  fxPre.gain.setTargetAtTime(Math.pow(10, -peak / 20), t, 0.03);
  const useLimiter = eq.on || S.settings.normalize !== false;
  if (fxTail.limited !== useLimiter) {
    try { fxTail.disconnect(); } catch (e) {}
    fxTail.connect(useLimiter ? fxLimiter : analyser);
    fxTail.limited = useLimiter;
  }
  AUDIO.forEach(applyLoudness);
}

/* ---------- ses dengeleme ----------
   Her şarkının yüksekliği çalarken ölçülür (BS.1770'e yakın: K ağırlığı + 400 ms'lik bloklar + geçitleme) ve hedefe göre
   kazanç hesaplanır. Sonuç saklanır: bir kez dinlenen şarkı sonraki sefer baştan doğru sesle başlar. İlk dinleyişte tipik
   bir değerle başlar, ölçüm oturdukça yavaşça ayarlanır. */
const LOUD_TYPICAL = -11, LOUD_SURE = 30;  // henüz ölçülmemiş şarkı için varsayım; ölçümün kesinleştiği süre (sn)
const LN = new Map(AUDIO.map(el => [el, { id: null, stored: null, blocks: [], node: null, meter: null, buf: null, saved: 0, lufs: null }]));
function hookLoudness(el, source) {
  const st = LN.get(el);
  st.node = actx.createGain();
  source.connect(st.node);
  st.node.connect(fxIn);
  const hp = actx.createBiquadFilter(), shelf = actx.createBiquadFilter();
  hp.type = "highpass"; hp.frequency.value = 38; hp.Q.value = -6.02;  // WebAudio'da Q dB cinsinden: 0,5
  shelf.type = "highshelf"; shelf.frequency.value = 1681; shelf.gain.value = 4;
  // sağ ve sol ayrı ölçülür: analyser tek başına sesi tek kanala indirir, stereo enerji yanlış çıkar
  const split = actx.createChannelSplitter(2);
  st.meter = [0, 1].map(ch => {
    const m = actx.createAnalyser();
    m.fftSize = 16384;  // ~340 ms; pencere arka plandayken zamanlayıcı yavaşlasa da yeterli örnek alınır
    split.connect(m, ch);
    return m;
  });
  st.buf = new Float32Array(16384);
  source.connect(hp); hp.connect(shelf); shelf.connect(split);
  applyLoudness(el, true);
}
function loudnessOf(st) {
  const b = st.blocks;
  if (!b.length) return null;
  const mean = a => a.reduce((s, x) => s + x, 0) / a.length;
  const gate = mean(b) * 0.1;  // göreli geçit: ortalamanın 10 LU altı (sessiz bölümler sayılmaz)
  const kept = b.filter(x => x >= gate);
  return -0.691 + 10 * Math.log10(mean(kept.length ? kept : b));
}
const measuredSeconds = st => st.blocks.length * 0.34;
function loudnessGain(st) {
  if (S.settings.normalize === false) return 0;
  const target = +S.settings.norm_target || -14;
  if (st.stored != null) return Math.max(-15, Math.min(6, target - st.stored));
  const seen = st.lufs != null && measuredSeconds(st) >= 8 ? st.lufs : LOUD_TYPICAL;
  return Math.max(-15, Math.min(3, target - seen));  // kesinleşmeden fazla yükseltme: sessiz girişten sonra nakarat patlamasın
}
function applyLoudness(el, instant = false) {
  const st = LN.get(el);
  if (!st.node) return;
  const g = Math.pow(10, loudnessGain(st) / 20);
  if (instant === true) { st.node.gain.cancelScheduledValues(0); st.node.gain.value = g; }
  else st.node.gain.setTargetAtTime(g, actx.currentTime, st.stored != null ? 0.05 : 4);
}
function saveLoudness(st) {
  const secs = measuredSeconds(st);
  if (!st.id || st.lufs == null || secs < LOUD_SURE || secs - st.saved < 15) return;
  st.saved = secs;
  api.set_loudness(st.id, st.lufs, secs);
}
function loudnessFor(el, id) {
  const st = LN.get(el);
  if (st.id === id) return;
  saveLoudness(st);
  Object.assign(st, { id, stored: null, blocks: [], saved: 0, lufs: null });
  applyLoudness(el, true);
  if (id) api.loudness(id).then(r => {
    if (st.id !== id || !r) return;
    st.stored = r.lufs;
    st.saved = r.seconds;
    applyLoudness(el, true);
  });
}
setInterval(() => {
  if (!actx || actx.state !== "running") return;
  for (const [el, st] of LN) {
    if (!st.meter || !st.id || el.paused || el.seeking || el.volume < 0.003 || el.readyState < 3) continue;
    let sum = 0;
    for (const m of st.meter) {
      m.getFloatTimeDomainData(st.buf);
      for (let i = 0; i < st.buf.length; i++) sum += st.buf[i] * st.buf[i];
    }
    const power = sum / st.buf.length / (el.volume * el.volume);  // oynatıcının ses düzeyi ölçüme karışmasın
    if (power < 1e-7) continue;  // -70 LUFS altı: mutlak geçit
    st.blocks.push(power);
    if (st.blocks.length % 6 === 0) {
      st.lufs = loudnessOf(st);
      if (st.stored == null) applyLoudness(el);
      saveLoudness(st);
    }
  }
}, 400);

/* ---------- ekolayzır ve ses dengeleme penceresi ---------- */
async function openAudioFx() {
  const NORM = [[-19, "Sessiz"], [-14, "Normal"], [-11, "Yüksek"]];
  let timer = null;
  const save = () => {
    clearTimeout(timer);
    timer = setTimeout(() => api.update_settings({ eq: S.settings.eq, normalize: S.settings.normalize, norm_target: S.settings.norm_target }), 250);
  };
  const setEq = changes => { S.settings = { ...S.settings, eq: { ...eqOpts(), ...changes } }; applyFx(); save(); };
  await modal(`<h3>Ekolayzır ve ses dengeleme</h3><p style="margin-bottom:0">Değişiklikler hemen duyulur ve kaydedilir.</p><div id="fxBody"></div>
    <div class="row-btns" style="margin-top:18px"><button class="pill fill" data-x="close">Bitti</button></div>`, (box, done) => {
    const curve = () => {
      const eq = eqOpts(), r = eqResponse(eq.gains), W = 400, H = 90;
      const pts = [...r].map((v, i) => `${(i / (r.length - 1) * W).toFixed(1)},${(H / 2 - Math.max(-15, Math.min(15, v)) / 15 * (H / 2 - 3)).toFixed(1)}`).join(" ");
      return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true"><line x1="0" x2="${W}" y1="${H / 2}" y2="${H / 2}" class="fx-zero"/>
        <polyline points="${pts}" vector-effect="non-scaling-stroke"/></svg>`;
    };
    const meter = () => {
      const st = LN.get(A), lufs = st && (st.stored ?? st.lufs);
      if (S.settings.normalize === false) return "Şarkılar özgün seviyesinde çalıyor.";
      if (!P.current || lufs == null) return "Bir şarkı çalınca yüksekliği ölçülür ve sonraki dinleyişler için saklanır.";
      const fmt = v => (v > 0 ? "+" : "") + v.toFixed(1).replace(".", ",").replace("-", "−");
      return `Bu şarkı: ${fmt(lufs)} LUFS · uygulanan ${fmt(loudnessGain(st))} dB${st.stored == null ? " (ölçülüyor)" : ""}`;
    };
    const draw = () => {
      const eq = eqOpts(), norm = S.settings.normalize !== false, target = +S.settings.norm_target || -14;
      $("#fxBody", box).innerHTML = `
        <div class="set-sec">Ekolayzır</div>
        <div class="set-row"><div><b>Ekolayzır</b><p>Kapalıyken ayarların saklanır, ses olduğu gibi çalar.</p></div><button class="switch ${eq.on ? "on" : ""}" data-fx="eq"><i></i></button></div>
        <div class="fx-eq ${eq.on ? "" : "dim"}">
          <div class="fx-presets">${Object.entries(EQ_PRESETS).map(([k, [name]]) => `<button class="fx-chip ${eq.preset === k ? "on" : ""}" data-preset="${k}" ${eq.on ? "" : "disabled"}>${name}</button>`).join("")}
            ${eq.preset === "custom" ? `<button class="fx-chip on" disabled>Özel</button>` : ""}</div>
          <div class="fx-curve">${curve()}</div>
          <div class="fx-bands">${eq.gains.map((g, i) => `<label title="${EQ_FREQS[i]} Hz"><span class="fx-db">${g > 0 ? "+" : ""}${g}</span>
            <input type="range" min="-12" max="12" step="1" value="${g}" data-band="${i}" aria-label="${EQ_FREQS[i]} Hz" style="--v:${(g + 12) / 24 * 100}%" ${eq.on ? "" : "disabled"}><span>${EQ_LABELS[i]}</span></label>`).join("")}</div>
        </div>
        <div class="set-sec">Ses dengeleme</div>
        <div class="set-row"><div><b>Ses seviyesini dengele</b><p>Şarkılar arasındaki ses farkını giderir.</p></div><button class="switch ${norm ? "on" : ""}" data-fx="norm"><i></i></button></div>
        <div class="set-row ${norm ? "" : "dim"}"><div><b>Seviye</b><p id="fxMeter">${esc(meter())}</p></div>
          <div class="seg">${NORM.map(([v, n]) => `<button data-target="${v}" class="${target === v ? "on" : ""}" ${norm ? "" : "disabled"}>${n}</button>`).join("")}</div></div>`;
    };
    box.addEventListener("click", e => {
      const t = e.target.closest("button");
      if (!t) return;
      if (t.dataset.x === "close") return done(null);
      if (t.dataset.fx === "eq") setEq({ on: !eqOpts().on });
      else if (t.dataset.fx === "norm") { S.settings = { ...S.settings, normalize: S.settings.normalize === false }; applyFx(); save(); }
      else if (t.dataset.preset) setEq({ preset: t.dataset.preset, gains: [...EQ_PRESETS[t.dataset.preset][1]] });
      else if (t.dataset.target) { S.settings = { ...S.settings, norm_target: +t.dataset.target }; applyFx(); save(); }
      else return;
      draw();
    });
    box.addEventListener("input", e => {
      const r = e.target.closest("[data-band]");
      if (!r) return;
      const gains = [...eqOpts().gains];
      gains[+r.dataset.band] = +r.value;
      const match = Object.keys(EQ_PRESETS).find(k => EQ_PRESETS[k][1].every((g, i) => g === gains[i]));
      setEq({ gains, preset: match || "custom" });
      r.style.setProperty("--v", (+r.value + 12) / 24 * 100 + "%");
      r.previousElementSibling.textContent = (+r.value > 0 ? "+" : "") + r.value;
      $(".fx-curve", box).innerHTML = curve();
      $$(".fx-chip", box).forEach(c => c.classList.toggle("on", c.dataset.preset === (match || "custom")));
    });
    box.addEventListener("change", e => { if (e.target.closest("[data-band]")) draw(); });
    box.addEventListener("dblclick", e => {  // çift tık: bandı sıfırla
      const r = e.target.closest("[data-band]");
      if (!r) return;
      const gains = [...eqOpts().gains];
      gains[+r.dataset.band] = 0;
      setEq({ gains, preset: Object.keys(EQ_PRESETS).find(k => EQ_PRESETS[k][1].every((g, i) => g === gains[i])) || "custom" });
      draw();
    });
    const tick = setInterval(() => {
      const m = $("#fxMeter", box);
      if (!m) clearInterval(tick); else m.textContent = meter();
    }, 1000);
    draw();
  }, "sheet");
}

/* ---------- dinleme kaydı: gerçekten çalınan süre, oturum oturum ---------- */
const LS = { session: null, track: null, seconds: 0, sent: 0, last: 0 };
function listenFlush() {
  if (LS.session && LS.seconds >= 5 && LS.seconds - LS.sent >= 1) {
    LS.sent = LS.seconds;
    api.listen(LS.session, plain(LS.track), Math.round(LS.seconds));
  }
}
function listenEnd() { listenFlush(); LS.session = null; LS.track = null; }
setInterval(() => {
  const now = performance.now(), dt = (now - LS.last) / 1000;
  LS.last = now;
  const t = P.current;
  if (!t || P.loading || A.paused || !A.src || A.readyState < 3) return;
  if (!LS.track || LS.track.id !== t.id) {
    listenEnd();
    LS.session = `${Date.now()}:${t.id}`; LS.track = t; LS.seconds = 0; LS.sent = 0;
    return;
  }
  LS.seconds += Math.min(dt, 5);  // pencere arka plandayken zamanlayıcı yavaşlar; uyku gibi uzun boşluklar sayılmaz
  if (LS.seconds - LS.sent >= 10) listenFlush();
}, 1000);
const STEP = 3;           // perdenin sütun aralığı (px)
let heights = new Float32Array(0), beat = 0, bassAvg = 0;
flame.addEventListener("pointerenter", () => flameHover = true);
flame.addEventListener("pointerleave", () => flameHover = false);
flame.addEventListener("pointerdown", e => {
  if (!P.current || !A.src || !P.duration()) return;
  flame.setPointerCapture(e.pointerId);
  seeking = Math.min(1, Math.max(0, e.offsetX / flame.clientWidth));
});
flame.addEventListener("pointermove", e => { if (seeking != null) seeking = Math.min(1, Math.max(0, e.offsetX / flame.clientWidth)); });
flame.addEventListener("pointerup", () => {
  if (seeking == null) return;
  A.currentTime = seeking * P.duration();
  seeking = null;
});
let lastFrame = 0;
function frame(now) {
  const dt = Math.min(3, (now - (lastFrame || now)) / 16.7) || 1;  // 60 fps'e göre adım
  lastFrame = now;
  const dpr = devicePixelRatio, w = flame.clientWidth, h = flame.clientHeight;
  if (flame.width !== Math.round(w * dpr) || flame.height !== Math.round(h * dpr)) { flame.width = Math.round(w * dpr); flame.height = Math.round(h * dpr); }
  fctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  fctx.clearRect(0, 0, w, h);
  const dur = P.duration(), pos = seeking != null ? seeking * dur : P.position();
  const x = dur ? Math.min(w - 2, Math.max(2, (w - 4) * pos / dur + 2)) : 2, y = h - 9;
  $("#t0").textContent = clock(pos);
  fctx.lineCap = "round";
  fctx.lineWidth = 4;
  fctx.strokeStyle = "#ffffff30";
  fctx.beginPath(); fctx.moveTo(2, y); fctx.lineTo(w - 2, y); fctx.stroke();
  const burning = !A.paused && !!A.src && !P.loading;
  // ses: frekanslar (0..1) ve bas vuruşu
  let spec = null, bass = 0;
  if (burning && analyser) {
    analyser.getByteFrequencyData(freq);
    for (let i = 1; i < 7; i++) bass += freq[i];
    bass = Math.min(1, bass / (6 * 255) + (bass > 0 ? -20 * Math.log10(Math.max(0.01, A.volume || 0.01)) / (analyser.maxDecibels - analyser.minDecibels) : 0));
    spec = freq;
  }
  bassAvg += (bass - bassAvg) * 0.05 * dt;
  if (bass > bassAvg * 1.18 + 0.04) beat = Math.min(1, beat + 0.6);  // vuruş
  beat *= Math.pow(0.9, dt);
  // sütun yükseklikleri: gürültü + frekans + vuruş; yumuşak geçişle hedefe gider
  const cols = Math.ceil(w / STEP) + 1;
  if (heights.length !== cols) heights = new Float32Array(cols);
  const maxH = y - 2;
  const span = Math.max(1, x - 2);
  let prevBin = 1;
  // çözümleyici sesi ses düzeyi uygulandıktan sonra duyar: kısık seste alev küçülmesin diye farkı geri ekle (dB ölçeği)
  const volComp = spec ? -20 * Math.log10(Math.max(0.01, A.volume || 0.01)) * 255 / (analyser.maxDecibels - analyser.minDecibels) : 0;
  for (let c = 0; c < cols; c++) {
    const px = c * STEP;
    let target = 0;
    if (burning && px <= x) {
      if (spec) {
        // çalınan kısım boyunca tüm frekanslar (logaritmik): solda bas (~40 Hz), başta tiz (~16 kHz)
        const f = Math.min(1, Math.max(0, (px - 2) / span)), bf = Math.pow(370, f), lo = Math.floor(bf);
        let v;
        if (lo - prevBin > 1) { v = 0; for (let b = prevBin + 1; b <= lo; b++) v = Math.max(v, spec[b]); }  // geniş aralık: en güçlüsü
        else v = spec[lo] + (spec[Math.min(spec.length - 1, lo + 1)] - spec[lo]) * (bf - lo);           // dar aralık: ara değer
        prevBin = lo;
        v = Math.min(255, v + (v > 0 ? volComp : 0));
        let s = Math.max(0, (v / 255 - 0.3) / 0.7) * (0.75 + 0.8 * f);  // sessiz kısımlar dibe, tizler biraz yükseltilir
        s = Math.pow(Math.min(1, s), 1.7) * 0.9;  // tepeler tavana yapışmasın: inişler-çıkışlar belirgin
        target = maxH * Math.min(1, s * (0.9 + 0.35 * beat));
      } else target = maxH * 0.2;  // ses çözümlenemiyorsa sabit, alçak bir kor
    }
    heights[c] += (target - heights[c]) * Math.min(1, (target > heights[c] ? 0.85 : 0.35) * dt);  // müziği yakından izle
  }
  const lastCol = Math.min(cols - 1, Math.ceil(x / STEP));
  if (x > 4 && heights[0] + heights[lastCol >> 1] + heights[lastCol] > 0.3) {
    fctx.globalCompositeOperation = "lighter";
    const layer = (scale, stops, blur) => {
      const g = fctx.createLinearGradient(0, y - maxH * scale, 0, y + 1);
      stops.forEach(([o, col]) => g.addColorStop(o, col));
      fctx.fillStyle = g;
      fctx.filter = blur ? `blur(${blur}px)` : "none";
      fctx.beginPath();
      fctx.moveTo(2, y + 1);
      let prevX = 2, prevY = y - heights[0] * scale;
      fctx.lineTo(prevX, prevY);
      for (let c = 1; c <= lastCol; c++) {
        const px = Math.min(x, c * STEP), py = y - heights[c] * scale;
        fctx.quadraticCurveTo(prevX, prevY, (prevX + px) / 2, (prevY + py) / 2);  // yumuşak dalgalı üst kenar
        prevX = px; prevY = py;
      }
      fctx.lineTo(x, y - heights[lastCol] * scale * 0.4);
      fctx.lineTo(x, y + 1);
      fctx.closePath();
      fctx.fill();
    };
    layer(1, flamePal.l1, 2);
    layer(0.6, flamePal.l2, 1);
    layer(0.25, flamePal.l3, 0);
    fctx.filter = "none";
    // kıvılcımlar: vuruşta ve baş kısımda
    const sparks = beat * 1.4 * dt;  // yalnızca vuruşlarda
    for (let k = 0; k < sparks; k++) {
      if (Math.random() > sparks - k) break;
      const sx = Math.random() < 0.5 ? x - Math.random() * 40 : 2 + Math.random() * (x - 2);
      parts.push({ x: sx, y: y - 2, vx: (Math.random() - 0.5) * 0.8, vy: -(0.8 + Math.random() * 1.4) * (1 + beat), life: 1, decay: 0.025 + Math.random() * 0.02 });
    }
  }
  for (let k = parts.length - 1; k >= 0; k--) {
    const p = parts[k];
    p.life -= p.decay * dt;
    if (p.life <= 0 || p.y < 0) { parts.splice(k, 1); continue; }
    p.x += (p.vx + Math.sin(now / 120 + k) * 0.3) * dt;
    p.y += p.vy * dt;
    fctx.globalAlpha = p.life;
    fctx.fillStyle = flamePal.sp[p.life > 0.6 ? 0 : p.life > 0.3 ? 1 : 2];
    fctx.fillRect(p.x, p.y, 1.8, 1.8);
  }
  fctx.globalAlpha = 1;
  fctx.globalCompositeOperation = "source-over";
  if ((flameHover || seeking != null) && dur) { fctx.fillStyle = "#fff"; fctx.beginPath(); fctx.arc(x, y, 6, 0, 7); fctx.fill(); }
  requestAnimationFrame(frame);
}

/* ---------- ses düzeyi ---------- */
const vol = $("#volume");
let muted = null, volTimer = null, volPos = 0.7;
/* kaydırıcı konumu → gerçek ses: kulak sesi logaritmik duyar, doğrusal ayarda %50 bile neredeyse tam ses gibi gelir.
   Küp eğrisi: %70 → %34 (-9 dB), %50 → %12,5 (-18 dB). Üstüne Ayarlar'daki "en yüksek ses" sınırı uygulanır. */
const volumeGain = v => Math.pow(v, 3) * ((S.settings.max_volume ?? 100) / 100);
function setVolume(v, save = true) {
  volPos = v;
  masterVolume = volumeGain(v);
  if (!fade) A.volume = masterVolume;
  vol.value = Math.round(v * 100);
  vol.style.setProperty("--v", vol.value + "%");
  $("#muteBtn").innerHTML = v === 0 ? I.mute : v < 0.5 ? I.volumeLow : I.volume;
  if (save) { clearTimeout(volTimer); volTimer = setTimeout(() => api.set_volume(v), 500); }
}
vol.addEventListener("input", () => { muted = null; setVolume(vol.value / 100); });
$("#muteBtn").onclick = () => {
  if (muted == null) { muted = volPos || 0.7; setVolume(0); }
  else { setVolume(muted); muted = null; }
};

/* ---------- sağ panel ---------- */
function togglePanel(open = !S.panelOpen) {
  S.panelOpen = open;
  $("#app").classList.toggle("panel-open", open);
  $("#panelBtn").classList.toggle("on", open);
  if (open) renderPanel();
  else { const v = $("#pvideo"); if (v) { v.pause(); v.removeAttribute("src"); v.load(); } }
}
function renderPanel() {
  if (!S.panelOpen) return;
  const t = P.current, box = $("#panelInner");
  if (!t) {
    box.innerHTML = `<div class="p-head"><span class="grow">Şimdi çalıyor</span><button class="round-btn" data-act="closePanel">${I.close}</button></div>
      <div class="empty" style="padding:20px 0"><b>Henüz bir şey çalmıyor</b><p>Bir şarkı çalınca kapağı, videosu, sanatçı bilgisi ve sıradakiler burada görünür.</p></div>`;
    return;
  }
  box.innerHTML = `<div class="p-head"><span class="grow">${esc(P.source && P.source.startsWith("album:") ? (L.album(P.source.slice(6)) || {}).name || "Şimdi çalıyor" : "Şimdi çalıyor")}</span>
      <div class="seg"><button data-act="panelMode" data-mode="cover" class="${S.panelMode === "cover" ? "on" : ""}">Kapak</button><button data-act="panelMode" data-mode="video" class="${S.panelMode === "video" ? "on" : ""}">Video</button></div>
      <button class="round-btn" data-act="closePanel" title="Kapat">${I.close}</button></div>
    <div id="pMedia"></div><div id="pTitle"></div><div id="pDl"></div><div id="pLyrics"></div><div id="pInfo"></div><div id="pQueue"></div>`;
  renderMedia();
  renderPanelParts();
  renderLyrics();
  renderInfo();
  renderQueue();
}
function renderMedia() {
  const t = P.current, box = $("#pMedia");
  if (!box || !t) return;
  if (S.panelMode === "video") {
    box.className = "p-media wide";
    box.innerHTML = `<video id="pvideo" muted playsinline style="background-image:url('${bigThumb(t)}')"></video><div class="vmsg">Video yükleniyor…</div>`;
    const v = $("#pvideo");
    v.addEventListener("loadeddata", () => { const m = $(".vmsg", box); if (m) m.remove(); syncVideo(true); });
    v.addEventListener("error", async () => {
      // akış adresi yenilenmiş olabilir: bir kez yenisiyle dene
      if (!v.dataset.retried && !L.video(t.id)) {
        v.dataset.retried = 1;
        const res = await api.stream(t, true);
        if (P.current && P.current.id === t.id && res.video && $("#pvideo") === v) { P.streams[t.id] = res; v.src = res.video; return; }
      }
      const m = $(".vmsg", box); if (m) m.textContent = "Video oynatılamadı";
    });
    const local = L.video(t.id);
    if (local) v.src = `/videos/${encodeURIComponent(local)}`;
    else if (P.streams[t.id] && P.streams[t.id].video && P.streams[t.id].expire - Date.now() / 1000 > 60) v.src = P.streams[t.id].video;
    else {
      const id = t.id;
      api.stream(t).then(res => {
        if (!P.current || P.current.id !== id || S.panelMode !== "video") return;
        if (res.error || !res.video) { const m = $(".vmsg", box); if (m) m.textContent = res.error || "Bu şarkının videosu yok"; return; }
        P.streams[id] = res;
        const vv = $("#pvideo"); if (vv) vv.src = res.video;
      });
    }
  } else {
    box.className = "p-media";
    box.innerHTML = `<img class="${squareArt(t) ? "" : "hq"}" src="${bigThumb(t)}" data-fallback="${thumb(t)}">`;
  }
}
function syncVideo(force = false) {
  const v = $("#pvideo");
  if (!v || !v.getAttribute("src") || v.readyState < 1) return;
  if (Math.abs(v.currentTime - A.currentTime) > 0.35 || force) v.currentTime = A.currentTime;
  if (A.paused || P.loading) v.pause(); else v.play().catch(() => {});
}
setInterval(() => { if (S.panelOpen && S.panelMode === "video") syncVideo(); }, 1000);

function renderPanelParts() {
  if (!S.panelOpen || !P.current) return;
  const t = P.current, title = $("#pTitle"), dl = $("#pDl");
  if (!title) return;
  title.innerHTML = `<div class="p-title"><div class="tt"><div class="t">${esc(t.title)}</div><div class="a">${esc(t.artist)}</div></div>
    <button class="rb heart ${L.fav(t.id) ? "on" : ""}" data-act="favCurrent" title="Favori">${L.fav(t.id) ? I.heart : I.heartO}</button></div>`;
  const button = kind => {
    const [state, icon] = dlIcon(t.id, kind), label = kind === "video" ? "Video" : "Ses";
    const text = state === "done" ? `${label} indirildi` : state === "busy" ? (S.dl.progress[dlKey(t.id, kind)] == null ? "Sırada…" : `%${(S.dl.progress[dlKey(t.id, kind)] * 100) | 0} · iptal`) : `${label} indir`;
    return `<button data-act="panelDl" data-kind="${kind}" class="${state}" title="${state === "busy" ? "İptal etmek için tıkla" : ""}">${state === "busy" ? icon : state === "done" ? I.check : kind === "video" ? I.video : I.music}${text}</button>`;
  };
  dl.innerHTML = `<div class="p-dl">${button("audio")}${button("video")}</div>`;
}
async function renderInfo() {
  const t = P.current, box = $("#pInfo");
  if (!box || !t) return;
  const info = S.info[t.id];
  if (!info) {
    box.innerHTML = `<div class="p-card"><h4>Sanatçı hakkında</h4><div class="muted">Yükleniyor…</div></div>`;
    if (!S.infoLoading.has(t.id)) {
      S.infoLoading.add(t.id);
      S.info[t.id] = await api.track_info(t);
      S.infoLoading.delete(t.id);
      if (P.current && P.current.id === t.id) renderInfo();
    }
    return;
  }
  const name = info.artist || info.channel || t.artist;
  const stats = [info.followers != null && `${num(info.followers)} abone`, info.views != null && `${num(info.views)} görüntülenme`, info.year, info.album && `Albüm: ${esc(info.album)}`].filter(Boolean);
  box.innerHTML = `<div class="p-card"><h4>Sanatçı hakkında</h4><div class="big">${esc(name)}</div>
    ${stats.length ? `<div class="stats">${stats.map(s => `<span>${s}</span>`).join("")}</div>` : ""}
    ${info.description ? `<div class="desc">${esc(info.description)}</div>` : ""}
    <div class="btns"><button class="pill" data-act="artist" data-artist="${esc(name)}">${I.user} Sanatçı sayfası</button>
    ${info.channel_url ? `<button class="pill" data-act="openUrl" data-url="${esc(info.channel_url)}">${I.external} Kanal</button>` : ""}
    <button class="pill" data-act="openUrl" data-url="${esc(t.url)}">${I.external} YouTube</button></div></div>`;
}
/* şarkı sözleri: şarkı başladıktan sonra arka planda gelir; zamanlıysa çalan satır vurgulanır */
S.lyrics = {};
async function loadLyrics(track) {
  if (S.lyrics[track.id]) return;
  S.lyrics[track.id] = { loading: true };
  renderLyrics();
  const data = await api.lyrics(plain(track));
  S.lyrics[track.id] = data.error ? null : data;
  if (P.current && P.current.id === track.id) renderLyrics();
}
let lyricLine = -1;
function renderLyrics() {
  const box = $("#pLyrics"), t = P.current;
  if (!box || !t) return;
  const data = S.lyrics[t.id];
  lyricLine = -1;
  if (!data) { box.innerHTML = ""; return; }
  if (data.loading) { box.innerHTML = `<div class="p-card lyrics"><h4>Şarkı sözleri</h4><div class="muted">Aranıyor…</div></div>`; return; }
  if (data.none) { box.innerHTML = `<div class="p-card lyrics"><h4>Şarkı sözleri</h4><div class="muted" style="font-size:13px">Bu şarkının sözleri bulunamadı.</div></div>`; return; }
  const body = data.synced
    ? `<div class="lines" id="lyricLines">${data.synced.map(([time, line], i) => `<p data-i="${i}" data-t="${time}">${esc(line) || "♪"}</p>`).join("")}</div>`
    : `<div class="lines plain">${esc(data.plain).replace(/\n/g, "<br>")}</div>`;
  box.innerHTML = `<div class="p-card lyrics"><h4>Şarkı sözleri${data.synced ? "" : '<span class="muted" style="font-size:12px;font-weight:600">zamanlı değil</span>'}</h4>${body}</div>`;
  const lines = $("#lyricLines");
  if (lines) lines.addEventListener("click", e => { const p = e.target.closest("p"); if (p && A.getAttribute("src")) A.currentTime = +p.dataset.t; });
  syncLyrics();
}
function syncLyrics() {
  const lines = $("#lyricLines"), t = P.current, data = t && S.lyrics[t.id];
  if (!lines || !data || !data.synced) return;
  const now = A.currentTime + 0.25;
  let i = data.synced.length - 1;
  while (i >= 0 && data.synced[i][0] > now) i--;
  if (i === lyricLine) return;
  lyricLine = i;
  $$("p.on", lines).forEach(p => p.classList.remove("on"));
  const p = lines.children[i];
  if (p) {
    p.classList.add("on");
    lines.scrollTo({ top: p.offsetTop - lines.clientHeight / 2 + p.clientHeight / 2, behavior: "smooth" });
  } else lines.scrollTo({ top: 0, behavior: "smooth" });
}
setInterval(() => { if (S.panelOpen) syncLyrics(); }, 200);

function renderQueue() {
  const box = $("#pQueue");
  if (!S.panelOpen || !box) return;
  const items = P.upcoming(40);
  registerList("panelq", items.map(([, t]) => t), { kind: "queue", key: "queue" });
  box.innerHTML = `<div class="p-card"><h4>Sırada${items.length ? `<button class="textbtn" data-act="clearQueue">Temizle</button>` : ""}</h4>
    ${items.length ? items.map(([index, t], i) => `<div class="qrow" data-list="panelq" data-i="${i}" data-qi="${index}" data-tid="${esc(t.id)}" data-act="jump">
      <img loading="lazy" src="${thumb(t)}"><div class="tt"><div class="t">${esc(t.title)}</div><div class="a">${esc(t.artist)}</div></div>
      <button class="rb" data-act="unqueue" title="Kuyruktan çıkar">${I.close}</button></div>`).join("")
      : `<div class="muted" style="font-size:13px">Sırada şarkı yok. ${S.settings.autoplay === false ? "Bir şarkının ⋯ menüsünden “Kuyruğa ekle”yi kullan." : "Bu şarkı bitince benzer şarkılarla devam edilecek."}</div>`}</div>`;
}

/* ---------- işlemler ---------- */
async function syncLib() { setLib(await api.snapshot()); }
async function toggleFavorite(track) {
  const added = await api.toggle_favorite(plain(track));
  toast(added ? "Favorilere eklendi" : "Favorilerden çıkarıldı");
}
async function download(track, kind = "audio") {
  const key = dlKey(track.id, kind);
  if (busy(key)) { api.cancel_download(key); return; }
  const message = await api.download(plain(track), kind);
  if (message) toast(message);
}
async function createAlbum({ folder = null, track = null } = {}) {
  const name = await ask("Yeni albüm", "Albüm adı", `Albümüm #${Object.keys(S.lib.albums).length + 1}`);
  if (!name) return;
  if (folder) { S.expanded.add(folder); saveExpanded(); }
  const id = await api.create_album(name, folder, track ? [plain(track)] : []);
  await syncLib();
  if (track) toast(`“${short(name, 30)}” oluşturuldu ve şarkı eklendi`);
  else openPage("album", id);
}
async function createFolder(moveAlbum = null) {
  const name = await ask("Yeni klasör", "Klasör adı", "Yeni klasör");
  if (!name) return;
  const id = await api.create_folder(name);
  S.expanded.add(id); saveExpanded();
  if (moveAlbum) await api.move_album(moveAlbum, id);
  await syncLib();
}
async function addToAlbum(albumId, track) {
  const ok = await api.add_to_album(albumId, plain(track));
  toast(ok ? `“${short(L.album(albumId).name, 30)}” albümüne eklendi` : "Bu şarkı zaten albümde");
}
async function removeDownload(track) {
  if (!await confirmBox("İndirme silinsin mi?", `“${short(track.title, 60)}” cihazından silinecek. Favori ve albümlerde kalmaya devam eder.`)) return;
  if (P.current && P.current.id === track.id && P.local) {  // dosya çalınırken silinemez: akışa geç
    P.resumeAt = [track.id, A.currentTime];
    const wasPlaying = !A.paused;
    A.removeAttribute("src"); A.load();
    await sleep(300);
    await api.remove_download(track.id);
    await syncLib();
    if (wasPlaying) P.playCurrent();
  } else await api.remove_download(track.id);
  toast("İndirme silindi");
}
async function loadPlaylist(pl) {
  if (S.playlists[pl.id]) return S.playlists[pl.id];
  const res = await api.playlist(pl.id);
  if (res.tracks) { S.playlists[pl.id] = res.tracks; delete S.playlistErrors[pl.id]; return res.tracks; }
  S.playlistErrors[pl.id] = res.error;
  return null;
}
async function playPlaylist(pl) {
  const src = `playlist:${pl.id}`;
  if (P.source === src && P.current) { P.toggle(); return; }
  if (!S.playlists[pl.id]) toast("Albüm yükleniyor…");
  const tracks = await loadPlaylist(pl);
  if (tracks && tracks.length) P.playList(tracks, 0, src);
  else toast(`Albüm açılamadı: ${S.playlistErrors[pl.id] || "şarkı yok"}`, true);
}
async function savePlaylist(pl, download = false) {
  if (!S.playlists[pl.id]) toast("Albüm yükleniyor…");
  const res = await api.save_playlist(pl, download);
  await syncLib();
  toast(res.error || res.message, !!res.error);
}
function doSearch(query) {
  query = (query || "").trim();
  if (!query) return;
  $("#searchInput").value = query;
  $("#searchClear").classList.toggle("hidden", false);
  const token = ++S.search.token;
  S.search = { query, loading: true, tracks: [], videos: [], albums: [], artists: [], error: null, token };
  openPage("search", null, { keep: false });
  api.search(query).then(res => {
    if (token !== S.search.token) return;
    S.search = { query, loading: false, tracks: res.tracks || [], videos: res.videos || [], albums: res.albums || [], artists: res.artists || [], error: res.error || (!res.tracks?.length ? "Sonuç bulunamadı. Başka bir şey dene." : null), token };
    if (S.page.kind === "search") renderPage(true);
  });
}
function setRecent(list) {
  S.lib.recent_searches = list;
  renderSearchDrop();
  if (S.page.kind === "search" && !S.search.query) renderPage(true);
}
function renderSearchDrop() {
  const drop = $("#searchDrop"), input = $("#searchInput");
  const text = input.value.trim().toLocaleLowerCase("tr");
  const items = S.lib.recent_searches.filter(q => !text || q.toLocaleLowerCase("tr").includes(text)).slice(0, 8);
  if (document.activeElement !== input || !items.length) { drop.classList.add("hidden"); return; }
  drop.innerHTML = `<div class="sh">Son aramalar<button class="textbtn" data-act="forgetAll">Geçmişi temizle</button></div>` +
    items.map(q => `<div class="ri" data-act="searchFor" data-q="${esc(q)}">${stroke('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', 2)}<span>${esc(q)}</span>
      <button class="rb" data-act="forget" data-q="${esc(q)}" title="Geçmişten sil">${I.close}</button></div>`).join("");
  drop.classList.remove("hidden");
}
function saveExpanded() { localStorage.setItem("expanded", JSON.stringify([...S.expanded])); }

function trackMenu(track, ctx, x, y) {
  const albums = L.allAlbums();
  const items = [
    { label: "Çal", act: () => P.playList([track], 0, `single:${track.id}`) },
    { label: "Sıradaki olarak çal", act: () => P.playNext(track) },
    { label: "Kuyruğa ekle", act: () => P.enqueue(track) },
    "-",
    { label: "Albüme ekle", sub: [...albums.map(([id, a]) => ({ label: a.name, act: () => addToAlbum(id, track) })), ...(albums.length ? ["-"] : []), { label: "+ Yeni albüm…", act: () => createAlbum({ track }) }] },
  ];
  if (ctx && ctx.kind === "album") items.push({ label: "Bu albümden çıkar", act: () => api.remove_from_album(ctx.album, track.id) });
  if (ctx && ctx.kind === "queue") items.push({ label: "Kuyruktan çıkar", act: () => P.removeAt(ctx.index) });
  items.push({ label: L.fav(track.id) ? "Favorilerden çıkar" : "Favorilere ekle", act: () => toggleFavorite(track) });
  if (L.dl(track.id)) items.push({ label: "İndirmeyi sil", act: () => removeDownload(track) });
  else if (busy(track.id)) items.push({ label: "İndirmeyi iptal et", act: () => api.cancel_download(track.id) });
  else items.push({ label: "İndir", act: () => download(track) });
  if (!L.video(track.id) && !busy(dlKey(track.id, "video"))) items.push({ label: "Videoyu indir (MP4)", act: () => download(track, "video") });
  items.push("-", { label: "YouTube'da aç", act: () => api.open_url(track.url) });
  menu(items, x, y);
}
function albumMenu(id, x, y) {
  const album = L.album(id), tracks = L.albumTracks(id), folders = L.folders();
  const items = [];
  if (tracks.length) items.push({ label: "Çal", act: () => P.playList(tracks, 0, `album:${id}`) }, { label: "Tümünü indir", act: async () => { const m = await api.download_all(tracks.map(plain)); if (m) toast(m); } }, "-");
  items.push({ label: "Yeniden adlandır…", act: async () => { const n = await ask("Yeniden adlandır", "Albüm adı", album.name); if (n) api.rename_album(id, n); } });
  items.push({ label: "Klasöre taşı", sub: [
    ...folders.map(([fid, f]) => ({ label: f.name, checked: album.folder === fid, act: () => { S.expanded.add(fid); saveExpanded(); api.move_album(id, fid); } })),
    ...(folders.length ? ["-"] : []),
    ...(album.folder ? [{ label: "Klasörden çıkar", act: () => api.move_album(id, null) }] : []),
    { label: "+ Yeni klasör…", act: () => createFolder(id) }] });
  items.push("-", { label: "Albümü sil", danger: true, act: async () => {
    if (await confirmBox("Albüm silinsin mi?", `“${album.name}” silinecek. İndirdiğin şarkılar ve favorilerin silinmez.`)) { await api.delete_album(id); toast("Albüm silindi"); }
  } });
  menu(items, x, y);
}
function folderMenu(id, x, y) {
  const folder = S.lib.folders[id];
  menu([
    { label: "Bu klasörde yeni albüm…", act: () => createAlbum({ folder: id }) },
    { label: "Yeniden adlandır…", act: async () => { const n = await ask("Yeniden adlandır", "Klasör adı", folder.name); if (n) api.rename_folder(id, n); } },
    "-",
    { label: "Klasörü sil", danger: true, act: async () => { if (await confirmBox("Klasör silinsin mi?", `“${folder.name}” silinecek. İçindeki albümler silinmez, kitaplığa taşınır.`)) api.delete_folder(id); } },
  ], x, y);
}

/* tıklamalar: data-act ile */
const ACT = {
  statsPeriod: el => { S.statsPeriod = el.dataset.k; renderPage(true); },
  play(el) {
    const holder = el.closest("[data-list]"), list = S.lists[holder.dataset.list], i = +holder.dataset.i, t = list.tracks[i];
    if (P.current && P.current.id === t.id) P.toggle();
    else P.playList(list.tracks, i, list.ctx.key);
  },
  playAll(el) {
    const list = S.lists[el.closest("[data-list]").dataset.list];
    if (list && list.tracks.length) P.playCollection(list.tracks, list.ctx.key);
  },
  shuffleAll(el) {
    const list = S.lists[el.dataset.list];
    P.playList(list.tracks, Math.floor(Math.random() * list.tracks.length), list.ctx.key, true);
  },
  fav: el => toggleFavorite(itemTrack(el)),
  favCurrent: () => P.current && toggleFavorite(P.current),
  dl(el) {
    const t = itemTrack(el);
    if (L.dl(t.id)) toast("Bu şarkı indirildi; silmek için ⋯ menüsünü kullan");
    else download(t);
  },
  menu(el) {
    const holder = el.closest("[data-list]"), t = itemTrack(el), r = el.getBoundingClientRect();
    trackMenu(t, S.lists[holder.dataset.list].ctx, r.left - 180, r.bottom + 4);
  },
  open: el => openPage(el.dataset.page, el.dataset.ref || null),
  folder(el) { const id = el.dataset.folder; S.expanded.has(id) ? S.expanded.delete(id) : S.expanded.add(id); saveExpanded(); renderSide(); },
  newAlbum: () => createAlbum(),
  plopen: el => openPage("playlist", S.plShown[el.closest("[data-pl]").dataset.pl]),
  plplay: el => playPlaylist(S.plShown[el.closest("[data-pl]").dataset.pl]),
  pldl(el) {
    const pl = S.plShown[el.closest("[data-pl]").dataset.pl], saved = L.albumBySource(pl.id);
    if (saved && L.albumTracks(saved).every(t => L.dl(t.id))) { toast("Albümün tamamı indirildi"); return; }
    savePlaylist(pl, true);
  },
  plsave: el => savePlaylist(S.plShown[el.dataset.pl]),
  plretry(el) { delete S.playlistErrors[S.plShown[el.dataset.pl].id]; renderPage(true); },
  unalbum(el) {
    const list = S.lists[el.closest("[data-list]").dataset.list], t = itemTrack(el);
    api.remove_from_album(list.ctx.album, t.id);
    toast(`“${short(t.title, 40)}” albümden çıkarıldı · Geri al: Ctrl+Z`);
  },
  undo: () => undo(),
  artist: el => openPage("artist", { id: el.dataset.aid || null, name: el.dataset.artist || "" }),
  artistMore(el) { S.artistMore = S.artistMore === el.dataset.id ? null : el.dataset.id; renderPage(true); },
  artistRetry(el) { delete S.artistErrors[el.dataset.k]; renderPage(true); },
  async artistRadio(el) {
    const src = `radio:${el.dataset.radio}`;
    if (P.source === src && P.current) { P.toggle(); return; }
    toast(`${el.dataset.name} radyosu hazırlanıyor…`);
    const res = await api.artist_radio(el.dataset.radio);
    if (res.tracks && res.tracks.length) P.playList(res.tracks, 0, src);
    else toast(`Radyo açılamadı: ${res.error || "şarkı yok"}`, true);
  },
  async forget(el) { setRecent(await api.remove_recent_search(el.dataset.q)); },
  async forgetAll() { setRecent(await api.clear_recent_searches()); toast("Arama geçmişi temizlendi"); },
  searchFor(el) { doSearch(el.dataset.q); $("#searchInput").blur(); },
  homeRefresh() { toast("Öneriler yenileniyor…"); api.home(true).then(h => { S.home = h; if (S.page.kind === "home") renderPage(true); }); },
  downloadAll: async el => { const list = S.lists[el.closest("[data-list]").dataset.list]; const m = await api.download_all(list.tracks.map(plain)); if (m) toast(m); },
  albumMenu(el) { const r = el.getBoundingClientRect(); albumMenu(el.dataset.ref, r.left, r.bottom + 4); },
  sortMenu(el) {
    const v = view(el.dataset.key);
    menuAt(SORTS.map(([k, label]) => ({ label, checked: v.sort === k, act: () => { v.sort = k; el.innerHTML = `${esc(label)} ${I.down}`; fillList(); } })), el);
  },
  focusSearch() { const i = $("#searchInput"); i.focus(); i.select(); },
  cancel: el => api.cancel_download(el.dataset.key),
  cancelAll: () => S.dl.active.forEach(a => api.cancel_download(a.key)),
  retry: el => api.retry_download(el.dataset.key),
  dismiss: el => api.dismiss_failed(el.dataset.key),
  openVideo: el => api.open_video(el.dataset.id),
  async removeVideo(el) {
    const t = L.t(el.dataset.id);
    if (await confirmBox("Video silinsin mi?", `“${short(t.title, 60)}” videosu cihazından silinecek.`)) { await api.remove_video(t.id); toast("Video silindi"); }
  },
  openFolder: () => api.open_music_folder(),
  openUrl: el => api.open_url(el.dataset.url),
  showPanel: () => togglePanel(true),
  closePanel: () => togglePanel(false),
  panelMode(el) { S.panelMode = el.dataset.mode; renderPanel(); },
  panelDl: el => P.current && download(P.current, el.dataset.kind),
  jump: el => P.jumpTo(+el.dataset.qi),
  unqueue: el => P.removeAt(+el.closest("[data-qi]").dataset.qi),
  clearQueue: () => P.clearQueue(),
};
document.addEventListener("click", e => {
  if (D.suppressClick) return;
  const el = e.target.closest("[data-act]");
  if (!el || el.disabled) return;
  const fn = ACT[el.dataset.act];
  if (fn) { e.stopPropagation(); fn(el, e); }
});
document.addEventListener("dblclick", e => {
  const row = e.target.closest(".row");
  if (row && !e.target.closest("button")) {
    const list = S.lists[row.dataset.list];
    P.playList(list.tracks, +row.dataset.i, list.ctx.key);
  }
});
document.addEventListener("contextmenu", e => {
  e.preventDefault();
  const item = e.target.closest("[data-tid][data-list]");
  if (item) {
    const list = S.lists[item.dataset.list], ctx = { ...list.ctx, index: item.dataset.qi != null ? +item.dataset.qi : null };
    trackMenu(itemTrack(item), ctx, e.clientX, e.clientY);
    return;
  }
  const album = e.target.closest("[data-album]");
  if (album) return albumMenu(album.dataset.album, e.clientX, e.clientY);
  const folder = e.target.closest("[data-folder]");
  if (folder) return folderMenu(folder.dataset.folder, e.clientX, e.clientY);
  const pl = e.target.closest("[data-pl]");
  if (pl) {
    const p = S.plShown[pl.dataset.pl];
    menu([{ label: "Çal", act: () => playPlaylist(p) }, { label: "Kitaplığa kaydet", act: () => savePlaylist(p) },
      { label: "Kaydet ve tümünü indir", act: () => savePlaylist(p, true) }, "-", { label: "YouTube'da aç", act: () => api.open_url(p.url) }], e.clientX, e.clientY);
  }
});

/* fareyle bir şarkının üzerinde durunca: tıklanacak gibi, şimdiden hazırla */
let hoverTimer = null, hoverEl = null;
document.addEventListener("pointerover", e => {
  const el = e.target.closest(".row, .card[data-tid]");
  if (el === hoverEl) return;
  hoverEl = el;
  clearTimeout(hoverTimer);
  if (el) hoverTimer = setTimeout(() => { const t = itemTrack(el); if (t && !L.dl(t.id)) api.prefetch([plain(t)]); }, 450);
});

/* ---------- sürükle-bırak ---------- */
const D = {
  src: null, start: null, ghost: null, target: null, after: false, line: null, suppressClick: false, scrollTimer: null, pointer: [0, 0],

  down(e) {
    if (e.button !== 0 || e.target.closest("button, input, .menu, #modal")) return;
    const el = e.target.closest(".row, .card[data-tid], .card[data-pl], .qrow");
    if (!el) return;
    this.src = el;
    this.start = [e.clientX, e.clientY];
  },
  move(e) {
    if (!this.src) return;
    this.pointer = [e.clientX, e.clientY];
    if (!this.ghost) {
      if (Math.hypot(e.clientX - this.start[0], e.clientY - this.start[1]) < 6) return;
      this.begin();
    }
    this.ghost.style.left = e.clientX + 16 + "px";
    this.ghost.style.top = e.clientY + 12 + "px";
    this.setTarget(this.find(e.clientX, e.clientY), e.clientY);
  },
  up(e) {
    if (!this.ghost) { this.src = null; return; }
    const target = this.find(e.clientX, e.clientY);
    this.setTarget(target, e.clientY);
    const after = this.after, src = this.src;
    this.end();
    this.suppressClick = true;
    setTimeout(() => this.suppressClick = false, 0);
    if (target) this.drop(src, target, after);
  },
  item(el) {
    if (el.dataset.pl) return { playlist: S.plShown[el.dataset.pl] };
    const list = S.lists[el.dataset.list];
    return { track: itemTrack(el), ctx: list.ctx, list: el.dataset.list, qi: el.dataset.qi != null ? +el.dataset.qi : null };
  },
  begin() {
    const it = this.item(this.src), obj = it.playlist || it.track;
    this.ghost = document.createElement("div");
    this.ghost.id = "ghost";
    this.ghost.innerHTML = `<img src="${thumb(obj)}"><div><b>${esc(obj.title)}</b><span></span></div>`;
    document.body.appendChild(this.ghost);
    document.body.classList.add("dragging");
    $("#toast").className = "";
    this.hint(null);
    this.scrollTimer = setInterval(() => this.autoscroll(), 16);
  },
  end() {
    this.setTarget(null, 0);
    if (this.ghost) this.ghost.remove();
    this.ghost = null;
    this.src = null;
    document.body.classList.remove("dragging");
    clearInterval(this.scrollTimer);
    if (this.line) { this.line.remove(); this.line = null; }
  },
  reorderable(it, rowEl) {
    if (!it.track) return false;
    if (it.ctx.kind === "queue") return rowEl.classList.contains("qrow");
    return ["album", "favorites"].includes(it.ctx.kind) && it.ctx.reorder !== false && rowEl.dataset.list === it.list;
  },
  find(x, y) {
    const el = document.elementFromPoint(x, y);
    if (!el) return null;
    const it = this.item(this.src);
    const row = el.closest(".row, .qrow");
    if (row && row !== this.src && this.reorderable(it, row)) return { kind: "row", el: row };
    const drop = el.closest("[data-drop]");
    if (!drop) return null;
    const [kind, value] = drop.dataset.drop.split(":");
    if (kind === "favorites" && it.playlist) return null;
    return { kind, value, el: drop };
  },
  setTarget(target, y) {
    const old = this.target;
    if (old && (!target || target.el !== old.el)) old.el.classList.remove("drop-on");
    this.target = target;
    if (this.line && (!target || target.kind !== "row")) { this.line.remove(); this.line = null; }
    if (!target) { this.hint(null); return; }
    const it = this.item(this.src);
    if (target.kind === "row") {
      const r = target.el.getBoundingClientRect();
      this.after = y > r.top + r.height / 2;
      if (!this.line) { this.line = document.createElement("div"); this.line.className = "drop-line"; document.body.appendChild(this.line); }
      Object.assign(this.line.style, { left: r.left + "px", width: r.width + "px", top: (this.after ? r.bottom : r.top) - 1 + "px" });
      this.hint("Sırayı değiştir");
      return;
    }
    target.el.classList.add("drop-on");
    if (target.kind === "album") {
      const name = short(L.album(target.value).name, 24);
      this.hint(it.playlist ? `＋ Tüm şarkıları “${name}” albümüne ekle` : `＋ “${name}” albümüne ekle`);
    } else if (target.kind === "library") this.hint(it.playlist ? "＋ Kitaplığına kaydet" : "＋ Bu şarkıyla yeni albüm oluştur");
    else this.hint("♥ Favorilere ekle");
  },
  hint(text) {
    if (!this.ghost) return;
    const it = this.item(this.src);
    $("span", this.ghost).textContent = text || (it.playlist ? "Kitaplığına ya da bir albüme bırak"
      : it.ctx.kind === "queue" || (["album", "favorites"].includes(it.ctx.kind) && it.ctx.reorder !== false) ? "Sırayı değiştir ya da bir albüme bırak"
      : "Kenar çubuğundaki bir albüme ya da Favoriler'e bırak");
  },
  drop(src, target, after) {
    const it = this.item(src);
    if (it.playlist) {
      if (target.kind === "library") savePlaylist(it.playlist);
      else if (target.kind === "album") api.add_playlist_to_album(it.playlist, target.value).then(r => toast(r.error || r.message, !!r.error));
      return;
    }
    const t = it.track;
    if (target.kind === "album") addToAlbum(target.value, t);
    else if (target.kind === "library") createAlbum({ track: t });
    else if (target.kind === "favorites") { if (L.fav(t.id)) toast("Bu şarkı zaten favorilerde"); else toggleFavorite(t); }
    else if (target.kind === "row") {
      if (it.ctx.kind === "queue") P.move(it.qi, +target.el.dataset.qi, after);
      else {
        const other = itemTrack(target.el);
        if (it.ctx.kind === "album") api.reorder_album(it.ctx.album, t.id, other.id, after);
        else api.reorder_favorites(t.id, other.id, after);
      }
    }
  },
  autoscroll() {
    const [x, y] = this.pointer;
    for (const area of [$("#scroll"), $("#panelInner"), $("#libList")]) {
      const r = area.getBoundingClientRect();
      if (x < r.left || x > r.right) continue;
      if (y >= r.top && y < r.top + 50) area.scrollTop -= 12;
      else if (y > r.bottom - 50 && y <= r.bottom) area.scrollTop += 12;
    }
  },
};
document.addEventListener("pointerdown", e => D.down(e));
document.addEventListener("pointermove", e => D.move(e));
document.addEventListener("pointerup", e => D.up(e));
document.addEventListener("keydown", e => { if (e.key === "Escape" && D.ghost) D.end(); });

/* ---------- Python'dan gelen bildirimler ---------- */
function setLib(lib) {
  S.lib = lib;
  S.favSet = new Set(lib.favorites);
  const u = $("#undoBtn");
  if (u) { u.disabled = !lib.undo; u.title = lib.undo ? `Geri al: ${lib.undo} (Ctrl+Z)` : "Geri alınacak bir şey yok"; }
}
async function undo() {
  if (!S.lib.undo) { toast("Geri alınacak bir şey yok"); return; }
  const label = await api.undo();
  if (label) { toast(`Geri alındı: ${label}`); syncLib(); }
}
function libraryChanged() {
  renderSide();
  if (S.page.kind !== "search" && pageSignature() !== S.signature) renderPage(true);
  else refreshItems();
  playerChanged();
}
function downloadsChanged() {
  if (S.page.kind === "downloads" && pageSignature() !== S.signature) renderPage(true);
  refreshItems();
  renderPanelParts();
}
window.SOUND = {
  receive(event) {
    const d = event.data;
    switch (event.type) {
      case "library": setLib(d); libraryChanged(); break;
      case "downloads": S.dl = d; downloadsChanged(); break;
      case "progress":
        S.dl.progress[d.key] = d.value;
        refreshItems();
        renderPanelParts();
        $$(`.dlrow[data-key="${CSS.escape(d.key)}"]`).forEach(row => {
          const bar = $("[data-bar]", row), st = $("[data-status]", row);
          if (bar) bar.style.width = d.value * 100 + "%";
          if (st) st.textContent = dlStatus(d.key);
        });
        break;
      case "toast": toast(d.message, d.error); break;
      case "app_update": showAppUpdate(d); break;
      case "import": importProgress(d); break;

      case "home": S.home = d; if (S.page.kind === "home") renderPage(true); break;
      case "age": openAccount(`“${short(d.title, 50)}” için YouTube yaş doğrulaması istiyor.`, () => api.retry_download(d.key)); break;
      case "command":
        ({ toggle: () => P.toggle(), play: () => !P.isPlaying() && P.toggle(), pause: () => P.isPlaying() && P.toggle(),
           next: () => P.next(), previous: () => P.previous(), shuffle: () => P.toggleShuffle(), repeat: () => P.cycleRepeat() })[d]?.();
        break;
    }
  },
};

/* ---------- oturum: kaldığın yerden devam ---------- */
let lastSession = "";
function sessionState() {
  return {
    current: P.current, position: Math.round(P.position() * 10) / 10, queue: P.queue.slice(0, 300),
    order: P.order.filter(i => i < 300), pos: P.pos, source: P.source, shuffle: P.shuffle, repeat: P.repeat,
    panel: S.panelOpen, panel_mode: S.panelMode,
  };
}
setInterval(() => {
  if (!api) return;
  const state = sessionState(), sig = JSON.stringify(state);
  if (sig !== lastSession) { lastSession = sig; api.save_session(state); }
}, 4000);
function restoreSession(s) {
  P.shuffle = !!s.shuffle;
  P.repeat = ["off", "all", "one"].includes(s.repeat) ? s.repeat : "off";
  S.panelMode = s.panel_mode === "video" ? "video" : "cover";
  const queue = s.queue || [], order = (s.order || []).filter(i => i >= 0 && i < queue.length), pos = s.pos ?? -1;
  if (s.current && queue.length && order.length && pos >= 0 && pos < order.length) {
    Object.assign(P, { queue, order, pos, source: s.source || null });
    P.current = queue[order[pos]];
  } else if (s.current) Object.assign(P, { queue: [s.current], order: [0], pos: 0, current: s.current });
  if (P.current) P.resumeAt = [P.current.id, +s.position || 0];
  if (s.panel) togglePanel(true);
}

/* ---------- klavye ve üst çubuk ---------- */
document.addEventListener("keydown", e => {
  const typing = e.target.closest?.("input, textarea");
  if (e.ctrlKey && e.key.toLowerCase() === "f") { e.preventDefault(); ACT.focusSearch(); return; }
  if (typing || $("#modal")) return;
  if (e.code === "Space") { e.preventDefault(); P.toggle(); }
  else if (e.ctrlKey && e.key === "ArrowRight") P.next();
  else if (e.ctrlKey && e.key === "ArrowLeft") P.previous();
  else if (e.ctrlKey && e.key.toLowerCase() === "z") { e.preventDefault(); undo(); }
  else if (e.altKey && e.key === "ArrowLeft") goBack();
  else if (e.altKey && e.key === "ArrowRight") goForward();
  else if (e.key === "Escape") closeMenus();
});
document.addEventListener("mouseup", e => { if (e.button === 3) goBack(); if (e.button === 4) goForward(); });
const searchInput = $("#searchInput");
searchInput.addEventListener("keydown", e => { if (e.key === "Enter") { doSearch(searchInput.value); searchInput.blur(); } if (e.key === "Escape") searchInput.blur(); });
searchInput.addEventListener("input", () => { $("#searchClear").classList.toggle("hidden", !searchInput.value); renderSearchDrop(); });
searchInput.addEventListener("focus", () => { if (S.page.kind !== "search") openPage("search"); renderSearchDrop(); });
searchInput.addEventListener("blur", () => setTimeout(renderSearchDrop, 150));
$("#searchDrop").addEventListener("mousedown", e => e.preventDefault());  // tıklarken arama kutusu odağı kaybetmesin
$("#searchClear").onclick = e => {
  e.preventDefault();
  searchInput.value = "";
  $("#searchClear").classList.add("hidden");
  S.search = { query: "", loading: false, tracks: [], videos: [], albums: [], artists: [], error: null, token: S.search.token + 1 };
  if (S.page.kind === "search") renderPage();
  searchInput.focus();
};
$("#backBtn").onclick = goBack;
$("#fwdBtn").onclick = goForward;
const statTip = document.createElement("div");
statTip.id = "statTip";
statTip.className = "hidden";
document.body.appendChild(statTip);
document.addEventListener("pointermove", e => {
  const col = e.target.closest && e.target.closest("[data-tip]");
  statTip.classList.toggle("hidden", !col);
  if (!col) return;
  statTip.textContent = col.dataset.tip;
  const r = col.getBoundingClientRect(), w = statTip.offsetWidth;
  statTip.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + "px";
  statTip.style.top = Math.max(8, e.clientY - 40) + "px";
});
$$("#nav a").forEach(a => a.onclick = () => a.dataset.page === "search" ? ACT.focusSearch() : openPage(a.dataset.page));
$("#newBtn").onclick = e => { e.stopPropagation(); menuAt([{ label: "Yeni albüm", act: () => createAlbum() }, { label: "Yeni klasör", act: () => createFolder() }], $("#newBtn")); };
$("#accountBtn").onclick = () => openSettings();
$("#shuffleBtn").innerHTML = I.shuffle; $("#shuffleBtn").onclick = () => P.toggleShuffle();
$("#prevBtn").innerHTML = I.prev; $("#prevBtn").onclick = () => P.previous();
$("#nextBtn").innerHTML = I.next; $("#nextBtn").onclick = () => P.next();
$("#ppBtn").onclick = () => P.toggle();
$("#repeatBtn").onclick = () => P.cycleRepeat();
$("#panelBtn").innerHTML = I.queue; $("#panelBtn").onclick = () => togglePanel();
function onScroll() { $("#topbar").classList.toggle("solid", $("#scroll").scrollTop > 40); }
$("#scroll").addEventListener("scroll", onScroll, { passive: true });

/* ---------- açılış ---------- */
async function start() {
  api = window.pywebview.api;
  const init = await api.init();
  setLib(init.lib);
  S.dl = init.downloads;
  S.home = init.home;
  S.browsers = init.browsers;
  S.settings = init.settings;
  applyUI(S.settings.ui);
  setVolume(init.volume, false);
  restoreSession(init.session || {});
  openPage("home", null, { push: false });
  playerChanged(true);
  if (P.current) api.prefetch([P.current, ...P.upcoming(1).map(([, t]) => t)].filter(t => !L.dl(t.id)), S.panelOpen && S.panelMode === "video");
  requestAnimationFrame(frame);
}
try { applyUI(JSON.parse(localStorage.getItem("sound.ui") || "null")); } catch { }  // kayıtlı görünüm: ilk karede
if (window.pywebview && window.pywebview.api && window.pywebview.api.init) start();
else window.addEventListener("pywebviewready", start, { once: true });
