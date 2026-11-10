"""IngredientService 契约测试。负责人：B（食材端）。"""
import pytest

from drink.model import (DrinkError, ErrorCode, OrderLine, Recipe, Size, Sugar, Temperature,
                         seed)
from helpers import make_order

COMPONENT = "ingredient"


@pytest.fixture
def ing(system):
    return system.ingredient


def invalid(ing, recipe):
    with pytest.raises(DrinkError) as e:
        ing.validate(recipe)
    assert e.value.code == ErrorCode.INVALID_RECIPE
    assert e.value.message


class TestMenu:
    def test_structure(self, ing):
        menu = ing.get_menu()
        assert [e.item.id for e in menu.bases] == ["milk_tea", "jasmine", "latte", "lemon_soda"]
        assert [e.item.id for e in menu.addons] == ["pearl", "pudding", "coconut"]
        assert menu.sizes == tuple(Size)
        assert menu.temperatures == tuple(Temperature)
        assert menu.sugars == tuple(Sugar)
        assert menu.size_extra_fen == {"M": 0, "L": 300}
        assert menu.default_recipe == seed.DEFAULT_RECIPE

    def test_initial_availability(self, ing):
        menu = ing.get_menu()
        assert all(e.available for e in menu.bases)
        assert {e.item.id: e.available for e in menu.addons} == {
            "pearl": True, "pudding": True, "coconut": False}

    def test_base_needs_a_large_cup(self, system, ing):
        system.repo.apply_stock_changes({"black_tea": -(5000 - 279)})   # 大杯需要 280
        bases = {e.item.id: e.available for e in ing.get_menu().bases}
        assert bases["milk_tea"] is False and bases["jasmine"] is True

    def test_no_cups_means_nothing_available(self, system, ing):
        system.repo.apply_stock_changes({"cup": -200})
        assert not any(e.available for e in ing.get_menu().bases)

    def test_shared_material(self, system, ing):
        system.repo.apply_stock_changes({"milk": -5000})
        bases = {e.item.id: e.available for e in ing.get_menu().bases}
        assert bases == {"milk_tea": False, "jasmine": True, "latte": False, "lemon_soda": True}


class TestValidate:
    def test_valid(self, ing):
        ing.validate(Recipe("milk_tea", ("pearl", "pudding", "coconut"), Size.L,
                            Temperature.HOT, Sugar.NONE))   # 不检查库存

    def test_unknown_base(self, ing):
        invalid(ing, Recipe("cola"))

    def test_addon_as_base(self, ing):
        invalid(ing, Recipe("pearl"))

    def test_base_as_addon(self, ing):
        invalid(ing, Recipe("milk_tea", ("jasmine",)))

    def test_unknown_addon(self, ing):
        invalid(ing, Recipe("milk_tea", ("gold",)))

    def test_duplicate_addon(self, ing):
        invalid(ing, Recipe("milk_tea", ("pearl", "pearl")))

    def test_hot_lemon_soda(self, ing):
        invalid(ing, Recipe("lemon_soda", temperature=Temperature.HOT))
        ing.validate(Recipe("lemon_soda", temperature=Temperature.NORMAL))


class TestQuote:
    def test_medium(self, ing):
        q = ing.quote(Recipe("milk_tea", ("pearl",)))
        assert q.lines == (OrderLine("经典奶茶", 1200), OrderLine("黑糖珍珠", 200))
        assert q.total_fen == 1400

    def test_large_keeps_addon_order(self, ing):
        q = ing.quote(Recipe("jasmine", ("pudding", "pearl"), Size.L))
        assert [l.label for l in q.lines] == ["茉莉绿茶", "香滑布丁", "黑糖珍珠", "大杯"]
        assert q.total_fen == 800 + 300 + 200 + 300

    def test_invalid(self, ing):
        with pytest.raises(DrinkError) as e:
            ing.quote(Recipe("cola"))
        assert e.value.code == ErrorCode.INVALID_RECIPE


class TestConsumption:
    def test_medium_iced_half(self, ing):
        assert ing.consumption_of(Recipe("milk_tea", ("pearl",))) == {
            "black_tea": 200, "milk": 150, "syrup": 15, "ice": 80, "pearl": 40, "cup": 1}

    def test_large_hot_full(self, ing):
        assert ing.consumption_of(Recipe("jasmine", ("pudding",), Size.L, Temperature.HOT,
                                         Sugar.FULL)) == {
            "green_tea": 490, "syrup": 42, "pudding": 50, "cup": 1}

    def test_large_light_iced_rounding(self, ing):
        c = ing.consumption_of(Recipe("latte", (), Size.L, Temperature.ICED, Sugar.LIGHT))
        assert c == {"coffee": 168, "milk": 280, "syrup": 13, "ice": 112, "cup": 1}

    def test_zero_amounts_omitted(self, ing):
        c = ing.consumption_of(Recipe("lemon_soda", (), Size.M, Temperature.NORMAL, Sugar.NONE))
        assert c == {"lemon_juice": 60, "soda": 300, "cup": 1}


class TestRecommend:
    def test_presets_when_no_sales(self, ing):
        assert ing.recommend() == list(seed.PRESET_RECOMMENDATIONS)
        assert ing.recommend(limit=2) == list(seed.PRESET_RECOMMENDATIONS[:2])

    def test_best_sellers_first_and_deduplicated(self, system, ing):
        for i in range(3):
            system.repo.save_order(make_order(f"s{i}", base="lemon_soda"))
        system.repo.save_order(make_order("p", base="milk_tea", addons=("pearl",)))
        recs = ing.recommend(limit=3)
        assert [(r.base_id, r.addon_ids) for r in recs] == [
            ("lemon_soda", ()), ("milk_tea", ("pearl",)), ("jasmine", ())]

    def test_skips_unavailable(self, system, ing):
        system.repo.apply_stock_changes({"green_tea": -5000})
        recs = ing.recommend()
        assert "jasmine" not in [r.base_id for r in recs]
        for r in recs:
            ing.validate(r)
            assert system.inventory.check(ing.consumption_of(r)) == []
