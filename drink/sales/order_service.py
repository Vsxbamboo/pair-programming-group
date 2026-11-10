"""销售端正式实现。负责人：B。

构造参数是约定的一部分（wiring.py 按此创建），不要改。
行为约定见 interfaces.OrderService 的文档字符串和 docs/03-详细设计.md 的状态图；
验收标准是 tests/contract/test_order.py。
"""
from __future__ import annotations

from drink.maintenance.interfaces import InventoryService, MachineDriver
from drink.model import Clock, Repository

from .interfaces import IngredientService, OrderService, PaymentGateway


class OrderServiceImpl(OrderService):

    def __init__(self, machine_id: str, repo: Repository, ingredient: IngredientService,
                 inventory: InventoryService, machine: MachineDriver, payment: PaymentGateway,
                 clock: Clock):
        self.machine_id = machine_id
        self.repo = repo
        self.ingredient = ingredient
        self.inventory = inventory
        self.machine = machine
        self.payment = payment
        self.clock = clock

    def create_order(self, recipe):
        raise NotImplementedError  # TODO(B)

    def get_order(self, order_id):
        raise NotImplementedError  # TODO(B)

    def cancel_order(self, order_id):
        raise NotImplementedError  # TODO(B)

    def list_orders(self, status=None, limit=50):
        raise NotImplementedError  # TODO(B)

    def refund_order(self, order_id, operator):
        raise NotImplementedError  # TODO(B)
