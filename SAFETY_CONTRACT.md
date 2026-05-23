# Gopher-bot Safety Contract

This contract is versioned. Changes require a proposal with human approval, following the same process as Doctrine changes.

Version: 1

This contract defines runtime invariants the world model graph must always satisfy. It is separate from governance, which decides who may act, and testing, which checks whether code behaves as expected.

---

**SC-001 — Epistemic chain requires provenance**
- Invariant: Every Belief node must have at least one incoming edge from a Claim or Source node. A Belief without provenance is inadmissible.
- Why: Durable beliefs must be grounded in evidence or recorded source material, not introduced as unsupported assertions.
- Enforced by: verify_safety.py check `check_sc_001`

**SC-002 — Doctrine requires approved proposal**
- Invariant: Every Doctrine node must be linked to a Proposal node with status APPROVED. Doctrine without governance approval must not exist in the graph.
- Why: Doctrine is a high-level governance structure and must only enter the graph through explicit human-approved proposal flow.
- Enforced by: verify_safety.py check `check_sc_002`

**SC-003 — Principle elevation requires Belief support**
- Invariant: Every Principle node must be reachable from at least one Belief node. A Principle with no epistemic support is a floating assertion.
- Why: Principles should be elevated from supported beliefs rather than created independently of the epistemic chain.
- Enforced by: verify_safety.py check `check_sc_003`

**SC-004 — Epistemic chain is acyclic**
- Invariant: The directed subgraph of Source -> Claim -> Belief -> Principle -> Doctrine edges must contain no cycles.
- Why: Cycles make provenance and elevation ambiguous, preventing a clear account of what supports what.
- Enforced by: verify_safety.py check `check_sc_004`

**SC-005 — Audit log entries are complete**
- Invariant: Every AuditEntry node must have non-null values for coordinator_id, action, and timestamp fields. Entries missing any of these are invalid.
- Why: Audit entries without actor, action, or time cannot support accountability or reconstruction.
- Enforced by: verify_safety.py check `check_sc_005`

**SC-006 — Schema version is current**
- Invariant: The graph's SchemaVersion node version must equal the codebase's CURRENT_SCHEMA_VERSION. A mismatch indicates an unapplied migration.
- Why: Runtime code must not operate against an older or newer graph schema than the one it was built to understand.
- Enforced by: verify_safety.py check `check_sc_006`

**SC-007 — Blacklisted actions are unexecuted**
- Invariant: No AuditEntry node with a blacklisted action name from BLACKLIST_ACTIONS in coordinators/hands_policy.py may exist in the graph. If one does, the audit log has been corrupted.
- Why: Blacklisted actions are prohibited by policy; their presence in the audit graph is evidence of an invalid or tampered action history.
- Enforced by: verify_safety.py check `check_sc_007`
