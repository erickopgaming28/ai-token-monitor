"""Auto-detect AI tools installed on the system.

Scans for CLI tools, log directories, and config files to determine
which AI providers are actually available on this machine.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DetectedTool:
    provider_slug: str
    provider_name: str
    tool_name: str
    version: str | None = None
    log_path: str | None = None
    config_path: str | None = None
    detection_method: str = ""


def detect_all() -> list[DetectedTool]:
    """Run all detectors and return found tools."""
    detectors = [
        _detect_claude_code,
        _detect_openai_codex,
        _detect_gemini_cli,
        _detect_github_copilot,
        _detect_cursor,
        _detect_aider,
        _detect_continue_dev,
    ]
    found: list[DetectedTool] = []
    for detector in detectors:
        try:
            result = detector()
            if result:
                found.append(result)
                logger.info("Detected: %s (%s)", result.tool_name, result.detection_method)
        except Exception as e:
            logger.debug("Detector %s failed: %s", detector.__name__, e)
    return found


def _run_version(cmd: list[str]) -> str | None:
    """Try to get version output from a CLI command."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:200]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _detect_claude_code() -> DetectedTool | None:
    home = Path.home()
    claude_dir = home / ".claude"
    projects_dir = claude_dir / "projects"

    # Check if claude CLI is in PATH
    claude_bin = shutil.which("claude")
    version = None
    if claude_bin:
        version = _run_version(["claude", "--version"])

    # Even without CLI, check for log directory
    if projects_dir.exists() and any(projects_dir.iterdir()):
        return DetectedTool(
            provider_slug="claude_code",
            provider_name="Claude Code",
            tool_name="Claude Code CLI",
            version=version,
            log_path=str(projects_dir),
            config_path=str(claude_dir / "settings.json") if (claude_dir / "settings.json").exists() else None,
            detection_method="cli+logs" if claude_bin else "logs_only",
        )
    if claude_bin:
        return DetectedTool(
            provider_slug="claude_code",
            provider_name="Claude Code",
            tool_name="Claude Code CLI",
            version=version,
            detection_method="cli_only",
        )
    return None


def _detect_openai_codex() -> DetectedTool | None:
    codex_bin = shutil.which("codex")
    if not codex_bin:
        # Also check for openai CLI
        codex_bin = shutil.which("openai")

    home = Path.home()
    # Codex CLI stores config in ~/.codex/
    codex_dir = home / ".codex"
    openai_dir = home / ".config" / "openai" if sys.platform != "win32" else home / ".openai"

    version = None
    if codex_bin:
        version = _run_version([codex_bin, "--version"])

    config_path = None
    if codex_dir.exists():
        config_path = str(codex_dir)
    elif openai_dir.exists():
        config_path = str(openai_dir)

    if codex_bin or codex_dir.exists():
        return DetectedTool(
            provider_slug="openai",
            provider_name="OpenAI",
            tool_name="Codex CLI" if shutil.which("codex") else "OpenAI CLI",
            version=version,
            config_path=config_path,
            detection_method="cli" if codex_bin else "config_dir",
        )
    return None


def _detect_gemini_cli() -> DetectedTool | None:
    gemini_bin = shutil.which("gemini")
    if not gemini_bin:
        return None
    version = _run_version(["gemini", "--version"])
    return DetectedTool(
        provider_slug="gemini",
        provider_name="Gemini",
        tool_name="Gemini CLI",
        version=version,
        detection_method="cli",
    )


def _detect_github_copilot() -> DetectedTool | None:
    # Copilot CLI
    gh_bin = shutil.which("gh")
    if not gh_bin:
        return None
    # Check if copilot extension is installed
    result = _run_version(["gh", "extension", "list"])
    if result and "copilot" in result.lower():
        return DetectedTool(
            provider_slug="github_copilot",
            provider_name="GitHub Copilot",
            tool_name="GitHub Copilot CLI",
            detection_method="gh_extension",
        )
    return None


def _detect_cursor() -> DetectedTool | None:
    cursor_bin = shutil.which("cursor")
    home = Path.home()

    # Cursor stores data in different locations per OS
    if sys.platform == "win32":
        cursor_dir = home / "AppData" / "Roaming" / "Cursor"
    elif sys.platform == "darwin":
        cursor_dir = home / "Library" / "Application Support" / "Cursor"
    else:
        cursor_dir = home / ".config" / "Cursor"

    if cursor_bin or cursor_dir.exists():
        return DetectedTool(
            provider_slug="cursor",
            provider_name="Cursor",
            tool_name="Cursor IDE",
            config_path=str(cursor_dir) if cursor_dir.exists() else None,
            detection_method="cli" if cursor_bin else "config_dir",
        )
    return None


def _detect_aider() -> DetectedTool | None:
    aider_bin = shutil.which("aider")
    if not aider_bin:
        return None
    version = _run_version(["aider", "--version"])
    return DetectedTool(
        provider_slug="aider",
        provider_name="Aider",
        tool_name="Aider CLI",
        version=version,
        detection_method="cli",
    )


def _detect_continue_dev() -> DetectedTool | None:
    home = Path.home()
    continue_dir = home / ".continue"
    if continue_dir.exists():
        return DetectedTool(
            provider_slug="continue_dev",
            provider_name="Continue",
            tool_name="Continue (VS Code)",
            config_path=str(continue_dir),
            detection_method="config_dir",
        )
    return None
