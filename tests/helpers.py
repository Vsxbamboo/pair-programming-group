"""测试里造数据的小工具。"""
from drink.model import (Order, OrderLine, OrderStatus, PaymentInfo, PaymentStatus, Recipe, Size,
                         Sugar, Temperature)


def make_order(order_id="O1", *, machine_id="M001", base="milk_tea", addons=(),
               sugar=Sugar.HALF, status=OrderStatus.COMPLETED, created_at=1_762_000_000_000,
               total_fen=1200, payment=True, failure_reason=None) -> Order:
    recipe = Recipe(base, tuple(addons), Size.M, Temperature.ICED, sugar)
    pay = PaymentInfo("mock", f"mock-pay://{order_id}", PaymentStatus.SUCCESS) if payment else None
    return Order(order_id, machine_id, recipe, (OrderLine("测试", total_fen),), total_fen, status,
                 created_at, created_at, created_at + 120_000, pay, failure_reason)
