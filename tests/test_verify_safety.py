from __future__ import annotations


class FakeResult:
    def __init__(self, record):
        self.record = record

    def single(self):
        return self.record


class FakeSession:
    def __init__(self, record=None, error: Exception | None = None):
        self.record = record
        self.error = error
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def run(self, query, **params):
        self.calls.append((query, params))
        if self.error is not None:
            raise self.error
        return FakeResult(self.record)


class FakeDriver:
    def __init__(self, record=None, error: Exception | None = None):
        self.session_obj = FakeSession(record, error)

    def session(self):
        return self.session_obj


def test_check_sc_001_fails_when_beliefs_lack_provenance():
    from scripts import verify_safety

    result = verify_safety.check_sc_001(FakeDriver({"orphaned_beliefs": 2}))

    assert result["status"] == verify_safety.FAIL
    assert "2" in result["detail"]


def test_check_sc_006_passes_when_schema_version_is_current():
    from scripts import verify_safety
    from world_models.schema_version import CURRENT_SCHEMA_VERSION

    result = verify_safety.check_sc_006(
        FakeDriver({"version": CURRENT_SCHEMA_VERSION}),
        expected_version=CURRENT_SCHEMA_VERSION,
    )

    assert result["status"] == verify_safety.PASS


def test_check_sc_004_warns_when_apoc_is_unavailable():
    from scripts import verify_safety

    result = verify_safety.check_sc_004(
        FakeDriver(error=RuntimeError("There is no procedure with the name apoc.path.expandConfig"))
    )

    assert result["status"] == verify_safety.WARN
    assert "APOC" in result["detail"]


def test_healthcheck_safety_contract_fails_when_verifier_fails():
    from scripts import healthcheck

    healthcheck.results.clear()

    healthcheck.check_safety_contract(
        neo4j_reachable=True,
        safety_runner=lambda: [
            {"status": healthcheck.FAIL, "name": "SC-001", "detail": "bad graph"},
        ],
    )

    assert healthcheck.results[-1]["status"] == healthcheck.FAIL
    assert "SC-001" in healthcheck.results[-1]["detail"]


def test_healthcheck_safety_contract_warns_when_neo4j_unreachable():
    from scripts import healthcheck

    healthcheck.results.clear()

    healthcheck.check_safety_contract(neo4j_reachable=False)

    assert healthcheck.results[-1]["status"] == healthcheck.WARN
    assert "skipped" in healthcheck.results[-1]["detail"]
