"""库存正式实现。负责人：C。

构造参数是约定的一部分（wiring.py 按此创建），不要改。
验收标准是 tests/contract/test_inventory.py。
"""
from __future__ import annotations

from drink.model import Clock, Repository

from .interfaces import InventoryService


class InventoryServiceImpl(InventoryService):

    def __init__(self, repo: Repository, clock: Clock):
        self.repo = repo
        self.clock = clock

    def list_stock(self):
        raise NotImplementedError  # TODO(C)

    def check(self, consumption):
        raise NotImplementedError  # TODO(C)

    def consume(self, consumption, order_id):
        raise NotImplementedError  # TODO(C)

    def restock(self, material_id, quantity, operator):
        raise NotImplementedError  # TODO(C)

    def list_restocks(self, limit=50):
        raise NotImplementedError  # TODO(C)
