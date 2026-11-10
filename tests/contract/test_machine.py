"""MachineDriver 契约测试。负责人：C（机器维护）。所有时长按 conftest.JOB_MS（5 秒）计。"""
import pytest

from conftest import JOB_MS
from drink.model import DrinkError, ErrorCode, FaultCode, JobState

COMPONENT = "machine"
CUP = {"black_tea": 200, "milk": 150, "cup": 1}


@pytest.fixture
def m(system):
    return system.machine


def code_of(fn, *args):
    with pytest.raises(DrinkError) as e:
        fn(*args)
    return e.value.code


def test_initial_status(m):
    s = m.status()
    assert (s.machine_id, s.online, s.busy, s.faults) == ("M001", True, False, ())


def test_job_runs_to_done(m, clock):
    m.start_job("O1", CUP)
    assert m.status().busy
    j = m.job_status("O1")
    assert j.state == JobState.RUNNING and 0 <= j.progress < 100 and j.step
    clock.advance(JOB_MS)
    j = m.job_status("O1")
    assert (j.state, j.progress) == (JobState.DONE, 100)
    assert not m.status().busy


def test_not_done_one_ms_early(m, clock):
    m.start_job("O1", CUP)
    clock.advance(JOB_MS - 1)
    assert m.job_status("O1").state == JobState.RUNNING


def test_progress_never_decreases(m, clock):
    m.start_job("O1", CUP)
    seen = []
    for _ in range(6):
        seen.append(m.job_status("O1").progress)
        clock.advance(JOB_MS // 5)
    assert seen == sorted(seen) and seen[-1] == 100


def test_busy_rejects_second_job_but_same_id_is_idempotent(m, clock):
    m.start_job("O1", CUP)
    m.start_job("O1", CUP)
    assert code_of(m.start_job, "O2", CUP) == ErrorCode.MACHINE_UNAVAILABLE
    clock.advance(JOB_MS)
    m.start_job("O2", CUP)
    assert m.job_status("O2").state == JobState.RUNNING


def test_unknown_job(m):
    assert code_of(m.job_status, "nope") == ErrorCode.NOT_FOUND


def test_fault_during_job(m, clock):
    m.start_job("O1", CUP)
    clock.advance(1000)
    m.inject_fault(FaultCode.CUP_JAM)
    j = m.job_status("O1")
    assert (j.state, j.fault) == (JobState.FAILED, FaultCode.CUP_JAM)
    clock.advance(JOB_MS)
    assert m.job_status("O1").state == JobState.FAILED
    s = m.status()
    assert (s.online, s.busy, s.faults) == (False, False, (FaultCode.CUP_JAM,))
    assert code_of(m.start_job, "O2", CUP) == ErrorCode.MACHINE_UNAVAILABLE


def test_clear_faults(m):
    m.inject_fault(FaultCode.CUP_JAM)
    m.inject_fault(FaultCode.PUMP_ERROR)
    assert m.clear_fault(FaultCode.CUP_JAM).faults == (FaultCode.PUMP_ERROR,)
    s = m.clear_fault()
    assert (s.online, s.faults) == (True, ())
    m.start_job("O3", CUP)


def test_fault_when_idle_takes_machine_offline(m):
    m.inject_fault(FaultCode.WATER_TEMP_LOW)
    assert not m.status().online
