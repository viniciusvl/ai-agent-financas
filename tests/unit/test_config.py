from app.config import Settings


def test_allowed_user_ids_from_comma_separated_string(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "111, 222,")
    assert Settings(_env_file=None).allowed_user_ids == [111, 222]


def test_defaults():
    settings = Settings(_env_file=None)
    assert settings.timezone == "Asia/Shanghai"
    assert settings.default_currency == "CNY"
    assert settings.whisper_base_url is None


def test_public_base_url_trailing_slash_removed():
    assert Settings(_env_file=None, public_base_url="https://x.com/").public_base_url == (
        "https://x.com"
    )
