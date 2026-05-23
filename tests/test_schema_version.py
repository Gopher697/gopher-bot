from __future__ import annotations

import io


class FakeResult:
    def __init__(self, record):
        self.record = record

    def single(self):
        return self.record


class FakeTx:
    def __init__(self, record=None):
        self.record = record
        self.calls = []

    def run(self, query, **params):
        self.calls.append((query, params))
        return FakeResult(self.record)


class FakeSession:
    def __init__(self, tx):
        self.tx = tx

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute_read(self, fn):
        return fn(self.tx)

    def execute_write(self, fn):
        return fn(self.tx)


class FakeDriver:
    def __init__(self, record=None):
        self.tx = FakeTx(record)
        self.session_kwargs = None

    def session(self, **kwargs):
        self.session_kwargs = kwargs
        return FakeSession(self.tx)


def test_get_schema_version_returns_none_when_no_node():
    from world_models import graph

    driver = FakeDriver(record=None)

    assert graph.get_schema_version(driver) is None


def test_get_schema_version_returns_integer_when_node_exists():
    from world_models import graph

    driver = FakeDriver(record={"version": 1})

    assert graph.get_schema_version(driver) == 1


def test_set_schema_version_calls_merge_with_correct_version():
    from world_models import graph

    driver = FakeDriver()

    graph.set_schema_version(driver, 1)

    query, params = driver.tx.calls[0]
    assert "MERGE (s:SchemaVersion)" in query
    assert params["version"] == 1
    assert "applied_at" in params


def test_migration_001_calls_set_schema_version(monkeypatch):
    from scripts.migrations import migrate_001_baseline

    calls = []
    driver = object()

    monkeypatch.setattr(
        "world_models.graph.set_schema_version",
        lambda passed_driver, version: calls.append((passed_driver, version)),
    )

    migrate_001_baseline.up(driver)

    assert calls == [(driver, 1)]


def test_migration_001_is_idempotent(monkeypatch):
    from scripts.migrations import migrate_001_baseline

    monkeypatch.setattr("world_models.graph.set_schema_version", lambda *_args: None)

    migrate_001_baseline.up(object())
    migrate_001_baseline.up(object())


def test_run_migrations_skips_already_applied():
    from scripts import run_migrations

    class Migration001:
        VERSION = 1
        DESCRIPTION = "Baseline schema stamp"

        @staticmethod
        def up(_driver):
            raise AssertionError("already-applied migration should not run")

    output = io.StringIO()

    exit_code = run_migrations.run_migrations(
        object(),
        migrations=[Migration001],
        current_version=1,
        out=output,
    )

    assert exit_code == 0
    assert "SKIP" in output.getvalue()


def test_healthcheck_warns_when_no_schema_version_node():
    from scripts import healthcheck

    healthcheck.results.clear()

    healthcheck.check_graph_schema_version(
        neo4j_reachable=True,
        driver_factory=lambda: object(),
        version_reader=lambda _driver: None,
    )

    assert healthcheck.results[-1]["status"] == healthcheck.WARN
    assert "Graph has no SchemaVersion node" in healthcheck.results[-1]["detail"]
    assert all(result["status"] != healthcheck.FAIL for result in healthcheck.results)


def test_healthcheck_fails_when_schema_version_behind():
    from scripts import healthcheck

    healthcheck.results.clear()

    healthcheck.check_graph_schema_version(
        neo4j_reachable=True,
        driver_factory=lambda: object(),
        version_reader=lambda _driver: 0,
        expected_version=1,
    )

    assert healthcheck.results[-1]["status"] == healthcheck.FAIL
    assert "behind expected 1" in healthcheck.results[-1]["detail"]
