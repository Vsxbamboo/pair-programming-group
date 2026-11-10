"""测试公共设施 + 进度看板。

每个契约测试都会跑两遍：
    [reference]  参考实现 —— 必须全部通过，否则是测试本身写错了；
    [real]       正式实现 —— 你的代码，全部通过即完成。
测试结束时打印“各负责人进度”表。
"""
from __future__ import annotations

import unicodedata
from collections import defaultdict

import pytest

from drink.model import FakeClock
from drink.wiring import OWNERS, build

JOB_MS = 5000


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture(params=["reference", "real"])
def impl(request):
    return request.param


@pytest.fixture
def system(request, impl, clock, tmp_path):
    """按测试文件里的 COMPONENT 决定哪个组件用正式实现。"""
    component = getattr(request.module, "COMPONENT", None)
    real = {component} if impl == "real" and component else set()
    if impl == "real" and getattr(request.module, "ALL_REAL", False):
        real = set(OWNERS)
    return build(real, db_path=str(tmp_path / "test.db"), clock=clock, machine_job_ms=JOB_MS)


# ---------------------------------------------------------------- 进度看板

_meta: dict[str, tuple[str, str]] = {}
_result: dict[str, str] = {}


def _owner_of(item) -> str:
    owner = getattr(item.module, "OWNER", None)
    if owner:
        return owner
    component = getattr(item.module, "COMPONENT", None)
    return OWNERS.get(component, "未分配")


def pytest_collection_modifyitems(items):
    for item in items:
        params = getattr(item, "callspec", None)
        impl = params.params.get("impl", "real") if params else "real"
        _meta[item.nodeid] = (_owner_of(item), impl)


def pytest_runtest_logreport(report):
    prev = _result.get(report.nodeid)
    if report.skipped:
        outcome = "skipped"
    elif report.failed:
        text = str(report.longrepr)
        outcome = "todo" if "NotImplementedError" in text else "failed"
    elif report.when == "call":
        outcome = "passed"
    else:
        return
    if prev in ("failed", "todo") and outcome != "failed":
        return
    _result[report.nodeid] = outcome


def _pad(value, width, right=False):
    text = str(value)
    shown = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    space = " " * max(0, width - shown)
    return space + text if right else text + space


def pytest_terminal_summary(terminalreporter):
    if not _result:
        return
    table = defaultdict(lambda: defaultdict(int))
    for nodeid, outcome in _result.items():
        owner, impl = _meta.get(nodeid, ("未分配", "real"))
        table[(owner, impl)][outcome] += 1
        table[(owner, impl)]["total"] += 1
    tr = terminalreporter
    tr.section("各负责人进度（real = 你的正式实现；reference = 参考实现，应全绿）")
    header = ["负责人", "对象", "通过", "未实现", "失败", "跳过", "合计"]
    widths = [18, 11, 6, 8, 6, 6, 6]
    tr.write_line("".join(_pad(h, w, i >= 2) for i, (h, w) in enumerate(zip(header, widths))))
    for (owner, impl), c in sorted(table.items()):
        row = [owner, impl, c["passed"], c["todo"], c["failed"], c["skipped"], c["total"]]
        done = "  √ 完成" if c["passed"] + c["skipped"] == c["total"] else ""
        tr.write_line("".join(_pad(v, w, i >= 2) for i, (v, w) in enumerate(zip(row, widths))) + done)
    if any(impl == "reference" and c["failed"] for (_, impl), c in table.items()):
        tr.write_line("注意：参考实现有失败，说明测试或参考实现有问题，请联系 D 和 A。", red=True)
