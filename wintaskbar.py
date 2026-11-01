"""Windows görev çubuğunda pencereye kendi kimliğini ve ikonunu verir.

Microsoft Store'dan kurulan Python paketli bir uygulama olduğu için Windows görev çubuğunda
pencerenin ikonunu değil Python'un ikonunu gösterir. Pencereye ayrı bir AppUserModelID atayınca
Windows onu ayrı bir uygulama sayar ve pencerenin kendi ikonunu kullanır.
"""
import ctypes
import os
from ctypes import wintypes


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, text):
        super().__init__()
        ctypes.oledll.ole32.CLSIDFromString(text, ctypes.byref(self))


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", ctypes.c_ulong)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("reserved1", ctypes.c_ushort), ("reserved2", ctypes.c_ushort),
                ("reserved3", ctypes.c_ushort), ("value", ctypes.c_wchar_p), ("padding", ctypes.c_void_p)]


VT_LPWSTR = 31
IID_IPROPERTYSTORE = "{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}"
APP_USER_MODEL = "{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"
PID_RELAUNCH_COMMAND, PID_RELAUNCH_ICON, PID_RELAUNCH_NAME, PID_ID = 2, 3, 4, 5


def set_window_identity(hwnd, app_id, icon_path=None, name=None, command=None):
    store = ctypes.c_void_p()
    ctypes.oledll.shell32.SHGetPropertyStoreForWindow(
        wintypes.HWND(hwnd), ctypes.byref(GUID(IID_IPROPERTYSTORE)), ctypes.byref(store))
    vtable = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    set_value = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY),
                                   ctypes.POINTER(PROPVARIANT))(vtable[6])
    commit = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)(vtable[7])
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])

    def put(pid, text):
        key = PROPERTYKEY(GUID(APP_USER_MODEL), pid)
        value = PROPVARIANT(vt=VT_LPWSTR, value=text)
        set_value(store, ctypes.byref(key), ctypes.byref(value))

    try:
        # Yeniden başlatma bilgileri kimlikten önce yazılmalı
        if command:
            put(PID_RELAUNCH_COMMAND, command)
        if icon_path:
            put(PID_RELAUNCH_ICON, os.path.abspath(icon_path) + ",0")
        if name:
            put(PID_RELAUNCH_NAME, name)
        put(PID_ID, app_id)
        commit(store)
    finally:
        release(store)


# ---------- görev çubuğu önizlemesindeki butonlar (ITaskbarList3 thumbnail toolbar) ----------

CLSID_TASKBARLIST = "{56FDF344-FD6D-11D0-958A-006097C9A090}"
# ITaskbarList4, ITaskbarList3'ten türer: ihtiyacımız olan ThumbBar fonksiyonları aynı vtable sırasındadır
IID_ITASKBARLIST4 = "{C43DC798-95D1-4BEA-9030-BB99E2983A1A}"
WM_COMMAND = 0x0111
THBN_CLICKED = 0x1800
THB_ICON, THB_TOOLTIP, THB_FLAGS = 0x2, 0x4, 0x8
GWLP_WNDPROC = -4
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class THUMBBUTTON(ctypes.Structure):
    _fields_ = [("dwMask", wintypes.DWORD), ("iId", wintypes.UINT), ("iBitmap", wintypes.UINT),
                ("hIcon", wintypes.HICON), ("szTip", ctypes.c_wchar * 260), ("dwFlags", wintypes.DWORD)]


