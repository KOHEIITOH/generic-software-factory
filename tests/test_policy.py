from sf_factory.policy import (
    Capability,
    ExecutionPolicy,
    ExecutionRequest,
    PolicyDecision,
)


def test_read_only_allowed_by_default() -> None:
    result = ExecutionPolicy().evaluate(ExecutionRequest(Capability.READ_ONLY))
    assert result.decision is PolicyDecision.ALLOW


def test_side_effects_denied_by_default_even_when_approved() -> None:
    policy = ExecutionPolicy()
    for capability in (Capability.WORKSPACE_WRITE, Capability.EXTERNAL_ACTION):
        result = policy.evaluate(ExecutionRequest(capability, approved=True))
        assert result.decision is PolicyDecision.DENY


def test_opted_in_side_effect_requires_approval() -> None:
    policy = ExecutionPolicy(allow_workspace_write=True)
    result = policy.evaluate(ExecutionRequest(Capability.WORKSPACE_WRITE))
    assert result.decision is PolicyDecision.REQUIRE_APPROVAL
    assert policy.evaluate(ExecutionRequest(Capability.WORKSPACE_WRITE, approved=True)).allowed


def test_external_action_has_separate_permission() -> None:
    policy = ExecutionPolicy(allow_workspace_write=True, allow_external_actions=False)
    assert not policy.evaluate(ExecutionRequest(Capability.EXTERNAL_ACTION, approved=True)).allowed


def test_execution_limits_fail_closed() -> None:
    policy = ExecutionPolicy()
    for request in (
        ExecutionRequest(Capability.READ_ONLY, timeout_seconds=0),
        ExecutionRequest(Capability.READ_ONLY, timeout_seconds=601),
        ExecutionRequest(Capability.READ_ONLY, retry_count=-1),
        ExecutionRequest(Capability.READ_ONLY, retry_count=3),
    ):
        assert policy.evaluate(request).decision is PolicyDecision.DENY
