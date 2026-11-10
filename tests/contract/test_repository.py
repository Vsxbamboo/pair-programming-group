"""Repository 契约测试。负责人：D（数据结构）。

    pytest tests/contract/test_repository.py -k real     # 只看自己的正式实现
"""
import dataclasses

import pytest

from drink.model import DrinkError, ErrorCode, OrderStatus, StockStatus, seed
from drink.model.repository import SqliteRepository
from helpers import make_order

COMPONENT = "repository"


@pytest.fixture
def repo(system):
    return system.repo


def stock_of(repo, material_id):
    return repo.get_stock(material_id).quantity


class TestCatalog:
    def test_materials_in_seed_order(self, repo):
        assert repo.list_materials() == list(seed.MATERIALS)

    def test_menu_items_in_seed_order_with_consumption(self, repo):
        assert repo.list_menu_items() == list(seed.MENU_ITEMS)

    def test_get_menu_item(self, repo):
        assert repo.get_menu_item("lemon_soda") == seed.MENU_ITEMS[3]
        assert repo.get_menu_item("lemon_soda").hot_allowed is False
        assert repo.get_menu_item("nope") is None

    def test_initialize_is_idempotent(self, repo):
        repo.apply_stock_changes({"milk": -100})
        repo.initialize(seed.MATERIALS, seed.MENU_ITEMS, seed.INITIAL_STOCK)
        assert len(repo.list_materials()) == len(seed.MATERIALS)
        assert stock_of(repo, "milk") == seed.INITIAL_STOCK["milk"] - 100


class TestStock:
    def test_initial_stock_and_status(self, repo):
        levels = {s.material.id: s for s in repo.list_stock()}
        assert [s.material.id for s in repo.list_stock()] == [m.id for m in seed.MATERIALS]
        assert {k: v.quantity for k, v in levels.items()} == seed.INITIAL_STOCK
        assert levels["coconut"].status == StockStatus.EMPTY
        assert levels["pudding"].status == StockStatus.LOW
        assert levels["milk"].status == StockStatus.OK

    def test_get_unknown_stock(self, repo):
        with pytest.raises(DrinkError) as e:
            repo.get_stock("gold")
        assert e.value.code == ErrorCode.NOT_FOUND

    def test_apply_changes(self, repo):
        repo.apply_stock_changes({"milk": -150, "black_tea": -200, "coconut": 40})
        assert stock_of(repo, "milk") == 4850
        assert stock_of(repo, "black_tea") == 4800
        assert stock_of(repo, "coconut") == 40

    def test_negative_result_is_atomic(self, repo):
        with pytest.raises(DrinkError) as e:
            repo.apply_stock_changes({"milk": -100, "pudding": -151, "coconut": -1})
        assert e.value.code == ErrorCode.OUT_OF_STOCK
        assert e.value.details["missing"] == ["coconut", "pudding"]
        assert stock_of(repo, "milk") == 5000
        assert stock_of(repo, "pudding") == 150

    def test_unknown_material_is_atomic(self, repo):
        with pytest.raises(DrinkError) as e:
            repo.apply_stock_changes({"milk": -100, "gold": 1})
        assert e.value.code == ErrorCode.NOT_FOUND
        assert stock_of(repo, "milk") == 5000

    def test_can_reach_exactly_zero(self, repo):
        repo.apply_stock_changes({"pudding": -150})
        assert repo.get_stock("pudding").status == StockStatus.EMPTY


class TestOrders:
    def test_round_trip_keeps_every_field(self, repo):
        order = make_order("A1", addons=("pearl", "pudding"), status=OrderStatus.PRODUCTION_FAILED,
                           failure_reason="制作故障：CUP_JAM")
        repo.save_order(order)
        assert repo.get_order("A1") == order

    def test_round_trip_without_payment(self, repo):
        order = make_order("A2", payment=False)
        repo.save_order(order)
        assert repo.get_order("A2") == order

    def test_save_overwrites(self, repo):
        order = make_order("A1", status=OrderStatus.AWAITING_PAYMENT)
        repo.save_order(order)
        repo.save_order(dataclasses.replace(order, status=OrderStatus.PAID, updated_at=order.updated_at + 1))
        assert repo.get_order("A1").status == OrderStatus.PAID
        assert len(repo.list_orders()) == 1

    def test_unknown_order(self, repo):
        assert repo.get_order("nope") is None

    def test_list_filters_and_order(self, repo):
        t = 1_762_000_000_000
        repo.save_order(make_order("a", created_at=t, status=OrderStatus.COMPLETED))
        repo.save_order(make_order("b", created_at=t + 10, status=OrderStatus.CANCELLED))
        repo.save_order(make_order("c", created_at=t + 20, status=OrderStatus.COMPLETED,
                                   machine_id="M002"))
        repo.save_order(make_order("d", created_at=t + 30, status=OrderStatus.COMPLETED))
        ids = lambda orders: [o.order_id for o in orders]
        assert ids(repo.list_orders()) == ["d", "c", "b", "a"]
        assert ids(repo.list_orders(machine_id="M001")) == ["d", "b", "a"]
        assert ids(repo.list_orders(statuses=[OrderStatus.COMPLETED])) == ["d", "c", "a"]
        assert ids(repo.list_orders(statuses=[])) == []
        assert ids(repo.list_orders(since_ms=t + 10, until_ms=t + 30)) == ["c", "b"]
        assert ids(repo.list_orders(limit=2)) == ["d", "c"]


class TestRestocks:
    def test_add_and_list(self, repo):
        r1 = repo.add_restock("milk", 500, "小王", 100)
        r2 = repo.add_restock("pearl", 200, "小李", 200)
        assert (r1.record_id, r2.record_id) == (1, 2)
        assert repo.list_restocks() == [r2, r1]
        assert repo.list_restocks(limit=1) == [r2]

    def test_add_restock_does_not_change_stock(self, repo):
        repo.add_restock("milk", 500, "小王", 100)
        assert stock_of(repo, "milk") == 5000


def test_data_survives_restart(impl, system, tmp_path):
    """正式实现特有：换一个 SqliteRepository 实例（相当于重启程序），数据还在。"""
    if impl == "reference":
        pytest.skip("内存实现不持久化")
    system.repo.apply_stock_changes({"milk": -100})
    system.repo.save_order(make_order("P1"))
    system.repo.add_restock("milk", 1, "x", 1)
    again = SqliteRepository(str(tmp_path / "test.db"))
    again.initialize(seed.MATERIALS, seed.MENU_ITEMS, seed.INITIAL_STOCK)
    assert again.get_stock("milk").quantity == 4900
    assert again.get_order("P1") == make_order("P1")
    assert len(again.list_restocks()) == 1
