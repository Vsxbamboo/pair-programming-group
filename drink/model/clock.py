"""时间来源。负责人：D（数据结构）。

业务代码一律通过 Clock 取时间，不直接调用 time.time()，这样测试可以“快进”。
时间统一用 epoch 毫秒（int）。
"""
import time
from typing import Protocol


class Clock(Protocol):
    def now_ms(self) -> int: ...


class SystemClock:
    def now_ms(self) -> int:
        return int(time.time() * 1000)


class FakeClock:
    """测试用：时间只在调用 advance() 时前进。"""

    def __init__(self, start_ms: int = 1_762_000_000_000):
        self._now = start_ms

    def now_ms(self) -> int:
        return self._now

    def advance(self, ms: int) -> None:
        self._now += ms
