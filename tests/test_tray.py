import tray


def test_icon_image_is_square():
    img = tray.make_image()
    assert img.size == (64, 64)


def test_menu_actions_call_callbacks():
    calls = []
    t = tray.TrayIcon(on_show=lambda: calls.append("show"), on_quit=lambda: calls.append("quit"),
                      on_pixaroma=lambda: calls.append("pixaroma"))
    items = [item for item in t.icon.menu.items if item.text]
    assert [item.text for item in items] == ["Show", "Pixaroma", "Quit"]
    assert items[0].default  # clicking the icon = Show
    for item in items:
        item(t.icon)
    assert calls == ["show", "pixaroma", "quit"]


def test_notify_before_icon_shown_is_ignored():
    t = tray.TrayIcon(on_show=lambda: None, on_quit=lambda: None)
    t.notify("hello")  # the icon is not displayed yet: nothing to notify through, no error


def test_tooltip():
    t = tray.TrayIcon(on_show=lambda: None, on_quit=lambda: None)
    t.set_tooltip("watching")
    assert t.icon.title == "watching"


def test_menu_follows_language():
    import i18n
    t = tray.TrayIcon(on_show=lambda: None, on_quit=lambda: None)
    i18n.set_language("de")
    assert [item.text for item in t.icon.menu.items if item.text] == ["Anzeigen", "Pixaroma", "Beenden"]
