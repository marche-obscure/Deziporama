import logo
import tray


def test_icon_from_logo_is_square_rgba():
    img = logo.icon_image(64)
    assert img is not None
    assert img.size == (64, 64)
    assert img.mode == "RGBA"


def test_icon_is_the_dez_and_slider_crop():
    # Crop C: lots of orange (letters) and green (zipper slider).
    img = logo.icon_image(64).convert("RGB")
    raw = img.tobytes()
    pixels = list(zip(raw[0::3], raw[1::3], raw[2::3]))
    orange = sum(1 for r, g, b in pixels if r > 180 and 60 < g < 140 and b < 80)
    green = sum(1 for r, g, b in pixels if g > 180 and r < 160 and b < 100)
    assert orange > len(pixels) * 0.15
    assert green > len(pixels) * 0.05


def test_banner_keeps_logo_proportions():
    img = logo.banner_image(420)
    assert img is not None
    w, h = img.size
    assert w == 420
    left, top, right, bottom = logo.BANNER_BOX
    assert abs(h - round(420 * (bottom - top) / (right - left))) <= 1


def test_missing_logo_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(logo, "LOGO_PATH", tmp_path / "absent.webp")
    assert logo.icon_image(64) is None
    assert logo.banner_image(420) is None


def test_tray_uses_logo():
    assert tray.make_image().tobytes() == logo.icon_image(64).tobytes()


def test_tray_falls_back_without_logo(tmp_path, monkeypatch):
    monkeypatch.setattr(logo, "LOGO_PATH", tmp_path / "absent.webp")
    img = tray.make_image()
    assert img.size == (64, 64)


def test_write_ico(tmp_path):
    from PIL import Image
    path = tmp_path / "x.ico"
    assert logo.write_ico(path)
    with Image.open(path) as ico:
        assert (32, 32) in ico.info["sizes"] and (256, 256) in ico.info["sizes"]


def test_write_ico_without_logo(tmp_path, monkeypatch):
    monkeypatch.setattr(logo, "LOGO_PATH", tmp_path / "absent.webp")
    assert not logo.write_ico(tmp_path / "x.ico")
