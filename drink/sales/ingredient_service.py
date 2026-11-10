"""食材端正式实现。负责人：B。

构造参数是约定的一部分（wiring.py 按此创建），不要改。
行为约定见 interfaces.IngredientService 的文档字符串；验收标准是 tests/contract/test_ingredient.py。
"""
from __future__ import annotations

from drink.maintenance.interfaces import InventoryService, StatsService
from drink.model import Repository

from .interfaces import IngredientService


class IngredientServiceImpl(IngredientService):

    def __init__(self, repo: Repository, inventory: InventoryService, stats: StatsService):
        self.repo = repo
        self.inventory = inventory
        self.stats = stats

    def get_menu(self):
        raise NotImplementedError  # TODO(B)

    def validate(self, recipe):
        raise NotImplementedError  # TODO(B)

    def quote(self, recipe):
        raise NotImplementedError  # TODO(B)

    def consumption_of(self, recipe):
        raise NotImplementedError  # TODO(B)

    def recommend(self, limit=3):
        raise NotImplementedError  # TODO(B)
