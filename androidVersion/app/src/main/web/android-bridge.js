/* Masaüstünde pywebview'in sağladığı window.pywebview.api burada SoundNative üzerinden kurulur. app.js'e dokunulmaz. */
(() => {
  const pending = new Map();
  let seq = 0;
  window.__soundDone = (id, res) => {
    const p = pending.get(id);
    if (!p) return;
    pending.delete(id);
    if ("error" in res) { console.error("api", p.method, res.error); p.reject(new Error(res.error)); }
    else p.resolve(res.ok === undefined ? null : res.ok);
  };
  const api = new Proxy({}, {
    get(_, method) {
      if (typeof method !== "string" || method === "then") return undefined;
      return (...args) => new Promise((resolve, reject) => {
        const id = ++seq;
        pending.set(id, { resolve, reject, method });
        SoundNative.call(id, method, JSON.stringify(args));
      });
    },
  });
  window.pywebview = { api };

  /* Müzik için büyük ses tamponu: varsayılan düşük gecikme, zayıf telefonda çıtırtı yapabiliyor ve pil harcıyor */
  const Ctx = window.AudioContext;
  window.AudioContext = class extends Ctx { constructor(o) { super({ latencyHint: "playback", ...o }); } };

  /* Alev perdesi telefonda hafif çizilsin: ekran çözünürlüğünde değil, en fazla 1,5 katta (kullanan tek yer o) */
  const realDpr = window.devicePixelRatio;
  Object.defineProperty(window, "devicePixelRatio", { get: () => Math.min(realDpr, 1.5) });
})();
