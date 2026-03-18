from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class TokenEvent:
    message_id: str
    model_slug: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    timestamp: str
    session_id: str
    project_path: str
    source_file: str
    source_line: int = 0
    data_quality: str = "exact"
    is_subagent: bool = False
    agent_id: Optional[str] = None


class ProviderAdapter(ABC):
    @abstractmethod
    def get_provider_slug(self) -> str: ...

    @abstractmethod
    def get_provider_name(self) -> str: ...

    @abstractmethod
    def discover_files(self) -> list[str]: ...

    @abstractmethod
    def parse_file(self, file_path: str, byte_offset: int) -> tuple[list[TokenEvent], int]: ...
