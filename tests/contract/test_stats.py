"""StatsService 契约测试。负责人：C（数据维护 · 用户分析）。"""
from datetime import datetime, timedelta, timezone

import pytest

from drink.model import OrderStatus, Sugar
from helpers import make_order

COMPONENT = "stats"
BJ = timezone(timedelta(hours=8))


def at(hour, minute=0, day=10):
    """北京时间 2026-11-<day> hour:minute 的 epoch 毫秒。"""
    return int(datetime(2026, 11, day, hour, minute, tzinfo=BJ).timestamp() * 1000)


@pytest.fixture
def stats(system):
    return system.stats


@pytest.fixture
def save(system):
    return system.repo.save_order


def test_empty(stats, clock):
    s = stats.summary()
    assert (s.order_count, s.revenue_fen, s.top_combos, s.by_hour, s.by_sugar) == (0, 0, (), {}, {})
    assert (s.machine_id, s.since_ms, s.until_ms) == (None, 0, clock.now_ms())


def test_only_completed_orders_count(stats, save):
    save(make_order("a", total_fen=1200, status=OrderStatus.COMPLETED, created_at=at(9)))
    save(make_order("b", total_fen=1400, status=OrderStatus.COMPLETED, created_at=at(9, 30)))
    for i, st in enumerate([OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.MAKING,
                            OrderStatus.PRODUCTION_FAILED, OrderStatus.REFUNDED]):
        save(make_order(f"x{i}", total_fen=999, status=st, created_at=at(10)))
    s = stats.summary()
    assert (s.order_count, s.revenue_fen) == (2, 2600)


def test_machine_and_time_filters(stats, save):
    save(make_order("a", created_at=at(9)))
    save(make_order("b", created_at=at(10), machine_id="M002"))
    save(make_order("c", created_at=at(11)))
    assert stats.summary(machine_id="M001").order_count == 2
    assert stats.summary(machine_id="M002").order_count == 1
    s = stats.summary(since_ms=at(10), until_ms=at(11))
    assert (s.order_count, s.since_ms, s.until_ms) == (1, at(10), at(11))


def test_by_hour_uses_beijing_time(stats, save):
    save(make_order("a", created_at=at(0, 30)))
    save(make_order("b", created_at=at(15, 5)))
    save(make_order("c", created_at=at(15, 59)))
    assert stats.summary().by_hour == {0: 1, 15: 2}


def test_by_sugar(stats, save):
    save(make_order("a", sugar=Sugar.HALF))
    save(make_order("b", sugar=Sugar.HALF))
    save(make_order("c", sugar=Sugar.NONE))
    assert stats.summary().by_sugar == {"HALF": 2, "NONE": 1}


def test_top_combos_grouping_and_labels(stats, save):
    save(make_order("a", base="milk_tea", addons=("pudding", "pearl")))
    save(make_order("b", base="milk_tea", addons=("pearl", "pudding"), sugar=Sugar.NONE))
    save(make_order("c", base="jasmine"))
    combos = stats.summary().top_combos
    assert [(c.label, c.count) for c in combos] == [("经典奶茶 + 黑糖珍珠 + 香滑布丁", 2),
                                                   ("茉莉绿茶", 1)]
    assert combos[0].recipe.base_id == "milk_tea"
    assert combos[0].recipe.addon_ids == ("pearl", "pudding")


def test_top_combos_ties_by_label_and_max_five(stats, save):
    combos = [("milk_tea", ()), ("jasmine", ()), ("latte", ()), ("lemon_soda", ()),
              ("milk_tea", ("pearl",)), ("jasmine", ("pearl",))]
    for i, (base, addons) in enumerate(combos):
        save(make_order(f"o{i}", base=base, addons=addons))
    labels = [c.label for c in stats.summary().top_combos]
    assert len(labels) == 5
    assert labels == sorted(labels)


def test_top_recipes(stats, save):
    for i in range(3):
        save(make_order(f"l{i}", base="latte"))
    save(make_order("j", base="jasmine"))
    save(make_order("x", base="jasmine", status=OrderStatus.CANCELLED))
    save(make_order("y", base="jasmine", status=OrderStatus.CANCELLED))
    top = stats.top_recipes(limit=1)
    assert [(c.recipe.base_id, c.count) for c in top] == [("latte", 3)]
    assert len(stats.top_recipes(limit=5)) == 2
