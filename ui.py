"""Small Tkinter helpers shared by the windows."""


def center_on_screen(window) -> None:
    """Centers the window on the screen (Tk would put it in the top-left corner)."""
    window.update_idletasks()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    x = (window.winfo_screenwidth() - width) // 2
    y = (window.winfo_screenheight() - height) // 2
    window.geometry(f"+{max(x, 0)}+{max(y, 0)}")
