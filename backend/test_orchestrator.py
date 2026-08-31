from orchestrator import DispatchLimits, DispatchTier, TaskState, acceptance_blocked, can_transition, validate_limits, write_sets_conflict


def test_state_machine_and_acceptance_gate():
    assert can_transition(TaskState.QUEUED, TaskState.CLAIMED)
    assert not can_transition(TaskState.QUEUED, TaskState.RELEASED)
    assert acceptance_blocked(["P1"])
    assert acceptance_blocked([" P1 "])
    assert not acceptance_blocked(["P1"], accepted_risk=True)


def test_disjoint_write_sets_can_run_together():
    assert not write_sets_conflict(["artifacts/routes/A"], ["artifacts/routes/B"])
    assert write_sets_conflict(["src/model.py"], ["src"])


def test_dispatch_limits():
    validate_limits(DispatchTier.SOLO, DispatchLimits(max_agents=1, max_parallel=1))
    validate_limits(DispatchTier.LITE, DispatchLimits(max_agents=3, max_parallel=2))
