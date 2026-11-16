"""Linux medya kontrolleri (MPRIS, D-Bus): klavyedeki ⏯ ⏭ ⏮ tuşları, kulaklık düğmeleri, masaüstünün
medya bildirimi / kilit ekranı SOUND'u yönetir; şarkı adı, sanatçı ve kapak orada görünür.

mediakeys.py'deki Windows sürümüyle aynı arayüz: create(schedule, on_button, on_raise) → nesne.update(track, playing, loading).
dbus-next saf Python'dur (pip ile kurulur); kendi asyncio döngüsünde, ayrı bir iş parçacığında çalışır.
"""
import asyncio
import re
import threading

BUS_NAME = "org.mpris.MediaPlayer2.sound"
OBJECT_PATH = "/org/mpris/MediaPlayer2"


def _interfaces(on_button, on_raise):
    from dbus_next import Variant
    from dbus_next.service import PropertyAccess, ServiceInterface, dbus_property, method

    class Root(ServiceInterface):
        def __init__(self):
            super().__init__("org.mpris.MediaPlayer2")

        @method()
        def Raise(self):
            on_raise()

        @method()
        def Quit(self):
            pass

        @dbus_property(access=PropertyAccess.READ)
        def CanQuit(self) -> "b":
            return False

        @dbus_property(access=PropertyAccess.READ)
        def CanRaise(self) -> "b":
            return True

        @dbus_property(access=PropertyAccess.READ)
        def HasTrackList(self) -> "b":
            return False

        @dbus_property(access=PropertyAccess.READ)
        def Identity(self) -> "s":
            return "SOUND"

        @dbus_property(access=PropertyAccess.READ)
        def DesktopEntry(self) -> "s":
            return "sound"  # ~/.local/share/applications/sound.desktop (install.sh)

        @dbus_property(access=PropertyAccess.READ)
        def SupportedUriSchemes(self) -> "as":
            return []

        @dbus_property(access=PropertyAccess.READ)
        def SupportedMimeTypes(self) -> "as":
            return []

    class Player(ServiceInterface):
        def __init__(self):
            super().__init__("org.mpris.MediaPlayer2.Player")
            self.status = "Stopped"
            self.meta = {}

        @method()
        def Next(self):
            on_button("next")

        @method()
        def Previous(self):
            on_button("previous")

        @method()
        def Pause(self):
            on_button("pause")

        @method()
        def Play(self):
            on_button("play")

        @method()
        def PlayPause(self):
            on_button("toggle")

        @method()
        def Stop(self):
            on_button("pause")

        @method()
        def Seek(self, offset: "x"):
            pass

        @method()
        def SetPosition(self, track_id: "o", position: "x"):
            pass

        @method()
        def OpenUri(self, uri: "s"):
            pass

        @dbus_property(access=PropertyAccess.READ)
        def PlaybackStatus(self) -> "s":
            return self.status

        @dbus_property(access=PropertyAccess.READ)
        def Metadata(self) -> "a{sv}":
            return self.meta

        @dbus_property(access=PropertyAccess.READ)
        def Rate(self) -> "d":
            return 1.0

        @dbus_property(access=PropertyAccess.READ)
        def MinimumRate(self) -> "d":
            return 1.0

        @dbus_property(access=PropertyAccess.READ)
        def MaximumRate(self) -> "d":
            return 1.0

        @dbus_property(access=PropertyAccess.READ)
        def Volume(self) -> "d":
            return 1.0

        @dbus_property(access=PropertyAccess.READ)
        def Position(self) -> "x":
            return 0

        @dbus_property(access=PropertyAccess.READ)
        def CanGoNext(self) -> "b":
            return True

        @dbus_property(access=PropertyAccess.READ)
        def CanGoPrevious(self) -> "b":
            return True

        @dbus_property(access=PropertyAccess.READ)
        def CanPlay(self) -> "b":
            return True

        @dbus_property(access=PropertyAccess.READ)
        def CanPause(self) -> "b":
            return True

        @dbus_property(access=PropertyAccess.READ)
        def CanSeek(self) -> "b":
            return False

        @dbus_property(access=PropertyAccess.READ)
        def CanControl(self) -> "b":
            return True

        def apply(self, track, status):
            meta = {}
            if track:
                track_id = re.sub(r"[^A-Za-z0-9_]", "_", str(track.get("id") or "x"))
                meta = {"mpris:trackid": Variant("o", f"/org/sound/track/t{track_id}"),
                        "xesam:title": Variant("s", track.get("title") or ""),
                        "xesam:artist": Variant("as", [track.get("artist") or ""])}
                if track.get("thumbnail"):
                    meta["mpris:artUrl"] = Variant("s", track["thumbnail"])
                if track.get("duration"):
                    meta["mpris:length"] = Variant("x", int(track["duration"]) * 1_000_000)
            changed = {}
            if status != self.status:
                self.status = status
                changed["PlaybackStatus"] = status
            if meta.keys() != self.meta.keys() or any(meta[k].value != self.meta[k].value for k in meta):
                self.meta = meta
                changed["Metadata"] = meta
            if changed:
                self.emit_properties_changed(changed)

    return Root(), Player()


class MprisControls:
    def __init__(self, on_button, on_raise):
        self.loop = asyncio.new_event_loop()
        self.player = None
        ready = threading.Event()
        error = []

        async def setup():
            from dbus_next.aio import MessageBus
            bus = await MessageBus().connect()
            root, player = _interfaces(on_button, on_raise)
            bus.export(OBJECT_PATH, root)
            bus.export(OBJECT_PATH, player)
            await bus.request_name(BUS_NAME)
            self.bus, self.player = bus, player

        def run():
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_until_complete(setup())
            except Exception as failure:
                error.append(failure)
                ready.set()
                return
            ready.set()
            self.loop.run_forever()

        threading.Thread(target=run, daemon=True, name="mpris").start()
        ready.wait(5)
        if error or self.player is None:
            raise RuntimeError(f"MPRIS kurulamadı: {error[0] if error else 'zaman aşımı'}")

    def update(self, track, playing, loading):
        status = "Stopped" if not track else "Playing" if playing or loading else "Paused"
        self.loop.call_soon_threadsafe(self.player.apply, track, status)


def create(on_button, on_raise=lambda: None):
    """D-Bus oturum hattı ya da dbus-next yoksa (sunucu, kapsayıcı) None döner; SOUND medya tuşları olmadan çalışır."""
    try:
        return MprisControls(on_button, on_raise)
    except Exception:
        return None
