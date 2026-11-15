from cinefacts import config


def test_parse_env_handles_windows_and_shell_styles():
    text = ('# comment\r\n'
            'export PIXABAY_API_KEY = "abc-123"\r\n'
            "OTHER='x y'\r\n"
            '\r\n'
            'EMPTY=\r\n')
    env = config.parse_env(text)
    assert env["PIXABAY_API_KEY"] == "abc-123"
    assert env["OTHER"] == "x y"
    assert env["EMPTY"] == ""
    assert "# comment" not in env


def test_load_env_strips_utf8_bom_from_windows_notepad(tmp_path):
    f = tmp_path / ".env"
    f.write_bytes("﻿PIXABAY_API_KEY=abc\r\n".encode("utf-8"))
    assert config.load_env(f) == {"PIXABAY_API_KEY": "abc"}


def test_load_env_missing_file_returns_empty(tmp_path):
    assert config.load_env(tmp_path / "nope.env") == {}


def test_repo_root_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert (config.REPO_ROOT / "cinefacts" / "config.py").is_file()
    assert config.STYLES_DIR == config.REPO_ROOT / "styles"


def test_load_style_documentary_has_spec_values():
    s = config.load_style("documentary")
    assert s["resolution"] == [1920, 1080]
    assert s["fps"] == 24
    assert s["preview"]["resolution"] == [1280, 720]
    assert s["loudness"] == {"integrated_lufs": -14, "true_peak_db": -1}
    assert s["resources"]["memory_max"] == "2500M"


def test_load_style_missing_key_names_it(tmp_path, monkeypatch):
    (tmp_path / "bad.json").write_text('{"fps": 24}')
    monkeypatch.setattr(config, "STYLES_DIR", tmp_path)
    try:
        config.load_style("bad")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "resolution" in str(e)
