/* Telefon uyarlaması: aynı arayüz, alt sekmeler, küçük çalar ve tam ekran çalar. Masaüstü kodu değişmez. */
(() => {
  const root = document.documentElement;
  root.classList.add("mobile");

  /* varsayılan koyu tema telefonda bir ton açık ve vurgu renginden hafifçe renkli; Siyah, Gri ve Renkli seçenekleri değişmez */
  const realApplyUI = applyUI;
  applyUI = ui => {
    realApplyUI(ui);
    const u = uiOpts(ui);
    if (u.bg !== "dark") return;
    const accent = hexRgb(u.accent), tone = (base, f) => rgbHex(mixRgb(hexRgb(base), accent, f));
    const style = root.style;
    style.setProperty("--bg", tone("#1a1a1a", .07));
    style.setProperty("--black", tone("#101010", .05));
    style.setProperty("--card", tone("#262626", .09));
    style.setProperty("--raise", tone("#2b2b2b", .09));
    style.setProperty("--raise2", tone("#303030", .09));
    style.setProperty("--card-hover", tone("#323232", .1));
  };
  try { applyUI((S.settings && S.settings.ui) || JSON.parse(localStorage.getItem("sound.ui") || "null")); } catch { }

  /* alt sekmeler */
  const icon = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
  const TABS = [
    ["home", "Ana sayfa", icon('<path d="M4 11 12 4l8 7v9h-5v-6H9v6H4z"/>')],
    ["library", "Kitaplık", icon('<path d="M4 4v16M9 4v16M14 4l6 16"/>')],
    ["social", "Profil", icon('<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4.5 4-7 8-7s7 2.5 8 7"/>')],
  ];
  const tabs = document.createElement("nav");
  tabs.id = "mTabs";
  tabs.innerHTML = TABS.map(([k, n, i]) => `<button data-tab="${k}">${i}<span>${n}</span></button>`).join("");
  $("#app").appendChild(tabs);

  /* YouTube hesabı: telefonda tarayıcı çerezi ya da cookies.txt yok, tek yol uygulama içi Google girişi */
  openAccount = async (reason = null, onConnected = null) => {
    const status = await api.auth_status();
    const connected = !status.includes("bağlı değil");
    await modal(`<h3>YouTube hesabı</h3>${reason ? `<p class="reason">${esc(reason)}</p>` : ""}
      <p>Hesap asıl olarak beğenilen şarkıları ve albümleri aktarmak içindir. Yaş sınırını telefonda genelde kaldırmaz; SOUND bunun yerine aynı şarkının kısıtsız bir yüklemesini arar.</p>
      <div class="status">${esc(connected ? "Google hesabına giriş yapıldı." : "Giriş yapılmadı.")}</div>
      <div class="row-btns">${connected ? `<button class="textbtn" data-x="out">Hesaptan çık</button>` : `<button class="pill fill" data-x="in">Google hesabınla giriş yap</button>`}<button class="pill" data-x="close">Kapat</button></div>`,
      (box, done) => {
        const on = (x, fn) => { const b = $(`[data-x="${x}"]`, box); if (b) b.onclick = fn; };
        on("close", () => done(null));
        on("out", async () => { await api.auth_clear(); toast("Hesaptan çıkıldı"); done(null); });
        on("in", async () => {
          const res = await api.login_import("ytmusic", null, false);
          if (res.error) return toast(res.error, true);
          accountDone = onConnected;
          done(null);
        });
      });
  };

  const libOpen = on => { document.body.classList.toggle("m-lib", on); syncTabs(); };
  function syncTabs() {
    const lib = document.body.classList.contains("m-lib"), kind = S.page && S.page.kind;
    const active = lib ? "library" : ["social", "person", "chat", "stats"].includes(kind) ? "social" : kind;  // ayarlar ve istatistikler profilin içinden açılır
    $$("#mTabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === active));
    document.body.classList.toggle("m-home", kind === "home");
    const box = $("#searchInput");
    if (kind === "home" && box.value && document.activeElement !== box) { box.value = ""; $("#searchClear").classList.add("hidden"); }  // ana sayfaya dönünce arama çubuğu boşalır
  }
  tabs.addEventListener("click", e => {
    const t = e.target.closest("[data-tab]");
    if (!t) return;
    const k = t.dataset.tab;
    if (k === "library") return libOpen(!document.body.classList.contains("m-lib"));
    libOpen(false);
    $("#searchInput").blur();
    openPage(k);
  });
  // kitaplıkta bir şey seçilince sayfası görünsün
  $("#side").addEventListener("click", e => {
    if (e.target.closest("#nav a, .li[data-page], .account")) setTimeout(() => libOpen(false));
  });
  const original = renderPage;
  ACT.openSettings = () => { $("#searchInput").blur(); openSettings(); };
  window.renderPage = keep => {
    original(keep);
    syncTabs();
    if (S.page.kind === "social") $("#scRoot").insertAdjacentHTML("beforebegin", `<div class="m-settings"><button class="pill" data-act="openSettings">${icon('<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>')}Ayarlar</button></div>`);
  };
  // koddan açılan sayfa (Sanatçı Mix sonrası albüm, bildirimden açılan sayfa...) kitaplık ekranının arkasında kalmasın
  const originalOpen = openPage;
  window.openPage = (...args) => { libOpen(false); return originalOpen(...args); };

  /* dokunma: masaüstünde çift tıklanan satır burada tek dokunuşla çalar; sürükle-bırak kapalı (kaydırmayla çakışır) */
  document.addEventListener("click", e => {
    const row = e.target.closest(".row");
    if (!row || e.target.closest("button, [data-act]")) return;
    const list = S.lists[row.dataset.list];
    if (list) P.playList(list.tracks, +row.dataset.i, list.ctx.key);
  });
  D.down = () => {};
  // Ara'ya basınca klavye kapansın, öneriler sonuçların üstünde kalmasın
  $("#searchInput").addEventListener("keydown", e => { if (e.key === "Enter") setTimeout(() => e.target.blur()); });
  $("#scroll").addEventListener("touchstart", () => { if (document.activeElement === $("#searchInput")) $("#searchInput").blur(); }, { passive: true });

  /* alev: parmakla sürükleme kaydırma sanılıp iptal edilirse sarma yarıda takılmasın; telefonda bulanıklık efekti yok
     (işlemciyi en çok yoran kısım), kare hızı yarıda, görünmezken neredeyse hiç çizilmez */
  flame.addEventListener("pointercancel", () => { seeking = null; });
  Object.defineProperty(fctx, "filter", { get: () => "none", set() {} });
  const raf = window.requestAnimationFrame.bind(window);
  let skip = false;
  window.requestAnimationFrame = cb => {
    if (cb !== frame) return raf(cb);
    if (!flame.clientWidth) return setTimeout(() => raf(cb), 500);
    skip = !skip;
    return raf(skip ? () => raf(cb) : cb);
  };

  /* ana sayfa: üstte küçük kısayollar, son dinlenenler liste halinde, öneriler yana kayan küçük kartlar */
  const radioHTML = (key, i, t) => `<div class="card m-radio" data-list="${key}" data-i="${i}">
    <div class="cover"><img loading="lazy" src="${thumb(t)}"><span>RADYO</span></div><div class="ct">${esc(t.title)} Radyosu</div>
    <div class="cfoot"><span>${esc(t.artist)}</span><div class="acts"><button class="pbtn">${I.play}</button></div></div></div>`;
  pageHome = () => {
    afterRender = () => {
      const cur = P.current;
      glowFrom(cur ? thumb(cur) : null, "#3b2470");
      api.home().then(h => { S.home = h; });
      api.mixes().then(m => { const had = JSON.stringify(S.mixes); S.mixes = m; if (JSON.stringify(m) !== had && S.page.kind === "home") renderPage(true); });
    };
    const quick = [
      { title: "Favoriler", art: tile("fav", 56, I.heart, "#6d4ae0", 0), page: "favorites", src: "favorites" },
      { title: "İndirilenler", art: tile("dl", 56, stroke('<path d="M12 4v11m-5-5 5 5 5-5M5 20h14"/>', 2.4), "#0f766e", 0), page: "downloads", src: "downloads" },
      ...Object.entries(S.lib.albums).sort((a, b) => b[1].created - a[1].created).slice(0, 6).map(([id, a]) => {
        const cover = albumCover(id);
        return { title: a.name, art: cover ? `<img src="${cover}">` : tile(id, 56, I.note, null, 0), page: "album", ref: id, src: `album:${id}` };
      }),
    ];
    let html = `<div class="pad home-page"><div class="m-head"><h1>${greeting()}</h1>
      <div class="m-head-btns"><button class="round-btn ${dvRemote() ? "on" : ""}" data-act="openDevices" title="Çalınacak cihaz">${I.devices}</button><button class="round-btn ${LT.room ? "on" : ""}" data-act="openListen" title="Ortak dinleme">${I.listen}</button>
      <button class="round-btn" data-act="homeRefresh" title="Önerileri yenile">${I.refresh}</button></div></div>
      <div class="quick">${quick.map(q => `<div class="q" data-act="open" data-page="${q.page}" data-ref="${esc(q.ref || "")}" data-src="${esc(q.src)}">${q.art}<b>${esc(q.title)}</b></div>`).join("")}</div>`;

    const recent = L.recent();
    if (recent.length) {
      const key = registerList("home:recent:r", recent.slice(0, 10), { kind: "home", key: "home:recent" });
      html += section("Son dinlediklerin", null, `<div class="list">${recent.slice(0, 4).map((t, i) => rowHTML(key, i, t)).join("")}</div>`);
      registerList("home:radio", recent.slice(0, 8), { kind: "home", key: "home:radio" });
      html += section("Senin için radyolar", null, `<div class="cards">${recent.slice(0, 8).map((t, i) => radioHTML("home:radio", i, t)).join("")}</div>`);
    }
    html += mixesSection();
    const sections = S.home.sections || [];
    if (sections.length) {
      for (const s of sections) {
        html += s.type === "albums" ? section(s.title, null, `<div class="cards">${s.albums.slice(0, 10).map(albumCardHTML).join("")}</div>`)
          : section(s.title, null, cards(`home:${s.key}`, s.tracks));
      }
    } else if (S.home.loading) html += section("Senin için hazırlanıyor…", null, skeletonCards());
    else if (S.home.error) html += `<div class="sec"><div><h2>Öneriler yüklenemedi</h2><p>${esc(S.home.error)} İndirdiğin şarkılar çevrimdışı da çalışır.</p></div></div>`;
    const artists = (S.lib.top_artists || []).slice(0, 10).filter(([, id]) => L.t(id));
    if (artists.length) html += section("En çok dinlediğin sanatçılar", null, `<div class="cards">${artists.map(([name, id]) =>
      `<div class="card circle" data-act="artist" data-artist="${esc(name)}"><div class="cover"><img loading="lazy" src="${thumb(L.t(id))}"></div><div class="ct">${esc(name)}</div></div>`).join("")}</div>`);
    const favs = L.favTracks().slice(0, 10);
    if (favs.length) html += section("Favorilerinden", null, cards("favorites", favs), `<span class="link" data-act="open" data-page="favorites">Tümü</span>`);
    const dls = L.dlTracks().slice(0, 10);
    if (dls.length) html += section("Çevrimdışı hazır", null, cards("downloads", dls), `<span class="link" data-act="open" data-page="downloads">Tümü</span>`);
    return html + "</div>";
  };
  /* radyo kartı: şarkıdan başlar, benzerleriyle sürer */
  $("#page").addEventListener("click", async e => {
    const card = e.target.closest(".m-radio");
    if (!card) return;
    const t = S.lists[card.dataset.list].tracks[+card.dataset.i];
    toast("Radyo hazırlanıyor…");
    const more = await api.radio(plain(t));
    P.playList([t, ...(more || []).filter(x => x.id !== t.id).slice(0, 30)], 0, `radio:${t.id}`);
  });

  /* küçük çaların altında ince ilerleme çizgisi; renk kapaktan gelir; şarkı yokken çalar gizlenir */
  const line = document.createElement("i");
  line.id = "mProg";
  $("#bar").appendChild(line);
  /* ortak dinleme: odadayken küçük çaların üstünde kod ve kişi sayısı, dokununca oda açılır */
  ACT.openListen = () => openListen();
  ACT.mQueue = () => { const q = $("#pQueue"), inner = $("#panelInner"); if (q && inner) inner.scrollTo({ top: q.offsetTop - 12, behavior: "smooth" }); };
  const listenChip = document.createElement("button");
  listenChip.id = "mListen";
  listenChip.onclick = e => { e.stopPropagation(); openListen(); };
  $("#bar").appendChild(listenChip);
  const drawListenChip = () => {
    listenChip.classList.toggle("show", !!LT.room && !S.panelOpen);
    if (LT.room) listenChip.innerHTML = `${I.listen}${esc(LT.room)} · ${LT.members.length}`;
    $$('[data-act="openListen"]').forEach(b => b.classList.toggle("on", !!LT.room));
  };
  document.addEventListener("listenchange", drawListenChip);
  /* okunmamış mesaj ve arkadaşlık isteği: alt çubuktaki Profil sekmesinde sayı */
  const drawSocial = () => {
    const count = (SC.data?.incoming?.length || 0) + (SC.data?.friends || []).reduce((n, f) => n + f.unread, 0), tab = $('#mTabs [data-tab="social"]');
    $(".sc-badge", tab)?.remove();
    if (count) tab.insertAdjacentHTML("beforeend", `<i class="sc-badge">${count > 99 ? "99+" : count}</i>`);
  };
  document.addEventListener("socialbadge", drawSocial);
  let tintFor = null;
  /* tam ekran arka planı: kapak 12x12'ye küçültülüp büyütülür; yumuşak renk geçişi verir, bulanıklık efekti gibi işlemci yemez */
  const meshFrom = url => {
    const img = new Image();
    img.onload = () => {
      try {
        const c = document.createElement("canvas");
        c.width = c.height = 12;
        c.getContext("2d").drawImage(img, 0, 0, 12, 12);
        root.style.setProperty("--m-art", `url(${c.toDataURL("image/png")})`);
      } catch { }
    };
    img.src = url;
  };
  /* kitaplıktaki Favoriler ve İndirilenler kartlarında şarkı sayısı */
  const navCount = {};
  [...$('#nav a[data-page="downloads"]').childNodes].find(n => n.nodeType === 3).textContent = "İndirilenler";  // bilgisayarda Kütüphane
  for (const page of ["favorites", "downloads"]) {
    const small = document.createElement("small");
    small.className = "m-n";
    $(`#nav a[data-page="${page}"]`).appendChild(small);
    navCount[page] = small;
  }
  setInterval(() => {
    const d = P.duration(), t = P.current;
    if (S.lib) {
      navCount.favorites.textContent = `${L.favTracks().length} şarkı`;
      navCount.downloads.textContent = `${L.dlTracks().length} şarkı`;
    }
    line.style.width = d ? Math.min(100, P.position() / d * 100) + "%" : "0";
    root.classList.toggle("m-idle", !t);
    drawListenChip();
    if (t && t.id !== tintFor) {
      tintFor = t.id;
      coverColor(thumb(t)).then(c => { if (c && tintFor === t.id) root.style.setProperty("--m-tint", c); });
      meshFrom(thumb(t));
    }
  }, 500);

  /* parmak hareketleri: küçük çalar yana = şarkı değiştir, yukarı = tam ekran; tam ekran aşağı = küçült */
  const bar = $("#bar"), panel = $("#panel"), np = $("#np");
  const THRESHOLD = 64, CLOSE_AT = 110;
  const moveFull = y => { const v = y ? `translateY(${y}px)` : ""; panel.style.transform = v; bar.style.transform = v; };
  const previousSong = () => { if (P.pos > 0) A.currentTime = 0; P.previous(); };  // şarkı başa sarılmasın, gerçekten öncekine geçsin

  const realToggle = togglePanel;
  let closing = false;
  togglePanel = (open = !S.panelOpen) => {
    if (open || !S.panelOpen) { closing = false; moveFull(0); return realToggle(open); }
    if (closing) return;
    closing = true;  // alta kayarak kapansın, sonra gerçekten kapat
    panel.classList.add("m-anim"); bar.classList.add("m-anim");
    moveFull(window.innerHeight);
    setTimeout(() => {
      panel.classList.remove("m-anim"); bar.classList.remove("m-anim");
      realToggle(false);
      centerHome();
      moveFull(0);
      closing = false;
    }, 210);
  };
  /* indirme: yazısız tek ikon, kalbin yanında. Kapak kipinde ses, video kipinde video indirir */
  const VIDEO_DL = stroke('<rect x="2" y="5" width="15" height="14" rx="3"/><path d="m17 10 5-3v10l-5-3"/><path d="M9.5 8.5v6.2m-2.6-2.6 2.6 2.6 2.6-2.6"/>', 1.9);
  const realParts = renderPanelParts;
  renderPanelParts = () => {
    realParts();
    const t = P.current, row = $("#pTitle .p-title");
    if (!t || !row) return;
    const kind = S.panelMode === "video" ? "video" : "audio", [state, icon] = dlIcon(t.id, kind);
    const button = document.createElement("button");
    button.className = `rb m-dl ${state}`;
    button.dataset.act = "panelDl";
    button.dataset.kind = kind;
    button.title = `${kind === "video" ? "Video" : "Ses"} ${state === "done" ? "indirildi" : state === "busy" ? "indiriliyor, iptal için dokun" : "indir"}`;
    button.innerHTML = kind === "video" && state !== "busy" ? VIDEO_DL : icon;
    row.insertBefore(button, $(".heart", row));
  };

  /* Alev ve düğmeler tam ekranda sayfanın içine taşınır: ilk ekran çaların kendisi, sözler ve bilgiler kaydırınca altta.
     Her yeniden çizimden önce çubuğa geri alınır, yoksa panelin içeriğiyle birlikte silinirdi. */
  const center = $("#bar .center");
  const centerHome = () => { if (center.parentElement !== bar) bar.insertBefore(center, $("#bar .right")); };
  const realRender = renderPanel;
  renderPanel = () => {
    centerHome();
    realRender();
    const inner = $("#panelInner"), media = $("#pMedia");
    if (!media) return;
    $('[data-act="closePanel"]', inner).innerHTML = stroke('<path d="m6 9 6 6 6-6"/>', 2.4);
    const now = document.createElement("div");
    now.id = "mNow";
    inner.insertBefore(now, inner.firstChild);
    now.append($(".p-head", inner), media, $("#pTitle"), center);
    // tam ekran çaların üstünde: çalınacak cihaz, ortak dinleme, sıradakiler (aşağıdaki listeye kaydırır)
    const btns = document.createElement("div");
    btns.className = "m-pbtns";
    btns.innerHTML = `<button data-act="openDevices" class="${dvRemote() ? "on" : ""}" title="Çalınacak cihaz">${I.devices}</button>
      <button data-act="openListen" class="${LT.room ? "on" : ""}" title="Ortak dinleme">${I.listen}</button>
      <button data-act="sleep" class="sleep-btn" title="Uyku zamanlayıcısı">${I.moon}</button>
      <button data-act="mQueue" title="Sıradakiler">${I.queue}</button>`;
    sleepDraw();
    $(".p-head", now).appendChild(btns);
    // denetimlerin altında: ses hangi cihazdan çıkıyor (Galaxy Buds2 gibi); app.js dvDraw doldurur
    const out = document.createElement("button");
    out.id = "mOut";
    out.dataset.act = "openDevices";
    now.appendChild(out);
    dvDraw();
  };

  let touch = null;
  const begin = e => {
    if (e.touches.length !== 1 || e.target.closest("#flame, input")) { touch = null; return; }
    const inner = $("#panelInner");
    touch = { x: e.touches[0].clientX, y: e.touches[0].clientY, mode: null, full: S.panelOpen, atTop: !inner || inner.scrollTop <= 0,
      cover: S.panelOpen ? e.target.closest("#pMedia") : null };
  };
  const move = e => {
    if (!touch) return;
    const dx = e.touches[0].clientX - touch.x, dy = e.touches[0].clientY - touch.y;
    if (!touch.mode) {
      if (Math.abs(dx) < 10 && Math.abs(dy) < 10) return;
      const sideways = Math.abs(dx) > Math.abs(dy);
      if (touch.full) touch.mode = sideways && touch.cover && P.current ? "cover" : !sideways && dy > 0 && touch.atTop ? "close" : "none";
      else touch.mode = sideways && P.current ? "swipe" : !sideways && dy < 0 && P.current ? "open" : "none";
    }
    if (touch.mode === "none") return;
    e.preventDefault();
    if (touch.mode === "close") moveFull(Math.max(0, dy));
    else if (touch.mode === "swipe") { np.style.transform = `translateX(${dx}px)`; np.style.opacity = Math.max(.35, 1 - Math.abs(dx) / 260); }
    else if (touch.mode === "cover") { touch.cover.style.transform = `translateX(${dx}px)`; touch.cover.style.opacity = Math.max(.35, 1 - Math.abs(dx) / 320); }
    touch.dx = dx; touch.dy = dy;
  };
  const end = () => {
    if (!touch) return;
    const { mode, dx = 0, dy = 0, cover } = touch;
    touch = null;
    if (mode && mode !== "none") suppressClick = true;
    setTimeout(() => { suppressClick = false; }, 350);
    if (mode === "close") {
      if (dy > CLOSE_AT) return togglePanel(false);
      panel.classList.add("m-anim"); bar.classList.add("m-anim");
      moveFull(0);
      setTimeout(() => { panel.classList.remove("m-anim"); bar.classList.remove("m-anim"); }, 210);
    } else if (mode === "open") {
      if (dy < -40) togglePanel(true);
    } else if (mode === "cover") {
      cover.classList.add("m-anim");
      cover.style.transform = ""; cover.style.opacity = "";
      setTimeout(() => cover.classList.remove("m-anim"), 210);
      // kapak sayfa gibi çevrilir: sola itince sonraki, sağa çekince önceki şarkı
      if (dx < -THRESHOLD) P.next();
      else if (dx > THRESHOLD) previousSong();
    } else if (mode === "swipe") {
      np.classList.add("m-anim");
      np.style.transform = ""; np.style.opacity = "";
      setTimeout(() => np.classList.remove("m-anim"), 210);
      if (dx > THRESHOLD) P.next();
      else if (dx < -THRESHOLD) previousSong();
    }
  };
  let suppressClick = false;
  // küçük çalarda düğmeler dışında her yer tam ekranı açar (sanatçı satırı ve boşluklar dahil)
  bar.addEventListener("click", e => { if (!S.panelOpen && P.current && !e.target.closest("button")) togglePanel(true); });
  document.addEventListener("click", e => { if (suppressClick) { e.stopPropagation(); e.preventDefault(); } }, true);
  for (const el of [bar, panel]) {
    el.addEventListener("touchstart", begin, { passive: true });
    el.addEventListener("touchmove", move, { passive: false });
    el.addEventListener("touchend", end);
    el.addEventListener("touchcancel", () => {
      if (touch && touch.cover) { touch.cover.style.transform = ""; touch.cover.style.opacity = ""; }
      touch = null; moveFull(0); np.style.transform = ""; np.style.opacity = "";
    });
  }

  /* şarkı satırını sağa kaydırınca kuyruğa eklenir (Spotify gibi): satır kayarken arkasında vurgu rengi açılır */
  const QUEUE_AT = 90;
  let rowTouch = null;
  const scroller = $("#scroll");
  scroller.addEventListener("touchstart", e => {
    const row = e.touches.length === 1 && e.target.closest(".row[data-list]");
    rowTouch = row ? { row, x: e.touches[0].clientX, y: e.touches[0].clientY, mode: null, dx: 0 } : null;
  }, { passive: true });
  scroller.addEventListener("touchmove", e => {
    if (!rowTouch) return;
    const dx = e.touches[0].clientX - rowTouch.x, dy = e.touches[0].clientY - rowTouch.y;
    if (!rowTouch.mode) {
      if (Math.abs(dx) < 10 && Math.abs(dy) < 10) return;
      rowTouch.mode = dx > 0 && Math.abs(dx) > Math.abs(dy) * 1.4 ? "queue" : "none";
    }
    if (rowTouch.mode !== "queue") return;
    e.preventDefault();
    const shift = Math.max(0, Math.min(dx, 140)), r = rowTouch.row;
    rowTouch.dx = dx;
    r.style.transition = "none";
    r.style.transform = `translateX(${shift}px)`;
    r.style.boxShadow = `-${shift}px 0 0 0 ${dx > QUEUE_AT ? "var(--accent)" : "#ffffff26"}`;
  }, { passive: false });
  const rowEnd = () => {
    if (!rowTouch) return;
    const { row, mode, dx } = rowTouch;
    rowTouch = null;
    if (mode !== "queue") return;
    suppressClick = true;
    setTimeout(() => { suppressClick = false; }, 350);
    row.style.transition = "transform .18s ease-out, box-shadow .18s ease-out";
    row.style.transform = ""; row.style.boxShadow = "";
    setTimeout(() => { row.style.transition = ""; }, 200);
    const t = dx > QUEUE_AT && itemTrack(row);
    if (t) { P.enqueue(t); navigator.vibrate?.(20); }
  };
  scroller.addEventListener("touchend", rowEnd);
  scroller.addEventListener("touchcancel", rowEnd);

  /* ses telefonun kendi tuşlarıyla ayarlanır: uygulama içi kaydırıcı tam açık kalır */
  const setVol = setVolume;
  window.setVolume = () => setVol(1, false);
  setVol(1, false);

  /* uygulama hep ana ekranla açılsın: masaüstünde panel açık kaldıysa geri açılır, burada tüm ekranı kaplardı */
  const restore = restoreSession;
  window.restoreSession = s => restore({ ...s, panel: false });

  /* güncelleme kutusu: masaüstünde "yeniden başlat" uygulamayı kapatır; burada sistemin yükleme ekranı açılır, kullanıcı
     vazgeçerse uygulama olduğu gibi sürer, yine Ayarlar'dan yükleyebilir */
  window.showAppUpdate = d => {
    $("#updateBox")?.remove();
    const el = document.createElement("div");
    el.id = "updateBox";
    el.innerHTML = `<b>SOUND ${esc(d.to)} hazır</b>
      <p>Yükleye basınca Android onay ister. Kitaplığın silinmez.</p>
      ${d.notes?.length ? `<ul>${d.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
      <div class="row-btns"><button class="textbtn" data-x="later">Sonra</button><button class="pill accent" data-x="restart">Yükle</button></div>`;
    document.body.appendChild(el);
    $('[data-x="later"]', el).onclick = () => el.remove();
    $('[data-x="restart"]', el).onclick = () => { el.remove(); api.restart_app(); };
  };

  /* geri tuşu: açık olan en üstteki şeyi kapatır, yoksa bir önceki sayfaya gider. false: uygulama arka plana alınır */
  window.soundBack = () => {
    const modalBox = $("#modal");
    if (modalBox) { modalBox.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true })); return true; }
    if (openMenus.length) { closeMenus(); return true; }
    if (S.panelOpen) { togglePanel(false); return true; }
    if (document.body.classList.contains("m-lib")) { libOpen(false); return true; }
    if (S.back.length) { $("#backBtn").click(); return true; }
    if (S.page.kind !== "home") { openPage("home"); return true; }
    return false;
  };
  window.soundSave = () => { if (api) api.save_session(sessionState()); };
  /* arayüz süreci ölüp yeniden açıldı: oturum geri yüklenince şarkı kaldığı yerden sürer (MainActivity.resumePlayback) */
  window.soundResume = () => {
    if (!P.current) return false;
    if (!P.isPlaying()) P.toggle();
    return true;
  };
  syncTabs();
})();