class ThumbBar:
    """Görev çubuğu simgesinin üstüne gelince çıkan önizlemeye önceki / çal-duraklat / sonraki ekler.

    Tıklamalar pencereye WM_COMMAND olarak gelir; pencere işleyicisini araya girerek yakalıyoruz.
    `schedule` tıklamaları pencere işleyicisinin dışında çalıştırmak için bir fonksiyon alır.
    Butonlar add() çağrılınca eklenir (pencere görev çubuğunda belirdikten sonra)."""

    PREV, PLAY, NEXT, SHUFFLE, REPEAT = 1, 2, 3, 4, 5
    ORDER = (SHUFFLE, PREV, PLAY, NEXT, REPEAT)

    def __init__(self, hwnd, icon_paths, on_click, schedule):
        user32 = ctypes.windll.user32
        user32.GetParent.restype = wintypes.HWND
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_void_p)
        user32.CallWindowProcW.restype = LRESULT
        user32.CallWindowProcW.argtypes = (ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.RegisterWindowMessageW.restype = wintypes.UINT

        self.user32 = user32
        self.on_click = on_click
        self.schedule = schedule
        self.playing = False
        self.shuffle = False
        self.repeat = "off"
        self.added = False
        self.hwnd = hwnd

        ctypes.windll.ole32.CoInitialize(None)
        self.taskbar = ctypes.c_void_p()
        ctypes.oledll.ole32.CoCreateInstance(ctypes.byref(GUID(CLSID_TASKBARLIST)), None, 1,
                                             ctypes.byref(GUID(IID_ITASKBARLIST4)), ctypes.byref(self.taskbar))
        vtable = ctypes.cast(self.taskbar, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)(vtable[3])(self.taskbar)  # HrInit
        button_call = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                         ctypes.POINTER(THUMBBUTTON))
        self._add_buttons = button_call(vtable[15])      # ThumbBarAddButtons
        self._update_buttons = button_call(vtable[16])   # ThumbBarUpdateButtons

        size = user32.GetSystemMetrics(49)  # SM_CXSMICON
        self.icons = {name: user32.LoadImageW(None, path, 1, size, size, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
                      for name, path in icon_paths.items()}

        # Gezgin yeniden başlarsa butonları tekrar eklememiz gerekir
        self.created_message = user32.RegisterWindowMessageW("TaskbarButtonCreated")
        self._proc = WNDPROC(self._window_proc)  # referansı tut, yoksa çöp toplanır ve uygulama çöker
        self._old_proc = user32.SetWindowLongPtrW(self.hwnd, GWLP_WNDPROC,
                                                  ctypes.cast(self._proc, ctypes.c_void_p))

    def _button(self, button_id):
        button = THUMBBUTTON()
        button.dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS
        button.iId = button_id
        if button_id == self.PREV:
            button.hIcon, button.szTip = self.icons["tb_prev"], "Önceki"
        elif button_id == self.NEXT:
            button.hIcon, button.szTip = self.icons["tb_next"], "Sonraki"
        elif button_id == self.SHUFFLE:
            button.hIcon = self.icons["tb_shuffle_on" if self.shuffle else "tb_shuffle"]
            button.szTip = "Karışık çalma: açık" if self.shuffle else "Karışık çalma: kapalı"
        elif button_id == self.REPEAT:
            button.hIcon = self.icons[{"off": "tb_repeat", "all": "tb_repeat_on", "one": "tb_repeat_one"}[self.repeat]]
            button.szTip = {"off": "Tekrar: kapalı", "all": "Tekrar: liste", "one": "Tekrar: bu şarkı"}[self.repeat]
        elif self.playing:
            button.hIcon, button.szTip = self.icons["tb_pause"], "Duraklat"
        else:
            button.hIcon, button.szTip = self.icons["tb_play"], "Çal"
        return button

    def add(self):
        count = len(self.ORDER)
        buttons = (THUMBBUTTON * count)(*(self._button(i) for i in self.ORDER))
        self.added = self._add_buttons(self.taskbar, self.hwnd, count, buttons) == 0

    def set_state(self, playing, shuffle, repeat):
        changed = [button_id for button_id, old, new in ((self.PLAY, self.playing, playing),
                                                         (self.SHUFFLE, self.shuffle, shuffle),
                                                         (self.REPEAT, self.repeat, repeat)) if old != new]
        self.playing, self.shuffle, self.repeat = playing, shuffle, repeat
        if self.added and changed:
            buttons = (THUMBBUTTON * len(changed))(*(self._button(i) for i in changed))
            self._update_buttons(self.taskbar, self.hwnd, len(changed), buttons)

    def _window_proc(self, hwnd, message, wparam, lparam):
        if message == WM_COMMAND and (wparam >> 16) & 0xFFFF == THBN_CLICKED:
            button_id = wparam & 0xFFFF
            self.schedule(lambda: self.on_click(button_id))
            return 0
        if message == self.created_message:
            self.added = False
            self.schedule(self.add)
        return self.user32.CallWindowProcW(self._old_proc, hwnd, message, wparam, lparam)


def thumbbar(root, icon_paths, on_click, schedule):
    """Tk penceresine ThumbBar kurar; olmazsa (ör. başka işletim sistemi) None döner."""
    if os.name != "nt":
        return None
    try:
        root.update_idletasks()
        bar = ThumbBar(ctypes.windll.user32.GetParent(root.winfo_id()), icon_paths, on_click, schedule)
    except OSError:
        return None
    root.after(600, bar.add)
    return bar


def apply(root, app_id, icon_path=None, name=None, command=None):
    """Tk kök penceresine uygula. Windows dışında ya da hata olursa sessizce geçer."""
    if os.name != "nt":
        return False
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        set_window_identity(hwnd, app_id, icon_path, name, command)
        return True
    except OSError:
        return False
