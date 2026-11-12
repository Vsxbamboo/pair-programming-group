"""食材端正式实现。负责人：B。

构造参数是约定的一部分（wiring.py 按此创建），不要改。
行为约定见 interfaces.IngredientService 的文档字符串；验收标准是 tests/contract/test_ingredient.py。
"""
from __future__ import annotations

from collections import Counter
from itertools import chain

from drink.maintenance.interfaces import InventoryService, StatsService
from drink.model import (Consumption, DrinkError, ErrorCode, ItemKind, Menu, MenuEntry,
                         MenuItem, OrderLine, Quote, Recipe, Repository, Size, Sugar,
                         Temperature, seed)

from .interfaces import IngredientService


class IngredientServiceImpl(IngredientService):

    def __init__(self, repo: Repository, inventory: InventoryService, stats: StatsService):
        self.repo = repo
        self.inventory = inventory
        self.stats = stats

    def _menu_item(self, item_id: str, kind: ItemKind) -> MenuItem:
        item = self.repo.get_menu_item(item_id)
        if item is None or item.kind != kind:
            label = "基底" if kind == ItemKind.BASE else "加料"
            raise DrinkError(ErrorCode.INVALID_RECIPE, f"没有这种{label}：{item_id}")
        return item

    def _recipe_items(self, recipe: Recipe) -> tuple[MenuItem, tuple[MenuItem, ...]]:
        base = self._menu_item(recipe.base_id, ItemKind.BASE)
        if len(set(recipe.addon_ids)) != len(recipe.addon_ids):
            raise DrinkError(ErrorCode.INVALID_RECIPE, "同一种加料不能重复选择")
        if len(recipe.addon_ids) > seed.MAX_ADDONS:
            raise DrinkError(ErrorCode.INVALID_RECIPE, f"加料最多 {seed.MAX_ADDONS} 种")
        addons = tuple(self._menu_item(item_id, ItemKind.ADDON) for item_id in recipe.addon_ids)
        if recipe.temperature == Temperature.HOT and not base.hot_allowed:
            raise DrinkError(ErrorCode.INVALID_RECIPE, f"{base.name}不能做热饮")
        if recipe.temperature == Temperature.ICED and not base.iced_allowed:
            raise DrinkError(ErrorCode.INVALID_RECIPE, f"{base.name}不能加冰")
        return base, addons

    def validate(self, recipe: Recipe) -> None:
        self._recipe_items(recipe)

    def quote(self, recipe: Recipe) -> Quote:
        base, addons = self._recipe_items(recipe)
        lines = [OrderLine(item.name, item.price_fen) for item in (base, *addons)]
        extra = seed.SIZE_EXTRA_FEN[recipe.size]
        if extra > 0:
            lines.append(OrderLine("大杯", extra))
        return Quote(tuple(lines), sum(line.price_fen for line in lines))

    @staticmethod
    def _base_consumption(base: MenuItem, size: Size) -> Counter[str]:
        factor = seed.SIZE_FACTOR[size]
        amounts = Counter({
            material_id: round(quantity * factor)
            for material_id, quantity in base.consumption.items()
        })
        amounts["cup"] += 1
        return amounts

    def consumption_of(self, recipe: Recipe) -> Consumption:
        base, addons = self._recipe_items(recipe)
        factor = seed.SIZE_FACTOR[recipe.size]
        amounts = self._base_consumption(base, recipe.size)
        amounts["syrup"] += round(seed.SUGAR_SYRUP_ML[recipe.sugar] * factor)
        amounts["ice"] += round(seed.ICE_G[recipe.temperature] * factor)
        for addon in addons:
            amounts.update(addon.consumption)
        return {material_id: quantity for material_id, quantity in amounts.items() if quantity > 0}

    def get_menu(self) -> Menu:
        bases, addons = [], []
        for item in self.repo.list_menu_items():
            if item.kind == ItemKind.BASE:
                amounts = self._base_consumption(item, Size.L)
                bases.append(MenuEntry(item, not self.inventory.check(dict(amounts))))
            elif item.kind == ItemKind.ADDON:
                addons.append(MenuEntry(item, not self.inventory.check(item.consumption)))
        return Menu(tuple(bases), tuple(addons), tuple(Size), tuple(Temperature), tuple(Sugar),
                    {size.value: extra for size, extra in seed.SIZE_EXTRA_FEN.items()},
                    seed.DEFAULT_RECIPE)

    def recommend(self, limit: int = 3) -> list[Recipe]:
        if limit <= 0:
            return []
        popular = self.stats.top_recipes(limit * 2)
        candidates = chain((combo.recipe for combo in popular), seed.PRESET_RECOMMENDATIONS)
        recommendations = []
        seen = set()
        for recipe in candidates:
            key = (recipe.base_id, frozenset(recipe.addon_ids))
            if key in seen:
                continue
            try:
                amounts = self.consumption_of(recipe)
            except DrinkError as error:
                if error.code != ErrorCode.INVALID_RECIPE:
                    raise
                continue
            if self.inventory.check(amounts):
                continue
            seen.add(key)
            recommendations.append(recipe)
            if len(recommendations) == limit:
                break
        return recommendations
