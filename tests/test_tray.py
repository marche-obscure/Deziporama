import tray


def test_icon_image_is_square():
    img = tray.make_image()
    assert img.size == (64, 64)


def test_menu_actions_call_callbacks():
    calls = []
    t = tray.TrayIcon(on_show=lambda: calls.append("show"), on_quit=lambda: calls.append("quit"))
    items = {item.text: item for item in t.icon.menu.items}
    assert set(items) == {"Show", "Quit"}
    assert items["Show"].default  # clicking the icon = Show
    items["Show"](t.icon)
    items["Quit"](t.icon)
    assert calls == ["show", "quit"]


def test_tooltip():
    t = tray.TrayIcon(on_show=lambda: None, on_quit=lambda: None)
    t.set_tooltip("watching")
    assert t.icon.title == "watching"
