from src.orchestrator.state_machine import OrchestratorStateMachine


def test_fsm_order_and_advance():
    fsm = OrchestratorStateMachine()
    assert fsm.current == "plan"
    assert fsm.remaining() == ["plan", "retrieve", "synthesize", "critique", "finalize"]

    assert fsm.advance() == "retrieve"
    assert fsm.current == "retrieve"
    assert fsm.advance() == "synthesize"
    assert fsm.advance() == "critique"
    assert fsm.advance() == "finalize"
    assert fsm.current == "finalize"
    assert fsm.advance() is None


def test_fsm_terminal_step():
    fsm = OrchestratorStateMachine()
    for step in fsm.ORDER:
        if step == "finalize":
            assert fsm.is_terminal(step) is True
        else:
            assert fsm.is_terminal(step) is False
