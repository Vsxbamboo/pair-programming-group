"""机器模拟器（MachineDriver 的正式实现）。负责人：C。

构造参数是约定的一部分（wiring.py 按此创建），不要改。
验收标准是 tests/contract/test_machine.py。

必须满足的约定（契约测试会检查）：
- 一杯饮料从 start_job 起，经过 job_ms 毫秒（按 clock 计时）完成；
- 制作过程中 inject_fault() → 当前任务 FAILED，机器 offline，直到 clear_fault；
- progress 在 0–100 之间且不减少，DONE 时为 100；step 非空。

可以自由发挥的部分：
- 制作步骤（落杯 → 加冰 → 注入茶底 → 加糖 → 加料 → 封口），每步的时长和 step 文案；
- 热饮需要先加热、杯子不足自动报 OUT_OF_CUPS 等更真实的模拟。
"""
from __future__ import annotations

from drink.model import Clock, FaultCode

from .interfaces import MachineDriver


class MachineSimulator(MachineDriver):

    def __init__(self, machine_id: str, clock: Clock, job_ms: int = 6000):
        self._machine_id = machine_id
        self.clock = clock
        self.job_ms = job_ms

    @property
    def machine_id(self):
        return self._machine_id

    def status(self):
        raise NotImplementedError  # TODO(C)

    def start_job(self, order_id, consumption):
        raise NotImplementedError  # TODO(C)

    def job_status(self, order_id):
        raise NotImplementedError  # TODO(C)

    def clear_fault(self, code=None):
        raise NotImplementedError  # TODO(C)

    # ----- 模拟器专有：演示用 -----
    def inject_fault(self, code: FaultCode) -> None:
        raise NotImplementedError  # TODO(C)
