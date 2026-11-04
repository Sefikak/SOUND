/* Telefon uyarlaması: aynı arayüz, alt sekmeler, küçük çalar ve tam ekran çalar. Masaüstü kodu değişmez. */
(() => {
  const root = document.documentElement;
  root.classList.add("mobile");

  /* alt sekmeler */
  const icon = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
  const TABS = [
    ["settings", "Ayarlar", icon('<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>')],
    ["home", "Ana sayfa", icon('<path d="M4 11 12 4l8 7v9h-5v-6H9v6H4z"/>')],
    ["search", "Ara", icon('<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>')],
    ["library", "Kitaplık", icon('<path d="M4 4v16M9 4v16M14 4l6 16"/>')],
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
    const active = lib ? "library" : kind === "stats" ? "settings" : kind;  // istatistikler ayarların içinden açılır
    $$("#mTabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === active));
  }
  tabs.addEventListener("click", e => {
    const t = e.target.closest("[data-tab]");
    if (!t) return;
    const k = t.dataset.tab;
    if (k === "settings") { $("#searchInput").blur(); libOpen(false); return openSettings(); }
    if (k === "library") return libOpen(!document.body.classList.contains("m-lib"));
    libOpen(false);
    if (k === "search") { openPage("search"); $("#searchInput").focus(); return; }
    $("#searchInput").blur();
    openPage(k);
  });
  // kitaplıkta bir şey seçilince sayfası görünsün
  $("#side").addEventListener("click", e => {
    if (e.target.closest("#nav a, .li[data-page], .account")) setTimeout(() => libOpen(false));
  });
  const original = renderPage;
  window.renderPage = keep => { original(keep); syncTabs(); };

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

  /* küçük çaların üstünde ince ilerleme çizgisi */
  const line = document.createElement("i");
  line.id = "mProg";
  $("#bar").appendChild(line);
  setInterval(() => {
    const d = P.duration();
    line.style.width = d ? Math.min(100, P.position() / d * 100) + "%" : "0";
  }, 500);

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
  syncTabs();
})();
