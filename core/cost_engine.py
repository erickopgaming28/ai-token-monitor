from __future__ import annotations

from dataclasses import dataclass

from db.database import Database


@dataclass
class CostBreakdown:
    input_cost: float
    output_cost: float
    cache_read_cost: float
    cache_write_cost: float
    total_cost: float
    model_slug: str
    currency: str = "USD"


class CostEngine:
    def __init__(self, db: Database):
        self.db = db
        self._cache: dict[str, dict[str, float]] = {}
        self.reload()

    def reload(self) -> None:
        rows = self.db.get_current_pricing()
        self._cache = {
            r["slug"]: {
                "input": r["input_rate_per_million"],
                "output": r["output_rate_per_million"],
                "cache_read": r["cache_read_rate_per_million"],
                "cache_write": r["cache_write_rate_per_million"],
            }
            for r in rows
        }

    def calculate(
        self,
        model_slug: str,
        input_tokens: int,
        output_tokens: int,
        cache_read: int = 0,
        cache_write: int = 0,
    ) -> CostBreakdown:
        rates = self._cache.get(model_slug)
        if not rates:
            return CostBreakdown(0, 0, 0, 0, 0, model_slug)

        ic = input_tokens * rates["input"] / 1_000_000
        oc = output_tokens * rates["output"] / 1_000_000
        crc = cache_read * rates["cache_read"] / 1_000_000
        cwc = cache_write * rates["cache_write"] / 1_000_000

        return CostBreakdown(
            input_cost=ic,
            output_cost=oc,
            cache_read_cost=crc,
            cache_write_cost=cwc,
            total_cost=ic + oc + crc + cwc,
            model_slug=model_slug,
        )

    def get_model_rates(self, model_slug: str) -> dict[str, float] | None:
        return self._cache.get(model_slug)
