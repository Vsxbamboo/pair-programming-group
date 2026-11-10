"""实体 <-> JSON。负责人：D（数据结构）。

to_jsonable：任何实体 → 可以 json.dumps 的 dict/list。
recipe_from_dict：前端发来的 JSON → Recipe（只校验格式，业务规则由食材端校验）。
"""
from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any

from .entities import Recipe, StockLevel
from .enums import Size, Sugar, Temperature
from .errors import DrinkError, ErrorCode


def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, StockLevel):
        return {"material": to_jsonable(obj.material), "quantity": obj.quantity,
                "status": obj.status.value}
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(to_jsonable(k)): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    return obj


def _enum(cls, value, field_name):
    try:
        return cls(value)
    except ValueError:
        allowed = ", ".join(m.value for m in cls)
        raise DrinkError(ErrorCode.INVALID_ARGUMENT, f"{field_name} 只能是 {allowed}") from None


def recipe_from_dict(data: Any) -> Recipe:
    if not isinstance(data, dict):
        raise DrinkError(ErrorCode.INVALID_ARGUMENT, "recipe 必须是对象")
    base_id = data.get("base_id")
    if not isinstance(base_id, str) or not base_id:
        raise DrinkError(ErrorCode.INVALID_ARGUMENT, "缺少 base_id")
    addon_ids = data.get("addon_ids", [])
    if not isinstance(addon_ids, list) or not all(isinstance(x, str) for x in addon_ids):
        raise DrinkError(ErrorCode.INVALID_ARGUMENT, "addon_ids 必须是字符串数组")
    return Recipe(
        base_id=base_id,
        addon_ids=tuple(addon_ids),
        size=_enum(Size, data.get("size", Size.M.value), "size"),
        temperature=_enum(Temperature, data.get("temperature", Temperature.ICED.value), "temperature"),
        sugar=_enum(Sugar, data.get("sugar", Sugar.HALF.value), "sugar"),
    )


def recipe_to_dict(recipe: Recipe) -> dict:
    return to_jsonable(recipe)
