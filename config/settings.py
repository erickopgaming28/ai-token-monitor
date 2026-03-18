from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path


def _default_claude_base() -> str:
    return str(Path.home() / ".claude" / "projects")


def _app_data_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    d = base / "AITokenMonitor"
    d.mkdir(parents=True, exist_ok=True)
    return d


APP_DATA_DIR = _app_data_dir()
DB_PATH = APP_DATA_DIR / "token_monitor.db"
SETTINGS_PATH = APP_DATA_DIR / "settings.json"


@dataclass
class AppSettings:
    scan_interval_seconds: int = 300
    debounce_ms: int = 1000
    claude_base_path: str = field(default_factory=_default_claude_base)

    ui_refresh_max_hz: float = 1.0
    default_period: str = "all"
    theme: str = "dark"

    start_with_windows: bool = False
    log_level: str = "INFO"

    # Auto-detection: if True, scan system for AI tools on startup
    auto_detect_providers: bool = True

    # Manual provider paths: slug -> log_path
    # These override auto-detected paths or add providers that can't be auto-detected
    manual_provider_paths: dict[str, str] = field(default_factory=dict)

    # Providers explicitly disabled by user (won't load even if detected)
    disabled_providers: list[str] = field(default_factory=list)

    excluded_paths: list[str] = field(default_factory=list)
    monitored_paths: list[str] = field(default_factory=list)

    comparison_models: list[str] = field(default_factory=list)

    def save(self) -> None:
        SETTINGS_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls) -> AppSettings:
        if SETTINGS_PATH.exists():
            try:
                data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception:
                pass
        return cls()
