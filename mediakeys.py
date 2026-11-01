"""Windows medya kontrolleri (SMTC): klavyedeki ⏯ ⏭ ⏮ tuşları, ses açılır penceresindeki
medya kartı ve kilit ekranı SOUND'u yönetir; şarkı adı, sanatçı ve kapak orada görünür.

Masaüstü uygulamasında SMTC'ye ulaşmanın kolay yolu: hiçbir şey çalmayan bir WinRT MediaPlayer
oluşturup onun kontrollerini kendimiz yönetmek (command_manager kapalı).
"""


class MediaControls:
    def __init__(self, schedule, on_button):
        from winrt.windows.media import MediaPlaybackStatus, MediaPlaybackType, SystemMediaTransportControlsButton
        from winrt.windows.media.playback import MediaPlayer

        self.Status = MediaPlaybackStatus
        self.schedule = schedule
        self.on_button = on_button
        self.buttons = {
            SystemMediaTransportControlsButton.PLAY: "play",
            SystemMediaTransportControlsButton.PAUSE: "pause",
            SystemMediaTransportControlsButton.STOP: "pause",
            SystemMediaTransportControlsButton.NEXT: "next",
            SystemMediaTransportControlsButton.PREVIOUS: "previous",
        }
        self.player = MediaPlayer()  # referansı tut; çöp toplanırsa kontroller kaybolur
        self.player.command_manager.is_enabled = False
        self.controls = self.player.system_media_transport_controls
        self.controls.is_enabled = True
        self.controls.is_play_enabled = True
        self.controls.is_pause_enabled = True
        self.controls.is_stop_enabled = True
        self.controls.is_next_enabled = True
        self.controls.is_previous_enabled = True
        self.controls.display_updater.type = MediaPlaybackType.MUSIC
        self.controls.playback_status = MediaPlaybackStatus.CLOSED
        self.token = self.controls.add_button_pressed(self._pressed)
        self.shown_track = None
        self.shown_status = None

    def _pressed(self, sender, args):
        # Windows bunu başka bir iş parçacığında çağırır; arayüze kuyruk üzerinden geç
        action = self.buttons.get(args.button)
        if action:
            self.schedule(lambda: self.on_button(action))

    def update(self, track, playing, loading):
        from winrt.windows.foundation import Uri
        from winrt.windows.storage.streams import RandomAccessStreamReference

        track_id = track["id"] if track else None
        if track_id != self.shown_track:
            self.shown_track = track_id
            updater = self.controls.display_updater
            if track:
                updater.music_properties.title = track.get("title") or ""
                updater.music_properties.artist = track.get("artist") or ""  # sanatçısı boş şarkılarda çökmesin
                if track.get("thumbnail"):
                    updater.thumbnail = RandomAccessStreamReference.create_from_uri(Uri(track["thumbnail"]))
            else:
                updater.clear_all()
                updater.type = 1  # MediaPlaybackType.MUSIC
            updater.update()

        if not track:
            status = self.Status.CLOSED
        elif loading:
            status = self.Status.CHANGING
        elif playing:
            status = self.Status.PLAYING
        else:
            status = self.Status.PAUSED
        if status != self.shown_status:
            self.shown_status = status
            self.controls.playback_status = status


def create(schedule, on_button):
    """Windows'ta medya kontrollerini kurar; kurulamazsa (paket yok, başka sistem) None döner."""
    try:
        return MediaControls(schedule, on_button)
    except Exception:
        return None
