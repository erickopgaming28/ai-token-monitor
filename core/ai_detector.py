"""Auto-detect AI tools installed on the system.

Scans for CLI tools, log directories, and config files to determine
which AI providers are actually available on this machine.
Returns log_path only when real log files exist.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
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
    has_logs: bool = False


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
                logger.info(
                    "Detected: %s (%s) logs=%s",
                    result.tool_name, result.detection_method,
                    result.log_path or "none",
                )
        except Exception as e:
            logger.debug("Detector %s failed: %s", detector.__name__, e)
    return found


def _run_version(cmd: list[str]) -> str | None:
    """Try to get version output from a CLI command."""
    try:
        kwargs = {"capture_output": True, "text": True, "timeout": 5}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(cmd, **kwargs)
        if result.returncode == 0:
            return result.stdout.strip()[:200]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _has_files(directory: Path, pattern: str) -> bool:
    """Check if directory contains files matching pattern (non-recursive quick check)."""
    if not directory.exists():
        return False
    try:
        return any(True for _ in directory.glob(pattern))
    except (OSError, PermissionError):
        return False


def _has_files_recursive(directory: Path, pattern: str, max_depth: int = 3) -> bool:
    """Check if directory tree contains files matching pattern."""
    if not directory.exists():
        return False
    try:
        # Use rglob but limit depth via parts count
        base_depth = len(directory.parts)
        for p in directory.rglob(pattern):
            if len(p.parts) - base_depth <= max_depth:
                return True
    except (OSError, PermissionError):
        pass
    return False


# ── Claude Code ──────────────────────────────────────────────────

def _detect_claude_code() -> DetectedTool | None:
    home = Path.home()
    claude_dir = home / ".claude"
    projects_dir = claude_dir / "projects"

    claude_bin = shutil.which("claude")
    version = None
    if claude_bin:
        version = _run_version(["claude", "--version"])

    has_logs = _has_files_recursive(projects_dir, "*.jsonl")

    if has_logs:
        return DetectedTool(
            provider_slug="claude_code",
            provider_name="Claude Code",
            tool_name="Claude Code CLI",
            version=version,
            log_path=str(projects_dir),
            config_path=str(claude_dir / "settings.json") if (claude_dir / "settings.json").exists() else None,
            detection_method="cli+logs" if claude_bin else "logs_only",
            has_logs=True,
        )
    if claude_bin:
        return DetectedTool(
            provider_slug="claude_code",
            provider_name="Claude Code",
            tool_name="Claude Code CLI",
            version=version,
            log_path=str(projects_dir),
            detection_method="cli_only",
            has_logs=False,
        )
    return None


# ── OpenAI / Codex CLI ───────────────────────────────────────────

def _detect_openai_codex() -> DetectedTool | None:
    home = Path.home()
    codex_bin = shutil.which("codex")
    openai_bin = shutil.which("openai") if not codex_bin else None

    # Codex CLI stores logs in ~/.codex/
    # Structure: ~/.codex/sessions/<session_id>.jsonl
    codex_dir = home / ".codex"
    codex_sessions = codex_dir / "sessions"

    # Also check for OpenAI CLI config
    if sys.platform == "win32":
        openai_config = home / ".openai"
    else:
        openai_config = home / ".config" / "openai"

    version = None
    if codex_bin:
        version = _run_version(["codex", "--version"])
    elif openai_bin:
        version = _run_version(["openai", "--version"])

    # Check for actual log files
    has_logs = _has_files(codex_sessions, "*.jsonl") or _has_files(codex_dir, "*.jsonl")

    log_path = None
    if has_logs:
        log_path = str(codex_sessions) if codex_sessions.exists() else str(codex_dir)
    elif codex_dir.exists():
        log_path = str(codex_dir)

    config_path = None
    if codex_dir.exists():
        config_path = str(codex_dir)
    elif openai_config.exists():
        config_path = str(openai_config)

    if codex_bin or openai_bin or codex_dir.exists():
        return DetectedTool(
            provider_slug="openai",
            provider_name="OpenAI",
            tool_name="Codex CLI" if codex_bin else "OpenAI CLI",
            version=version,
            log_path=log_path,
            config_path=config_path,
            detection_method="cli+logs" if (codex_bin and has_logs) else "cli" if codex_bin else "config_dir",
            has_logs=has_logs,
        )
    return None


# ── Gemini CLI ───────────────────────────────────────────────────

def _detect_gemini_cli() -> DetectedTool | None:
    home = Path.home()
    gemini_bin = shutil.which("gemini")

    # Gemini CLI stores logs/sessions in ~/.gemini/
    gemini_dir = home / ".gemini"

    # Check multiple possible log locations
    log_candidates = [
        gemini_dir / "sessions",
        gemini_dir / "logs",
        gemini_dir,
    ]

    version = None
    if gemini_bin:
        version = _run_version(["gemini", "--version"])

    has_logs = False
    log_path = None
    for candidate in log_candidates:
        if _has_files(candidate, "*.jsonl") or _has_files(candidate, "*.json"):
            has_logs = True
            log_path = str(candidate)
            break

    if not log_path and gemini_dir.exists():
        log_path = str(gemini_dir)

    if gemini_bin or gemini_dir.exists():
        return DetectedTool(
            provider_slug="gemini",
            provider_name="Gemini",
            tool_name="Gemini CLI",
            version=version,
            log_path=log_path,
            config_path=str(gemini_dir) if gemini_dir.exists() else None,
            detection_method="cli+logs" if (gemini_bin and has_logs) else "cli" if gemini_bin else "config_dir",
            has_logs=has_logs,
        )
    return None


# ── GitHub Copilot ───────────────────────────────────────────────

def _detect_github_copilot() -> DetectedTool | None:
    gh_bin = shutil.which("gh")
    if not gh_bin:
        return None
    result = _run_version(["gh", "extension", "list"])
    if result and "copilot" in result.lower():
        return DetectedTool(
            provider_slug="github_copilot",
            provider_name="GitHub Copilot",
            tool_name="GitHub Copilot CLI",
            detection_method="gh_extension",
            has_logs=False,
        )
    return None


# ── Cursor ───────────────────────────────────────────────────────

def _detect_cursor() -> DetectedTool | None:
    cursor_bin = shutil.which("cursor")
    home = Path.home()

    if sys.platform == "win32":
        cursor_dir = home / "AppData" / "Roaming" / "Cursor"
    elif sys.platform == "darwin":
        cursor_dir = home / "Library" / "Application Support" / "Cursor"
    else:
        cursor_dir = home / ".config" / "Cursor"

    # Cursor uses ~/.cursor/ for some session data
    cursor_dot = home / ".cursor"

    has_logs = False
    log_path = None

    # Check for usage/session logs
    for candidate in [cursor_dot, cursor_dir / "logs", cursor_dir]:
        if _has_files_recursive(candidate, "*.jsonl") or _has_files_recursive(candidate, "*.log"):
            has_logs = True
            log_path = str(candidate)
            break

    if cursor_bin or cursor_dir.exists() or cursor_dot.exists():
        return DetectedTool(
            provider_slug="cursor",
            provider_name="Cursor",
            tool_name="Cursor IDE",
            log_path=log_path,
            config_path=str(cursor_dir) if cursor_dir.exists() else None,
            detection_method="cli+logs" if (cursor_bin and has_logs) else "cli" if cursor_bin else "config_dir",
            has_logs=has_logs,
        )
    return None


# ── Aider ────────────────────────────────────────────────────────

def _detect_aider() -> DetectedTool | None:
    aider_bin = shutil.which("aider")
    home = Path.home()

    # Aider stores logs in ~/.aider/logs/ or ~/.aider.logs/
    aider_dir = home / ".aider"
    aider_logs = aider_dir / "logs"
    aider_alt_logs = home / ".aider.logs"

    version = None
    if aider_bin:
        version = _run_version(["aider", "--version"])

    has_logs = False
    log_path = None

    for candidate in [aider_logs, aider_alt_logs, aider_dir]:
        if candidate.exists() and (_has_files(candidate, "*.log") or _has_files(candidate, "*.jsonl") or _has_files(candidate, "*.md")):
            has_logs = True
            log_path = str(candidate)
            break

    if aider_bin or aider_dir.exists():
        return DetectedTool(
            provider_slug="aider",
            provider_name="Aider",
            tool_name="Aider CLI",
            version=version,
            log_path=log_path,
            config_path=str(aider_dir) if aider_dir.exists() else None,
            detection_method="cli+logs" if (aider_bin and has_logs) else "cli" if aider_bin else "config_dir",
            has_logs=has_logs,
        )
    return None


# ── Continue (VS Code extension) ────────────────────────────────

def _detect_continue_dev() -> DetectedTool | None:
    home = Path.home()
    continue_dir = home / ".continue"

    if not continue_dir.exists():
        return None

    # Continue stores session data in ~/.continue/sessions/
    sessions_dir = continue_dir / "sessions"
    has_logs = _has_files_recursive(sessions_dir, "*.json") if sessions_dir.exists() else False
    log_path = str(sessions_dir) if has_logs else None

    return DetectedTool(
        provider_slug="continue_dev",
        provider_name="Continue",
        tool_name="Continue (VS Code)",
        log_path=log_path,
        config_path=str(continue_dir),
        detection_method="config+logs" if has_logs else "config_dir",
        has_logs=has_logs,
    )
