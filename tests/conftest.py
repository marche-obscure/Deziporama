import pytest

import i18n


@pytest.fixture(autouse=True)
def english_by_default():
    """Every test starts in English; tests switching language never leak into others."""
    i18n.set_language("en")
    yield
    i18n.set_language("en")
