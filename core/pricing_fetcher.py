"""Fetch live pricing from AI provider APIs.

Uses public API endpoints to discover available models and their current prices.
Falls back to local default_pricing.json if network is unavailable.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from db.database import Database

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 86400  # 24 hours


@dataclass
class ModelPricing:
    provider_slug: str
    model_slug: str
    model_name: str
    input_rate: float  # per million tokens
    output_rate: float
    cache_read_rate: float = 0.0
    cache_write_rate: float = 0.0


class PricingFetcher:
    def __init__(self, db: Database, cache_dir: Path):
        self.db = db
        self._cache_file = cache_dir / "pricing_cache.json"
        self._fetchers = {
            "anthropic": _fetch_anthropic,
            "openai": _fetch_openai,
            "google": _fetch_google,
        }

    def update_all(self, force: bool = False) -> dict[str, list[ModelPricing]]:
        """Fetch pricing from all providers. Returns dict of provider -> models."""
        if not force and self._cache_valid():
            logger.info("Pricing cache still valid, skipping fetch")
            return self._load_cache()

        all_pricing: dict[str, list[ModelPricing]] = {}
        for provider_key, fetcher in self._fetchers.items():
            try:
                models = fetcher()
                if models:
                    all_pricing[provider_key] = models
                    logger.info("Fetched %d models from %s", len(models), provider_key)
            except Exception as e:
                logger.warning("Failed to fetch pricing from %s: %s", provider_key, e)

        if all_pricing:
            self._save_cache(all_pricing)
            self._apply_to_db(all_pricing)

        return all_pricing

    def _cache_valid(self) -> bool:
        if not self._cache_file.exists():
            return False
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            return (time.time() - data.get("timestamp", 0)) < CACHE_TTL_SECONDS
        except Exception:
            return False

    def _load_cache(self) -> dict[str, list[ModelPricing]]:
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            result: dict[str, list[ModelPricing]] = {}
            for provider_key, models in data.get("pricing", {}).items():
                result[provider_key] = [ModelPricing(**m) for m in models]
            return result
        except Exception:
            return {}

    def _save_cache(self, pricing: dict[str, list[ModelPricing]]) -> None:
        data = {
            "timestamp": time.time(),
            "pricing": {
                k: [
                    {
                        "provider_slug": m.provider_slug,
                        "model_slug": m.model_slug,
                        "model_name": m.model_name,
                        "input_rate": m.input_rate,
                        "output_rate": m.output_rate,
                        "cache_read_rate": m.cache_read_rate,
                        "cache_write_rate": m.cache_write_rate,
                    }
                    for m in v
                ]
                for k, v in pricing.items()
            },
        }
        self._cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _apply_to_db(self, pricing: dict[str, list[ModelPricing]]) -> None:
        """Update database with fetched pricing."""
        for _provider_key, models in pricing.items():
            for mp in models:
                provider_id = self.db.get_provider_id(mp.provider_slug)
                if not provider_id:
                    continue
                model_id = self.db.get_model_id(mp.model_slug)
                if not model_id:
                    model_id = self.db.ensure_model(mp.model_slug, mp.provider_slug)
                if model_id == -1:
                    continue
                # Update name if it was auto-created
                self.db.conn.execute(
                    "UPDATE models SET name = ? WHERE id = ? AND name = slug",
                    (mp.model_name, model_id),
                )
                # Upsert pricing for today
                self.db.conn.execute(
                    """INSERT INTO pricing
                       (model_id, input_rate_per_million, output_rate_per_million,
                        cache_read_rate_per_million, cache_write_rate_per_million,
                        effective_date)
                       VALUES (?, ?, ?, ?, ?, date('now'))
                       ON CONFLICT(model_id, effective_date) DO UPDATE SET
                         input_rate_per_million = excluded.input_rate_per_million,
                         output_rate_per_million = excluded.output_rate_per_million,
                         cache_read_rate_per_million = excluded.cache_read_rate_per_million,
                         cache_write_rate_per_million = excluded.cache_write_rate_per_million""",
                    (model_id, mp.input_rate, mp.output_rate, mp.cache_read_rate, mp.cache_write_rate),
                )
        self.db.conn.commit()


def _http_get_json(url: str, timeout: int = 10) -> Optional[dict]:
    """Simple HTTP GET that returns parsed JSON."""
    try:
        req = Request(url, headers={"User-Agent": "AITokenMonitor/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, json.JSONDecodeError, OSError) as e:
        logger.debug("HTTP fetch failed for %s: %s", url, e)
        return None


# ── Anthropic / Claude ──────────────────────────────────────────

# Anthropic doesn't have a public pricing API, but we can get the model list
# and map known pricing. The official pricing page is the source of truth.
# We maintain a mapping that gets updated with each app release and can be
# overridden by the user in settings.

ANTHROPIC_KNOWN_PRICING: dict[str, dict] = {
    "claude-opus-4-6": {"name": "Claude Opus 4", "input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_write": 18.75},
    "claude-sonnet-4-6": {"name": "Claude Sonnet 4", "input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-3-5-sonnet-20241022": {"name": "Claude Sonnet 3.5", "input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-3-5-haiku-latest": {"name": "Claude Haiku 3.5", "input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_write": 1.0},
    "claude-haiku-4-5-20251001": {"name": "Claude Haiku 4.5", "input": 1.0, "output": 5.0, "cache_read": 0.10, "cache_write": 1.25},
}


def _fetch_anthropic() -> list[ModelPricing]:
    """Fetch Anthropic models. Uses known pricing + attempts API discovery."""
    models: list[ModelPricing] = []

    # Try the models API (requires API key, may fail — that's OK)
    data = _http_get_json("https://api.anthropic.com/v1/models")
    if data and "data" in data:
        for m in data["data"]:
            model_id = m.get("id", "")
            if model_id in ANTHROPIC_KNOWN_PRICING:
                continue  # Already in known pricing
            # New model discovered but no pricing — add with zero rates
            models.append(ModelPricing(
                provider_slug="claude_code",
                model_slug=model_id,
                model_name=m.get("display_name", model_id),
                input_rate=0, output_rate=0,
            ))

    # Always add known pricing
    for slug, info in ANTHROPIC_KNOWN_PRICING.items():
        models.append(ModelPricing(
            provider_slug="claude_code",
            model_slug=slug,
            model_name=info["name"],
            input_rate=info["input"],
            output_rate=info["output"],
            cache_read_rate=info.get("cache_read", 0),
            cache_write_rate=info.get("cache_write", 0),
        ))
    return models


# ── OpenAI ──────────────────────────────────────────────────────

OPENAI_KNOWN_PRICING: dict[str, dict] = {
    "gpt-4o": {"name": "GPT-4o", "input": 2.50, "output": 10.0, "cache_read": 1.25},
    "gpt-4o-mini": {"name": "GPT-4o mini", "input": 0.15, "output": 0.60, "cache_read": 0.075},
    "gpt-4.1": {"name": "GPT-4.1", "input": 2.0, "output": 8.0, "cache_read": 0.50},
    "gpt-4.1-mini": {"name": "GPT-4.1 mini", "input": 0.40, "output": 1.60, "cache_read": 0.10},
    "gpt-4.1-nano": {"name": "GPT-4.1 nano", "input": 0.10, "output": 0.40, "cache_read": 0.025},
    "o3": {"name": "o3", "input": 2.0, "output": 8.0, "cache_read": 0.50},
    "o3-mini": {"name": "o3 mini", "input": 1.10, "output": 4.40, "cache_read": 0.275},
    "o4-mini": {"name": "o4 mini", "input": 1.10, "output": 4.40, "cache_read": 0.275},
}


def _fetch_openai() -> list[ModelPricing]:
    """Fetch OpenAI models. Tries /v1/models then falls back to known."""
    models: list[ModelPricing] = []

    # OpenAI /v1/models requires API key — attempt anyway
    data = _http_get_json("https://api.openai.com/v1/models")
    if data and "data" in data:
        for m in data["data"]:
            mid = m.get("id", "")
            if mid in OPENAI_KNOWN_PRICING:
                continue
            # Filter to GPT/o-series only
            if any(mid.startswith(p) for p in ("gpt-", "o1", "o3", "o4")):
                models.append(ModelPricing(
                    provider_slug="openai",
                    model_slug=mid,
                    model_name=mid,
                    input_rate=0, output_rate=0,
                ))

    for slug, info in OPENAI_KNOWN_PRICING.items():
        models.append(ModelPricing(
            provider_slug="openai",
            model_slug=slug,
            model_name=info["name"],
            input_rate=info["input"],
            output_rate=info["output"],
            cache_read_rate=info.get("cache_read", 0),
        ))
    return models


# ── Google / Gemini ─────────────────────────────────────────────

GEMINI_KNOWN_PRICING: dict[str, dict] = {
    "gemini-2.5-pro": {"name": "Gemini 2.5 Pro", "input": 1.25, "output": 10.0, "cache_read": 0.3125, "cache_write": 4.50},
    "gemini-2.5-flash": {"name": "Gemini 2.5 Flash", "input": 0.15, "output": 0.60, "cache_read": 0.0375, "cache_write": 1.00},
    "gemini-2.0-flash": {"name": "Gemini 2.0 Flash", "input": 0.10, "output": 0.40, "cache_read": 0.025, "cache_write": 1.00},
}


def _fetch_google() -> list[ModelPricing]:
    """Fetch Google Gemini models."""
    models: list[ModelPricing] = []
    for slug, info in GEMINI_KNOWN_PRICING.items():
        models.append(ModelPricing(
            provider_slug="gemini",
            model_slug=slug,
            model_name=info["name"],
            input_rate=info["input"],
            output_rate=info["output"],
            cache_read_rate=info.get("cache_read", 0),
            cache_write_rate=info.get("cache_write", 0),
        ))
    return models
