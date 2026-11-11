"""机器模拟器（MachineDriver 的正式实现）。负责人：C。

构造参数是约定的一部分（wiring.py 按此创建），不要改。
验收标准是 tests/contract/test_machine.py。

必须满足的约定（契约测试会检查）：
- 一杯饮料从 start_job 起，经过 job_ms 毫秒（按 clock 计时）完成；
- 制作过程中 inject_fault() → 当前任务 FAILED，机器 offline，直到 clear_fault；
- progress 在 0–100 之间且不减少，DONE 时为 100；step 非空。

真实感（MAC-05 加分项）：
- 按进度切成“落杯 → 加冰/加热 → 注入饮品 → 加糖 → 加料 → 封口”几步；
- 热饮没有冰，走“加热”；饮料里有哪种加料就多一步“加料”；
- 可调用 set_cups_left(n) 让模拟器自己数杯子，0 杯时自动注入 OUT_OF_CUPS 故障。
  正式流程里杯子数量由库存模块管，默认不启用（None）。

说明：MachineDriver.start_job 只收到 consumption，没有温度字段，因此用“是否加冰”
近似判断热饮。若以后要把温度传给机器，需要先改接口约定。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

from drink.model import (Clock, DrinkError, ErrorCode, FaultCode, JobState, JobStatus,
                         MachineState)

from .interfaces import MachineDriver

ADDON_MATERIALS = ("pearl", "pudding", "coconut")


@dataclass
class _Job:
    order_id: str
    start_ms: int
    steps: tuple[str, ...]
    state: JobState = JobState.RUNNING
    progress: int = 0
    fault: FaultCode | None = None


class MachineSimulator(MachineDriver):

    def __init__(self, machine_id: str, clock: Clock, job_ms: int = 6000):
        self._machine_id = machine_id
        self.clock = clock
        self.job_ms = max(1, int(job_ms))
        self._lock = threading.RLock()
        self._jobs: dict[str, _Job] = {}
        self._faults: list[FaultCode] = []
        self._cups_left: int | None = None

    @property
    def machine_id(self):
        return self._machine_id

    # ----- MachineDriver -----

    def status(self):
        with self._lock:
            self._refresh()
            return self._state()

    def start_job(self, order_id, consumption):
        with self._lock:
            self._refresh()
            if order_id in self._jobs:          # 同一订单重复调用：幂等
                return
            if self._faults:
                raise DrinkError(ErrorCode.MACHINE_UNAVAILABLE, "机器故障，暂停服务")
            if self._running():
                raise DrinkError(ErrorCode.MACHINE_UNAVAILABLE, "机器正在制作上一杯")
            if self._cups_left is not None:
                if self._cups_left <= 0:
                    self._add_fault(FaultCode.OUT_OF_CUPS)
                    raise DrinkError(ErrorCode.MACHINE_UNAVAILABLE, "杯子用完，暂停服务")
                self._cups_left -= 1
            self._jobs[order_id] = _Job(order_id, self.clock.now_ms(),
                                        self._steps_for(consumption))

    def job_status(self, order_id):
        with self._lock:
            self._refresh()
            job = self._jobs.get(order_id)
            if job is None:
                raise DrinkError(ErrorCode.NOT_FOUND, f"没有订单 {order_id} 的制作任务")
            if job.state == JobState.DONE:
                return JobStatus(order_id, JobState.DONE, 100, "出杯完成")
            if job.state == JobState.FAILED:
                return JobStatus(order_id, JobState.FAILED, job.progress, "故障停止",
                                 job.fault)
            return JobStatus(order_id, JobState.RUNNING, job.progress, self._step_of(job))

    def clear_fault(self, code=None):
        with self._lock:
            if code is None:
                self._faults = []
            else:
                self._faults = [fault for fault in self._faults if fault != code]
            return self._state()

    # ----- 模拟器专有：演示用 -----

    def inject_fault(self, code: FaultCode) -> None:
        """注入故障：机器立刻离线；正在制作的那一单立刻 FAILED。"""
        with self._lock:
            self._refresh()
            self._add_fault(code)
            now = self.clock.now_ms()
            for job in self._running():
                job.state = JobState.FAILED
                job.fault = code
                job.progress = max(job.progress, self._progress_at(job, now))

    def set_cups_left(self, cups: int | None) -> None:
        """演示用：设置机器内部剩余的杯子数；None 表示不跟踪（由库存模块负责）。

        设为 0 后下一单会被拒绝，并自动报 OUT_OF_CUPS 故障。
        """
        with self._lock:
            self._cups_left = None if cups is None else max(0, int(cups))

    # ----- 内部 -----

    def _state(self) -> MachineState:
        return MachineState(self._machine_id, not self._faults, bool(self._running()),
                            tuple(self._faults))

    def _running(self) -> list[_Job]:
        return [job for job in self._jobs.values() if job.state == JobState.RUNNING]

    def _refresh(self) -> None:
        now = self.clock.now_ms()
        for job in self._jobs.values():
            if job.state != JobState.RUNNING:
                continue
            if now - job.start_ms >= self.job_ms:
                job.state = JobState.DONE
                job.progress = 100
            else:
                job.progress = max(job.progress, self._progress_at(job, now))

    def _progress_at(self, job: _Job, now_ms: int) -> int:
        """运行中的进度：0–99，避免在完成前一毫秒就显示 100。"""
        return max(0, min(99, (now_ms - job.start_ms) * 100 // self.job_ms))

    def _add_fault(self, code: FaultCode) -> None:
        if code not in self._faults:
            self._faults.append(code)

    @staticmethod
    def _steps_for(consumption) -> tuple[str, ...]:
        steps = ["落杯"]
        steps.append("加冰" if consumption.get("ice", 0) > 0 else "加热")
        steps.append("注入饮品")
        if consumption.get("syrup", 0) > 0:
            steps.append("加糖")
        if any(consumption.get(material_id, 0) > 0 for material_id in ADDON_MATERIALS):
            steps.append("加料")
        steps.append("封口")
        return tuple(steps)

    @staticmethod
    def _step_of(job: _Job) -> str:
        index = min(len(job.steps) - 1, job.progress * len(job.steps) // 100)
        return job.steps[index]
