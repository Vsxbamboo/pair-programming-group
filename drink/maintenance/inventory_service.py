"""库存正式实现。负责人：C。

构造参数是约定的一部分（wiring.py 按此创建），不要改。
验收标准是 tests/contract/test_inventory.py。

实现要点（见 docs/03-详细设计.md §6）：
- 库存数量只通过 Repository 改，且一次调用内“全部成功或全部不扣”；
- 补货先校验数量、操作人、容量，再改库存并写补货记录；
- 库存状态（OK / LOW / EMPTY）由 StockLevel.status 现算，不落库。
"""
from __future__ import annotations

from drink.model import Clock, DrinkError, ErrorCode, Repository

from .interfaces import InventoryService


class InventoryServiceImpl(InventoryService):

    def __init__(self, repo: Repository, clock: Clock):
        self.repo = repo
        self.clock = clock

    def list_stock(self):
        return self.repo.list_stock()

    def check(self, consumption):
        stock = {level.material.id: level.quantity for level in self.repo.list_stock()}
        return sorted(material_id for material_id, need in consumption.items()
                      if stock.get(material_id, 0) < need)

    def consume(self, consumption, order_id):
        # order_id 用于出问题时排查；扣减本身由 Repository 保证原子性。
        deltas = {material_id: -quantity for material_id, quantity in consumption.items()
                  if quantity}
        self.repo.apply_stock_changes(deltas)

    def restock(self, material_id, quantity, operator):
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            raise DrinkError(ErrorCode.INVALID_ARGUMENT, "补货数量必须是正整数")
        if not isinstance(operator, str) or not operator.strip():
            raise DrinkError(ErrorCode.INVALID_ARGUMENT, "请填写操作人")

        current = self.repo.get_stock(material_id)
        room = current.material.capacity - current.quantity
        if quantity > room:
            raise DrinkError(ErrorCode.INVALID_ARGUMENT,
                             f"超过料仓容量，最多还能补 {room}{current.material.unit}")

        self.repo.apply_stock_changes({material_id: quantity})
        self.repo.add_restock(material_id, quantity, operator.strip(), self.clock.now_ms())
        return self.repo.get_stock(material_id)

    def list_restocks(self, limit=50):
        return self.repo.list_restocks(limit)
