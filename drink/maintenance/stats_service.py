"""销售统计正式实现。负责人：C。

构造参数是约定的一部分（wiring.py 按此创建），不要改。
验收标准是 tests/contract/test_stats.py。
"""
from __future__ import annotations

from drink.model import Clock, Repository

from .interfaces import StatsService


class StatsServiceImpl(StatsService):

    def __init__(self, repo: Repository, clock: Clock):
        self.repo = repo
        self.clock = clock

    def summary(self, machine_id=None, since_ms=None, until_ms=None):
        raise NotImplementedError  # TODO(C)

    def top_recipes(self, limit=3):
        raise NotImplementedError  # TODO(C)
