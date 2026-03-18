"""Gemini CLI adapter.

Gemini CLI stores session data in ~/.gemini/.
Parses JSON/JSONL log files for token usage metadata.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from providers.base import ProviderAdapter, TokenEvent

logger = logging.getLogger(__name__)


class GeminiAdapter(ProviderAdapter):
    def __init__(self, base_path: str | None = None):
        if base_path:
            self._base = Path(base_path)
        else:
            gemini_dir = Path.home() / ".gemini"
            sessions = gemini_dir / "sessions"
            self._base = sessions if sessions.exists() else gemini_dir

    def get_provider_slug(self) -> str:
        return "gemini"

    def get_provider_name(self) -> str:
        return "Gemini"

    def discover_files(self) -> list[str]:
        files: list[str] = []
        if not self._base.exists():
            return files
        for pattern in ["*.jsonl", "*.json", "**/*.jsonl"]:
            for f in self._base.glob(pattern):
                # Skip config files
                if f.name in ("config.json", "settings.json"):
                    continue
                if str(f) not in files:
                    files.append(str(f))
        return files

    def parse_file(self, file_path: str, byte_offset: int) -> tuple[list[TokenEvent], int]:
        """Parse Gemini CLI log files.

        Gemini API responses include usageMetadata with:
        - promptTokenCount
        - candidatesTokenCount
        - cachedContentTokenCount
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
        """Try to extract token usage from a Gemini log entry."""
        # Gemini API format: usageMetadata at top level or nested in response
        usage = entry.get("usageMetadata")
        if not usage:
            response = entry.get("response") or {}
            usage = response.get("usageMetadata")
        if not usage:
            # Also check for candidates[0].usageMetadata
            candidates = entry.get("candidates") or entry.get("response", {}).get("candidates") or []
            if candidates and isinstance(candidates, list):
                usage = candidates[0].get("usageMetadata") if isinstance(candidates[0], dict) else None

        if not usage:
            return None

        # Gemini uses different field names
        input_tokens = usage.get("promptTokenCount", 0)
        output_tokens = usage.get("candidatesTokenCount", 0) or usage.get("totalTokenCount", 0) - input_tokens
        cache_read = usage.get("cachedContentTokenCount", 0)

        if input_tokens == 0 and output_tokens == 0:
            return None

        # Model
        model = entry.get("model") or entry.get("modelVersion", "unknown")
        # Clean up model name: models/gemini-2.5-pro -> gemini-2.5-pro
        if isinstance(model, str) and model.startswith("models/"):
            model = model[7:]

        # Message ID
        msg_id = entry.get("id") or entry.get("responseId", "")
        if not msg_id:
            msg_id = f"gemini-{file_path}-{line_num}"

        # Project path
        cwd = entry.get("cwd") or entry.get("working_directory", "")
        if not cwd:
            cwd = str(Path(file_path).parent)
        cwd = cwd.replace("\\", "/")

        # Session
        session_id = entry.get("session_id") or entry.get("sessionId") or Path(file_path).stem

        # Timestamp
        timestamp = entry.get("timestamp") or entry.get("createTime", "")
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
