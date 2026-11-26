"""Windows ses karıştırıcısında SOUND'un adı ve simgesi.

Ses WebView2'nin kendi alt sürecinden (msedgewebview2.exe) çıkıyor; Windows bu yüzden karıştırıcıda "Microsoft Edge WebView2"
yazıyor. Bu modül, bizim süreç ağacımıza ait ses oturumlarını bulur ve adını "SOUND", simgesini uygulama simgesi yapar
(IAudioSessionControl::SetDisplayName / SetIconPath). comtypes gerekmesin diye COM çağrıları ctypes ile yapılır.
Ses oturumu şarkı başlayınca ya da çıkış cihazı değişince yeniden oluşabildiği için arada bir yeniden denetlenir.
"""
import ctypes
import os
import threading
from ctypes import wintypes

ole32 = ctypes.WinDLL("ole32")
kernel32 = ctypes.WinDLL("kernel32")

CLSCTX_ALL = 0x17
COINIT_MULTITHREADED = 0
E_RENDER = 0
DEVICE_STATE_ACTIVE = 1
TH32CS_SNAPPROCESS = 0x2


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, text):
        super().__init__()
        ole32.CLSIDFromString(ctypes.c_wchar_p("{" + text + "}"), ctypes.byref(self))


CLSID_MMDeviceEnumerator = GUID("BCDE0395-E52F-467C-8E3D-C4579291692E")
IID_IMMDeviceEnumerator = GUID("A95664D2-9614-4F35-A746-DE8DB63617E6")
IID_IAudioSessionManager2 = GUID("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F")
IID_IAudioSessionControl2 = GUID("BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D")
# Windows'un kendi ses ayarlarının kullandığı (belgelenmemiş ama Vista'dan beri aynı) varsayılan cihaz arabirimi
CLSID_PolicyConfigClient = GUID("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9")
IID_IPolicyConfig = GUID("F8679F50-850A-41CF-9C72-430F290290C8")


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]

    def __init__(self, fmtid, pid):
        super().__init__()
        self.fmtid = GUID(fmtid)
        self.pid = pid


class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", wintypes.USHORT), ("r1", wintypes.USHORT), ("r2", wintypes.USHORT), ("r3", wintypes.USHORT),
                ("value", ctypes.c_void_p), ("extra", ctypes.c_void_p)]


PKEY_FRIENDLY_NAME = PROPERTYKEY("A45C254E-DF1C-4EFD-8020-67D146A850E0", 14)
PKEY_DEVICE_DESC = PROPERTYKEY("A45C254E-DF1C-4EFD-8020-67D146A850E0", 2)
PKEY_ENUMERATOR = PROPERTYKEY("A45C254E-DF1C-4EFD-8020-67D146A850E0", 24)
PKEY_FORM_FACTOR = PROPERTYKEY("1DA5D803-D492-4EDD-8C23-E0C0FFEE7F0E", 0)
VT_UI4, VT_LPWSTR = 19, 31


def _call(obj, index, *args, restype=ctypes.HRESULT, argtypes=()):
    """COM arabirimindeki `index`. yöntemi çağırır (vtable)."""
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return prototype(vtable[index])(obj, *args)


def _release(obj):
    if obj:
        _call(obj, 2, restype=wintypes.ULONG)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


def _descendants(root):
    """root sürecinin tüm alt süreçleri (WebView2 tarayıcı süreci ve onun ses hizmeti dahil)."""
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (0, -1, ctypes.c_void_p(-1).value):
        return set()
    children = {}
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            children.setdefault(entry.th32ParentProcessID, []).append(entry.th32ProcessID)
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    found, stack = set(), [root]
    while stack:
        for child in children.get(stack.pop(), ()):
            if child not in found and child != root:
                found.add(child)
                stack.append(child)
    return found


