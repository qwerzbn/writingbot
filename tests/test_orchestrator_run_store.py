from datetime import datetime, timedelta

from src.orchestrator.run_store import RunStore


def test_run_store_create_and_result():
    store = RunStore(ttl_hours=2)
    run = store.create_run(mode="research", payload={"topic": "hello"})
    assert run.run_id
    assert run.trace_id
    assert run.status == "pending"

    store.set_status(run.run_id, "running")
    current = store.get_run(run.run_id)
    assert current is not None
    assert current.status == "running"

    store.set_result(run.run_id, {"output": "ok"})
    done = store.get_run(run.run_id)
    assert done is not None
    assert done.status == "done"
    assert done.result["output"] == "ok"


def test_run_store_ttl_cleanup():
    store = RunStore(ttl_hours=2)
    run = store.create_run(mode="research", payload={"topic": "x"})
    assert store.get_run(run.run_id) is not None

    # Force expiration without waiting.
    run.expires_at = datetime.now() - timedelta(seconds=1)
    assert store.get_run(run.run_id) is None
