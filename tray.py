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

    def notify(self, message):
        if self.icon:
            try:
                self.icon.notify(message, "SOUND")
            except Exception:
                pass

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