def _sessions(enumerator):
    """Etkin tüm çıkış cihazlarındaki ses oturumları: [(IAudioSessionControl2, süreç kimliği), ...] (çağıran bırakır)."""
    out = []
    collection = ctypes.c_void_p()
    if _call(enumerator, 3, E_RENDER, DEVICE_STATE_ACTIVE, ctypes.byref(collection),
             argtypes=(ctypes.c_int, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))) < 0:
        return out
    try:
        count = wintypes.UINT()
        _call(collection, 3, ctypes.byref(count), argtypes=(ctypes.POINTER(wintypes.UINT),))
        for i in range(count.value):
            device = ctypes.c_void_p()
            if _call(collection, 4, i, ctypes.byref(device), argtypes=(wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))) < 0:
                continue
            manager = ctypes.c_void_p()
            try:
                if _call(device, 3, ctypes.byref(IID_IAudioSessionManager2), CLSCTX_ALL, None, ctypes.byref(manager),
                         argtypes=(ctypes.POINTER(GUID), wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))) < 0:
                    continue
                sessions = ctypes.c_void_p()
                if _call(manager, 5, ctypes.byref(sessions), argtypes=(ctypes.POINTER(ctypes.c_void_p),)) < 0:
                    continue
                try:
                    total = ctypes.c_int()
                    _call(sessions, 3, ctypes.byref(total), argtypes=(ctypes.POINTER(ctypes.c_int),))
                    for j in range(total.value):
                        control = ctypes.c_void_p()
                        if _call(sessions, 4, j, ctypes.byref(control), argtypes=(ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))) < 0:
                            continue
                        control2 = ctypes.c_void_p()
                        hr = _call(control, 0, ctypes.byref(IID_IAudioSessionControl2), ctypes.byref(control2),
                                   argtypes=(ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)))
                        _release(control)
                        if hr < 0:
                            continue
                        pid = wintypes.DWORD()
                        if _call(control2, 14, ctypes.byref(pid), argtypes=(ctypes.POINTER(wintypes.DWORD),)) < 0:
                            _release(control2)
                            continue
                        out.append((control2, pid.value))
                finally:
                    _release(sessions)
            finally:
                _release(manager)
                _release(device)
    finally:
        _release(collection)
    return out


def _get_text(control, index):
    text = ctypes.c_wchar_p()
    if _call(control, index, ctypes.byref(text), argtypes=(ctypes.POINTER(ctypes.c_wchar_p),)) < 0:
        return None
    value = text.value
    ole32.CoTaskMemFree(text)
    return value


def label_sessions(name, icon=None, root=None):
    """Süreç ağacımızdaki ses oturumlarına ad/simge verir. Değiştirilen oturum sayısını döner."""
    ours = _descendants(root or os.getpid()) | {root or os.getpid()}
    enumerator = ctypes.c_void_p()
    if ole32.CoCreateInstance(ctypes.byref(CLSID_MMDeviceEnumerator), None, CLSCTX_ALL,
                              ctypes.byref(IID_IMMDeviceEnumerator), ctypes.byref(enumerator)) < 0:
        return 0
    changed = 0
    try:
        for control, pid in _sessions(enumerator):
            try:
                if pid not in ours:
                    continue
                if _get_text(control, 4) != name:
                    _call(control, 5, name, None, argtypes=(wintypes.LPCWSTR, ctypes.c_void_p))
                    changed += 1
                if icon and _get_text(control, 6) != icon:
                    _call(control, 7, icon, None, argtypes=(wintypes.LPCWSTR, ctypes.c_void_p))
            finally:
                _release(control)
    finally:
        _release(enumerator)
    return changed


def _enumerator():
    enumerator = ctypes.c_void_p()
    if ole32.CoCreateInstance(ctypes.byref(CLSID_MMDeviceEnumerator), None, CLSCTX_ALL,
                              ctypes.byref(IID_IMMDeviceEnumerator), ctypes.byref(enumerator)) < 0:
        return None
    return enumerator


def _prop(store, key):
    value = PROPVARIANT()
    if _call(store, 5, ctypes.byref(key), ctypes.byref(value),
             argtypes=(ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))) < 0:
        return None
    try:
        if value.vt == VT_LPWSTR and value.value:
            return ctypes.wstring_at(value.value)
        if value.vt == VT_UI4:
            return ctypes.c_uint32(value.value or 0).value
        return None
    finally:
        ole32.PropVariantClear(ctypes.byref(value))


def _kind(bus, form_factor, name):
    bus = (bus or "").upper()
    if bus.startswith("BTH") or "BLUETOOTH" in (name or "").upper():
        return "bluetooth"
    if form_factor in (3, 5):  # kulaklık, mikrofonlu kulaklık
        return "headphones"
    if bus == "USB":
        return "usb"
    return "speaker"


