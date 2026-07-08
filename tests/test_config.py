import textwrap
from wisper.config import Config, load_config


def test_load_config_reads_values(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent("""
        hotkey: "right ctrl"
        partial_interval_sec: 0.5
        device: "cpu"
        model_dir: "models/x"
        overlay_position: "bottom-center"
        overlay_width: 240
        inject_min_chars: 2
        realtime_typing: false
        silence_sec: 0.8
        log_level: "DEBUG"
    """), encoding="utf-8")
    cfg = load_config(p)
    assert isinstance(cfg, Config)
    assert cfg.hotkey == "right ctrl"
    assert cfg.partial_interval_sec == 0.5
    assert cfg.overlay_width == 240
    assert cfg.realtime_typing is False
    assert cfg.silence_sec == 0.8


def test_load_config_uses_defaults_for_missing_keys(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text('hotkey: "f9"\n', encoding="utf-8")
    cfg = load_config(p)
    assert cfg.hotkey == "f9"
    assert cfg.realtime_typing is True      # defaut
    assert cfg.partial_interval_sec == 0.7  # defaut
    assert cfg.device == "cpu"             # defaut
