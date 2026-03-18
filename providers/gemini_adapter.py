from __future__ import annotations

from providers.base import ProviderAdapter, TokenEvent


class GeminiAdapter(ProviderAdapter):
    """Placeholder adapter for future Gemini CLI/tool integration."""

    def get_provider_slug(self) -> str:
        return "gemini"

    def get_provider_name(self) -> str:
        return "Gemini"

    def discover_files(self) -> list[str]:
        return []

    def parse_file(self, file_path: str, byte_offset: int) -> tuple[list[TokenEvent], int]:
        return [], byte_offset
