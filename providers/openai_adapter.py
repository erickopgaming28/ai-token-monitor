"""OpenAI Codex CLI adapter.

Codex CLI stores session logs as JSONL in ~/.codex/sessions/.
Each line is a JSON object with role, content, and usage metadata.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from providers.base import ProviderAdapter, TokenEvent

logger = logging.getLogger(__name__)


class OpenAIAdapter(ProviderAdapter):
    def __init__(self, base_path: str | None = None):
        if base_path:
            self._base = Path(base_path)
        else:
            codex_sessions = Path.home() / ".codex" / "sessions"
            codex_root = Path.home() / ".codex"
            self._base = codex_sessions if codex_sessions.exists() else codex_root

    def get_provider_slug(self) -> str:
        return "openai"

    def get_provider_name(self) -> str:
        return "OpenAI"

    def discover_files(self) -> list[str]:
        files: list[str] = []
        if not self._base.exists():
            return files
        # Look for JSONL files in sessions dir and root
        for pattern in ["*.jsonl", "**/*.jsonl"]:
            for f in self._base.glob(pattern):
                if str(f) not in files:
                    files.append(str(f))
        return files

    def parse_file(self, file_path: str, byte_offset: int) -> tuple[list[TokenEvent], int]:
        """Parse Codex CLI JSONL log files.

        Codex CLI logs follow OpenAI's chat completion format.
        We look for response entries with usage data containing:
        - prompt_tokens / completion_tokens (standard OpenAI)
        - input_tokens / output_tokens (newer format)
        """
        events: list[TokenEvent] = []
        fp = Path(file_path)

        try:
            file_size = fp.stat().st_size
        except OSError:
            return events, byte_offset

        if file_size < byte_offset:
            byte_offset = 0
        if file_size == byte_offset:
            return events, byte_offset

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                f.seek(byte_offset)
                line_num = 0
                for line in f:
                    line_num += 1
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    event = self._try_parse_entry(entry, file_path, line_num)
                    if event:
                        events.append(event)

                new_offset = f.tell()
        except (OSError, PermissionError) as e:
            logger.warning("Cannot read %s: %s", file_path, e)
            return events, byte_offset

        return events, new_offset

    def _try_parse_entry(self, entry: dict, file_path: str, line_num: int) -> TokenEvent | None:
        """Try to extract token usage from a log entry."""
        # Format 1: OpenAI API response with usage field
        usage = entry.get("usage")
        if not usage:
            # Check nested in response/message
            response = entry.get("response") or entry.get("message") or {}
            usage = response.get("usage")

        if not usage:
            return None

        # Standard OpenAI fields
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens", 0)
        output_tokens = usage.get("completion_tokens") or usage.get("output_tokens", 0)
        cache_read = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0) if isinstance(usage.get("prompt_tokens_details"), dict) else 0

        if input_tokens == 0 and output_tokens == 0:
            return None

        # Extract model
        model = entry.get("model") or entry.get("response", {}).get("model", "unknown")

        # Extract message ID
        msg_id = entry.get("id") or entry.get("response", {}).get("id", "")
        if not msg_id:
            msg_id = f"openai-{file_path}-{line_num}"

        # Extract project path (cwd)
        cwd = entry.get("cwd") or entry.get("working_directory", "")
        if not cwd:
            # Try to infer from file path structure
            cwd = str(Path(file_path).parent)
        cwd = cwd.replace("\\", "/")

        # Session ID
        session_id = entry.get("session_id") or entry.get("sessionId") or Path(file_path).stem

        # Timestamp
        timestamp = entry.get("timestamp") or entry.get("created", "")
        if isinstance(timestamp, (int, float)):
            from datetime import datetime, timezone
            timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()

        return TokenEvent(
            message_id=msg_id,
            model_slug=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=0,
            timestamp=str(timestamp),
            session_id=session_id,
            project_path=cwd,
            source_file=file_path,
            source_line=line_num,
            data_quality="exact",
        )
