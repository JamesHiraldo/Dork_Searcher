import src.cli as cli


def test_paint_adds_ansi_codes_when_color_is_enabled(monkeypatch):
    monkeypatch.setattr(cli, "_COLOR_ENABLED", True)

    assert cli._paint("ready", cli._Ansi.GREEN) == "\033[32mready\033[0m"


def test_paint_returns_plain_text_when_color_is_disabled(monkeypatch):
    monkeypatch.setattr(cli, "_COLOR_ENABLED", False)

    assert cli._paint("ready", cli._Ansi.GREEN) == "ready"
