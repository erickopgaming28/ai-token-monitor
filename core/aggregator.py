from __future__ import annotations

from db.database import Database
from core.cost_engine import CostEngine


class Aggregator:
    def __init__(self, db: Database, cost_engine: CostEngine):
        self.db = db
        self.cost_engine = cost_engine

    def rebuild(self, project_ids: list[int] | None = None) -> None:
        self.db.rebuild_daily_aggregates(project_ids)

    def get_all_projects(self, period: str = "all") -> list[dict]:
        return self.db.get_all_projects_summary(period)

    def get_project_detail(self, project_id: int, period: str = "all") -> dict:
        return self.db.get_project_detail(project_id, period)

    def get_global_cost(self, period: str = "all") -> float:
        return self.db.get_global_cost(period)
