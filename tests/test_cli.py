import src.cli as cli


def test_paint_adds_ansi_codes_when_color_is_enabled(monkeypatch):
    monkeypatch.setattr(cli, "_COLOR_ENABLED", True)

    assert cli._paint("ready", cli._Ansi.GREEN) == "\033[32mready\033[0m"


def test_paint_returns_plain_text_when_color_is_disabled(monkeypatch):
    monkeypatch.setattr(cli, "_COLOR_ENABLED", False)

    assert cli._paint("ready", cli._Ansi.GREEN) == "ready"


def test_shared_header_does_not_repeat_authorization_notice(capsys):
    cli.print_header()

    assert "Authorization notice" not in capsys.readouterr().out


def test_result_folder_defaults_to_desktop(monkeypatch, tmp_path):
    desktop = tmp_path / "Desktop"
    monkeypatch.setattr(cli, "_desktop_directory", lambda: desktop)
    monkeypatch.delenv("DORK_SEARCHER_OUTPUT_DIR", raising=False)
    monkeypatch.setattr(cli, "_RESULT_DIRECTORY", None)

    result = cli.ensure_result_folder()

    assert result == (desktop / "Dork_Searcher_Results").resolve()
    assert result.is_dir()


def test_result_folder_falls_back_when_desktop_result_is_unavailable(monkeypatch, tmp_path):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    (desktop / "Dork_Searcher_Results").write_text(
        "this file blocks directory creation", encoding="utf-8"
    )
    fallback_root = tmp_path / "local-app-data"
    monkeypatch.setattr(cli, "_desktop_directory", lambda: desktop)
    monkeypatch.setenv("LOCALAPPDATA", str(fallback_root))
    monkeypatch.delenv("DORK_SEARCHER_OUTPUT_DIR", raising=False)
    monkeypatch.setattr(cli, "_RESULT_DIRECTORY", None)

    result = cli.ensure_result_folder()

    assert result == (fallback_root / "Dork_Searcher" / "Results").resolve()
    assert result.is_dir()


def test_custom_dorks_are_scoped_and_persisted(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_RESULT_DIRECTORY", tmp_path)

    cli.save_custom_dork_templates(["inurl:graphql", 'site:{t} ext:env "DB_PASSWORD"'])

    assert cli.load_custom_dork_templates() == [
        "site:{t} (inurl:graphql)",
        'site:{t} ext:env "DB_PASSWORD"',
    ]


def test_main_menu_uses_requested_sections(monkeypatch, capsys):
    monkeypatch.setattr(cli, "clear_screen", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: "0")

    cli.main_menu()

    output = capsys.readouterr().out
    assert "Dork_Search" in output
    assert "Wayback / Parser" in output
    assert "Sub-Domain Search" in output
    assert "[6] Certificate Transparency Discovery" in output
    assert "[8] Active HTTP Header/CORS Probe" in output
