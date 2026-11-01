import os

from webapp import APP_ID, run


def main():
    if os.name == "nt":
        # Görev çubuğunda Python ikonu yerine uygulamanın kendi ikonu görünsün
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    run()
    # Arka planda süren indirmeleri beklemeden kapan
    os._exit(0)


if __name__ == "__main__":
    main()
