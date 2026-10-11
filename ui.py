"""Small Tkinter helpers shared by the windows."""


def center_on_screen(window) -> None:
    """Centers the window on the screen (Tk would put it in the top-left corner)."""
    window.update_idletasks()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    x = (window.winfo_screenwidth() - width) // 2
    y = (window.winfo_screenheight() - height) // 2
    window.geometry(f"+{max(x, 0)}+{max(y, 0)}")


APP_ID = "marche-obscure.Deziporama"  # Windows taskbar identity (otherwise grouped as "Python")


def _set_app_id(app_id: str) -> None:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)


def set_app_id() -> None:
    """Makes Windows show Deziporama, with its own icon, in the taskbar. Call before creating windows."""
    try:
        _set_app_id(APP_ID)
    except (AttributeError, OSError):
        pass


def apply_app_icon(root, ico_path):
    """Logo icon for `root` and, as the default, for every later window: dialogs and message
    boxes included, even when the main window is hidden. Returns the images to keep referenced."""
    from pathlib import Path

    from PIL import ImageTk

    import logo

    images = [logo.icon_image(size) for size in (64, 32, 16)]
    if any(img is None for img in images):
        return []
    ico_path = Path(ico_path)
    try:
        if ico_path.exists() or logo.write_ico(ico_path):
            root.iconbitmap(default=str(ico_path))
    except Exception:  # noqa: BLE001 - a missing icon must never stop the application
        pass
    photos = [ImageTk.PhotoImage(img, master=root) for img in images]
    root.iconphoto(True, *photos)
    return photos
