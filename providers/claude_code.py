from __future__ import annotations

import json
import logging
from pathlib import Path

from providers.base import ProviderAdapter, TokenEvent

logger = logging.getLogger(__name__)


class ClaudeCodeAdapter(ProviderAdapter):
    def __init__(self, base_path: str | None = None):
        self._base = Path(base_path) if base_path else Path.home() / ".claude" / "projects"

    def get_provider_slug(self) -> str:
        return "claude_code"

    def get_provider_name(self) -> str:
        return "Claude Code"

    def discover_files(self) -> list[str]:
        files: list[str] = []
        if not self._base.exists():
            return files
        for project_dir in self._base.iterdir():
            if not project_dir.is_dir():
                continue
            for f in project_dir.glob("*.jsonl"):
                files.append(str(f))
            for session_dir in project_dir.iterdir():
                if session_dir.is_dir():
                    subagents = session_dir / "subagents"
                    if subagents.exists():
                        for f in subagents.glob("*.jsonl"):
                            files.append(str(f))
        return files

    def parse_file(self, file_path: str, byte_offset: int) -> tuple[list[TokenEvent], int]:
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

        is_subagent = "subagents" in fp.parts
        agent_id = self._extract_agent_id(fp) if is_subagent else None

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

                    if entry.get("type") != "assistant":
                        continue

                    message = entry.get("message")
                    if not message or not isinstance(message, dict):
                        continue

                    if message.get("stop_reason") is None:
                        continue

                    usage = message.get("usage")
                    if not usage:
                        continue

                    msg_id = message.get("id", "")
                    if not msg_id:
                        continue

                    cwd = entry.get("cwd", "")
                    if not cwd:
                        continue

                    cwd = cwd.replace("\\", "/")

                    events.append(
                        TokenEvent(
                            message_id=msg_id,
                            model_slug=message.get("model", "unknown"),
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0),
                            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                            cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
                            timestamp=entry.get("timestamp", ""),
                            session_id=entry.get("sessionId", ""),
                            project_path=cwd,
                            source_file=file_path,
                            source_line=line_num,
                            data_quality="exact",
                            is_subagent=is_subagent,
                            agent_id=agent_id,
                        )
                    )

                new_offset = f.tell()
        except (OSError, PermissionError) as e:
            logger.warning("Cannot read %s: %s", file_path, e)
            return events, byte_offset

        return events, new_offset

    @staticmethod
    def _extract_agent_id(fp: Path) -> str | None:
        name = fp.stem
        if name.startswith("agent-"):
            return name[6:]
        return name