def _describe(device, default_id):
    device_id = _get_text(device, 5)
    store = ctypes.c_void_p()
    if not device_id or _call(device, 4, 0, ctypes.byref(store), argtypes=(wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))) < 0:
        return None
    try:
        full = _prop(store, PKEY_FRIENDLY_NAME) or ""
        desc = _prop(store, PKEY_DEVICE_DESC) or ""
        kind = _kind(_prop(store, PKEY_ENUMERATOR), _prop(store, PKEY_FORM_FACTOR), full)
    finally:
        _release(store)
    # Windows adı "Kulaklık (Galaxy Buds2)" biçiminde: Bluetooth'ta asıl ad parantezin içindedir
    name = full
    if kind == "bluetooth" and "(" in full and full.endswith(")"):
        name = full[full.index("(") + 1:-1].strip() or full
    return {"id": device_id, "name": name or desc or "Ses cihazı", "full": full, "kind": kind, "active": device_id == default_id}


def outputs():
    """Etkin ses çıkışları: {"current": {...} | None, "outputs": [{"id","name","full","kind","active"}], "switch": bool}"""
    enumerator = _enumerator()
    if not enumerator:
        return {"outputs": [], "current": None, "switch": False}
    found, default_id = [], None
    try:
        default = ctypes.c_void_p()
        if _call(enumerator, 4, E_RENDER, 1, ctypes.byref(default),
                 argtypes=(ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))) >= 0:
            default_id = _get_text(default, 5)
            _release(default)
        collection = ctypes.c_void_p()
        if _call(enumerator, 3, E_RENDER, DEVICE_STATE_ACTIVE, ctypes.byref(collection),
                 argtypes=(ctypes.c_int, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))) >= 0:
            try:
                count = wintypes.UINT()
                _call(collection, 3, ctypes.byref(count), argtypes=(ctypes.POINTER(wintypes.UINT),))
                for i in range(count.value):
                    device = ctypes.c_void_p()
                    if _call(collection, 4, i, ctypes.byref(device), argtypes=(wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))) < 0:
                        continue
                    try:
                        info = _describe(device, default_id)
                        if info:
                            found.append(info)
                    finally:
                        _release(device)
            finally:
                _release(collection)
    finally:
        _release(enumerator)
    return {"outputs": found, "current": next((o for o in found if o["active"]), None), "switch": True}


def set_default(device_id):
    """Windows'un varsayılan ses çıkışını değiştirir (görev çubuğundaki ses menüsünden cihaz seçmekle aynı)."""
    policy = ctypes.c_void_p()
    if ole32.CoCreateInstance(ctypes.byref(CLSID_PolicyConfigClient), None, CLSCTX_ALL,
                              ctypes.byref(IID_IPolicyConfig), ctypes.byref(policy)) < 0:
        return False
    try:
        ok = True
        for role in (0, 1, 2):  # konsol, çoklu ortam, iletişim
            ok = _call(policy, 13, device_id, role, argtypes=(wintypes.LPCWSTR, ctypes.c_int)) >= 0 and ok
        return ok
    finally:
        _release(policy)


class SessionLabeler:
    """Arka planda arada bir (ve çalma başlayınca) oturumları adlandırır, ses çıkışlarındaki değişikliği bildirir.
    Kendi COM (MTA) iş parçacığında çalışır."""

    def __init__(self, name="SOUND", icon=None, every=4.0, on_outputs=None):
        self.name, self.icon, self.every = name, icon, every
        self.on_outputs = on_outputs  # (önceki, şimdiki) — kulaklık takıldı/çıktı, Bluetooth bağlandı, varsayılan değişti
        self.last_outputs = None
        self.wake = threading.Event()
        self.stopped = False
        threading.Thread(target=self._run, name="audiosession", daemon=True).start()

    def poke(self, icon=None):
        if icon:
            self.icon = icon
        self.wake.set()

    def stop(self):
        self.stopped = True
        self.wake.set()

    def _run(self):
        ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
        while not self.stopped:
            try:
                label_sessions(self.name, self.icon)
            except Exception:
                pass
            if self.on_outputs:
                try:
                    state = outputs()
                    signature = [(o["id"], o["active"]) for o in state["outputs"]]
                    if self.last_outputs is not None and signature != self.last_outputs[0]:
                        self.on_outputs(self.last_outputs[1], state)
                    self.last_outputs = (signature, state)
                except Exception:
                    pass
            self.wake.wait(self.every)
            self.wake.clear()
