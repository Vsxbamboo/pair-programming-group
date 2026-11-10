"""端到端流程。负责人：D（集成），全组的正式实现都完成后才会通过。

[reference] 全部用参考实现；[real] 全部用正式实现。
"""
from conftest import JOB_MS
from drink.model import FaultCode, OrderStatus, Recipe, Size, Sugar, Temperature
from drink.model.repository import SqliteRepository
from drink.model import seed

OWNER = "全组 集成"
ALL_REAL = True


def test_a_day_at_the_machine(system, clock, impl, tmp_path):
    s = system
    # 1. 顾客看菜单：椰果售罄
    menu = s.ingredient.get_menu()
    assert not {e.item.id: e.available for e in menu.addons}["coconut"]

    # 2. 维护人员补椰果
    s.inventory.restock("coconut", 1000, "小王")
    assert {e.item.id: e.available for e in s.ingredient.get_menu().addons}["coconut"]

    # 3. 顾客点一杯大杯热奶茶加椰果，扫码付款，等待出杯
    recipe = Recipe("milk_tea", ("coconut",), Size.L, Temperature.HOT, Sugar.LIGHT)
    order = s.orders.create_order(recipe)
    assert order.total_fen == 1200 + 200 + 300
    s.payment.simulate_success(order.order_id)
    assert s.orders.get_order(order.order_id).status == OrderStatus.MAKING
    clock.advance(JOB_MS)
    assert s.orders.get_order(order.order_id).status == OrderStatus.COMPLETED
    assert s.repo.get_stock("coconut").quantity == 1000 - 40

    # 4. 下一位顾客：制作中卡杯 → 维护人员退款、排除故障
    second = s.orders.create_order(Recipe("jasmine"))
    s.payment.simulate_success(second.order_id)
    s.orders.get_order(second.order_id)
    s.machine.inject_fault(FaultCode.CUP_JAM)
    assert s.orders.get_order(second.order_id).status == OrderStatus.PRODUCTION_FAILED
    assert [o.order_id for o in s.orders.list_orders(OrderStatus.PRODUCTION_FAILED)] == [second.order_id]
    s.orders.refund_order(second.order_id, "小王")
    assert s.machine.clear_fault().online

    # 5. 统计只算成功的那一杯；推荐把它排第一
    summary = s.stats.summary(machine_id="M001")
    assert (summary.order_count, summary.revenue_fen) == (1, 1700)
    assert summary.top_combos[0].label == "经典奶茶 + 椰果"
    assert s.ingredient.recommend(1)[0].addon_ids == ("coconut",)

    # 6. 重启程序，数据还在（仅正式实现）
    if impl == "real":
        again = SqliteRepository(str(tmp_path / "test.db"))
        again.initialize(seed.MATERIALS, seed.MENU_ITEMS, seed.INITIAL_STOCK)
        assert again.get_order(order.order_id).status == OrderStatus.COMPLETED
        assert again.get_stock("coconut").quantity == 960
