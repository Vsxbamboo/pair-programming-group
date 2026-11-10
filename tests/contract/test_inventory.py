"""InventoryService 契约测试。负责人：C（数据维护）。"""
import pytest

from drink.model import DrinkError, ErrorCode

COMPONENT = "inventory"


@pytest.fixture
def inv(system):
    return system.inventory


def qty(system, material_id):
    return system.repo.get_stock(material_id).quantity


def test_list_stock_matches_repository(system, inv):
    assert inv.list_stock() == system.repo.list_stock()


class TestCheck:
    def test_enough(self, inv):
        assert inv.check({"milk": 150, "cup": 1}) == []

    def test_exactly_enough(self, inv):
        assert inv.check({"pudding": 150}) == []

    def test_missing_sorted(self, inv):
        assert inv.check({"pudding": 151, "coconut": 1, "milk": 1}) == ["coconut", "pudding"]

    def test_unknown_material_counts_as_missing(self, inv):
        assert inv.check({"gold": 1}) == ["gold"]


class TestConsume:
    def test_deducts(self, system, inv):
        inv.consume({"milk": 150, "cup": 1}, "O1")
        assert qty(system, "milk") == 4850
        assert qty(system, "cup") == 199

    def test_all_or_nothing(self, system, inv):
        with pytest.raises(DrinkError) as e:
            inv.consume({"milk": 150, "coconut": 40}, "O1")
        assert e.value.code == ErrorCode.OUT_OF_STOCK
        assert qty(system, "milk") == 5000


class TestRestock:
    def test_restock_adds_and_records(self, system, inv, clock):
        level = inv.restock("pudding", 1000, "小王")
        assert level.quantity == 1150
        assert qty(system, "pudding") == 1150
        [record] = inv.list_restocks()
        assert (record.material_id, record.quantity, record.operator) == ("pudding", 1000, "小王")
        assert record.created_at == clock.now_ms()

    def test_fill_to_capacity_exactly(self, inv):
        assert inv.restock("pudding", 1350, "小王").quantity == 1500

    @pytest.mark.parametrize("bad", [0, -5, 1.5, "10", True])
    def test_quantity_must_be_positive_int(self, system, inv, bad):
        with pytest.raises(DrinkError) as e:
            inv.restock("pudding", bad, "小王")
        assert e.value.code == ErrorCode.INVALID_ARGUMENT
        assert qty(system, "pudding") == 150
        assert inv.list_restocks() == []

    def test_operator_required(self, inv):
        with pytest.raises(DrinkError) as e:
            inv.restock("pudding", 10, "  ")
        assert e.value.code == ErrorCode.INVALID_ARGUMENT

    def test_over_capacity(self, system, inv):
        with pytest.raises(DrinkError) as e:
            inv.restock("pudding", 1351, "小王")
        assert e.value.code == ErrorCode.INVALID_ARGUMENT
        assert qty(system, "pudding") == 150
        assert inv.list_restocks() == []

    def test_unknown_material(self, inv):
        with pytest.raises(DrinkError) as e:
            inv.restock("gold", 1, "小王")
        assert e.value.code == ErrorCode.NOT_FOUND

    def test_list_newest_first_with_limit(self, inv, clock):
        inv.restock("pudding", 10, "a")
        clock.advance(1000)
        inv.restock("coconut", 20, "b")
        records = inv.list_restocks()
        assert [r.operator for r in records] == ["b", "a"]
        assert [r.operator for r in inv.list_restocks(limit=1)] == ["b"]
