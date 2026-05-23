from __future__ import annotations

# Increment this when a migration script is added.
# The running database must match this version before the bot starts.
CURRENT_SCHEMA_VERSION: int = 1

# Authoritative list of node labels in the current schema.
# Update this list when adding a new label alongside a migration script.
KNOWN_NODE_LABELS: frozenset[str] = frozenset({
    "Entity",
    "Observation",
    "Episode",
    "LearningEpisode",
    "SystemEvent",
    "Media",
    "Goal",
    "Source",
    "Claim",
    "Belief",
    "Principle",
    "Doctrine",
    "Skill",
    "SchemaVersion",
})

# Authoritative list of fixed relationship types.
# Dynamic rel types validated by REL_TYPE_PATTERN are not listed here.
KNOWN_RELATIONSHIP_TYPES: frozenset[str] = frozenset({
    "OBSERVED",
    "DEPICTS",
    "PROCESSED",
    "YIELDS",
    "YIELDED",
    "SUPPORTS",
    "GROUNDS",
    "INSTANTIATES",
    "DEPENDS_ON",
    "BLOCKED_BY",
    "SPAWNED",
    "ADVANCES",
})
