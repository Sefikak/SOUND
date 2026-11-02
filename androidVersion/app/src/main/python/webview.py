"""Masaüstündeki pywebview'in yerine: webapp.py aynen kullanılabilsin diye yalnızca adlar var.
Android'de pencereyi MainActivity açar; ek pencere gerektiren işler (Google girişi) henüz yok."""


class FileDialog:
    OPEN = 10
    SAVE = 30
    FOLDER = 20


def create_window(*args, **kwargs):
    raise RuntimeError("Bu özellik mobil sürümde henüz yok")


def start(*args, **kwargs):
    pass
