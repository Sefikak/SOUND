"""Sistem tepsisi (bildirim alanı) simgesi: pencere kapatılınca SOUND burada çalmaya devam eder.

Sol tık pencereyi açar; sağ tık menüsü: Aç, Çal/Duraklat, Sonraki, Önceki, Çıkış. Windows'ta ve Linux'ta
(pystray) çalışır; kurulamazsa start() False döner ve pencere kapatılınca uygulama eskisi gibi tamamen kapanır.
"""
import threading

try:
    import pystray
    from PIL import Image
except Exception:  # paket yok (güncelleme pip'i henüz kurmadı) ya da telefon
    pystray = None


class Tray:
    def __init__(self, icon_path, on_show, on_command, on_quit):
        self.icon_path = icon_path
        self.on_show, self.on_command, self.on_quit = on_show, on_command, on_quit
        self.icon = None
        self.playing = False
        self.on_balloon = None  # bildirime tıklanınca (Windows)
        self.on_menu = None     # Windows: sağ tıkta temalı menü (webapp.TrayMenu.show); True dönerse sistem menüsü açılmaz

    def start(self):
        if pystray is None:
            return False
        try:
            image = Image.open(self.icon_path)
            item = pystray.MenuItem
            menu = pystray.Menu(
                item("SOUND'u aç", lambda: self.on_show(), default=True),  # sol tık / çift tık da bunu yapar
                pystray.Menu.SEPARATOR,
                item(lambda _: "Duraklat" if self.playing else "Çal", lambda: self.on_command("toggle")),
                item("Sonraki", lambda: self.on_command("next")),
                item("Önceki", lambda: self.on_command("previous")),
                pystray.Menu.SEPARATOR,
                item("Çıkış", lambda: self.on_quit()),
            )
            self.icon = pystray.Icon("SOUND", image, "SOUND", menu)
            self._hook_balloon_click()
            ready = threading.Event()

            def run():
                try:
                    self.icon.run(setup=lambda icon: (setattr(icon, "visible", True), ready.set()))
                except Exception:
                    pass
                finally:
                    ready.set()

            threading.Thread(target=run, daemon=True, name="tray").start()
            ready.wait(5)
            return bool(self.icon.visible)
        except Exception:
            self.icon = None
            return False

    def icon_rect(self):
        """Windows: simgenin ekrandaki yeri (left, top, right, bottom, fiziksel piksel); taşma kutusundaysa oradaki yeri.
        Bulunamazsa None."""
        if not self.icon or not getattr(self.icon, "_hwnd", None):
            return None
        try:
            import ctypes
            from ctypes import wintypes

            class NOTIFYICONIDENTIFIER(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                            ("guidItem", ctypes.c_byte * 16)]
            ident = NOTIFYICONIDENTIFIER(cbSize=ctypes.sizeof(NOTIFYICONIDENTIFIER), hWnd=self.icon._hwnd,
                                         uID=id(self.icon) & 0xFFFFFFFF)  # pystray simgeyi id(icon) ile kaydediyor
            rect = wintypes.RECT()
            fn = ctypes.WinDLL("shell32").Shell_NotifyIconGetRect
            fn.argtypes = [ctypes.POINTER(NOTIFYICONIDENTIFIER), ctypes.POINTER(wintypes.RECT)]
            if fn(ctypes.byref(ident), ctypes.byref(rect)) != 0:  # S_OK değil
                return None
            if rect.right <= rect.left or rect.bottom <= rect.top:
                return None
            return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            return None

    def set_state(self, title, playing):
        """İmlecin üstüne gelince görünen yazı (çalan şarkı) ve menüdeki Çal/Duraklat."""
        if not self.icon:
            return
        self.playing = playing
        try:
            self.icon.title = (title or "SOUND")[:120]  # Windows en fazla 127 karakter gösterir
            self.icon.update_menu()
        except Exception:
            pass

    def _hook_balloon_click(self):
        """pystray bildirime tıklamayı ve sağ tıkı ayrıca bildirmiyor: Windows iletileri burada yakalanır
        (NIN_BALLOONUSERCLICK, WM_RBUTTONUP)."""
        handler = getattr(self.icon, "_on_notify", None)
        if handler is None:
            return

        def on_notify(wparam, lparam):
            if lparam == 0x0205 and self.on_menu:  # WM_RBUTTONUP: kendi menümüz; açılamazsa sistem menüsü
                try:
                    if self.on_menu():
                        return
                except Exception:
                    pass
            if lparam == 0x0405:  # NIN_BALLOONUSERCLICK
                action, self.on_balloon = self.on_balloon, None
                if action:
                    threading.Thread(target=action, daemon=True).start()
                return
            return handler(wparam, lparam)
        try:
            self.icon._on_notify = on_notify
            self.icon._message_handlers[0x0400 + 11] = on_notify  # pystray'in WM_NOTIFY numarası
        except Exception:
            pass

    def notify(self, message, title="SOUND", on_click=None):
        if self.icon:
            try:
                self.on_balloon = on_click
                try:  # Windows: sistemin bildirim sesi çalmasın, SOUND kendi yumuşak sesini çalıyor (web/notify.wav)
                    from pystray._util import win32
                    self.icon._message(win32.NIM_MODIFY, win32.NIF_INFO, szInfo=message[:250], szInfoTitle=title[:60],
                                       dwInfoFlags=0x10)  # NIIF_NOSOUND
                except Exception:
                    self.icon.notify(message, title)
            except Exception:
                pass

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
