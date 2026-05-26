"""
Hands policy engine.

Declares the whitelist / greylist / blacklist action taxonomy and provides
a classify_action() function. Kept separate from hands.py so the declarations
can be hoisted to a Tauri IPC invoke layer in Phase 2 without redesign.

Policy classes:
  whitelist  — safe, read-only or append-only to designated paths; Tier 1 can execute
  greylist   — file writes, subprocesses with args, external API calls;
               requires Awareness approval before executing
  blacklist  — irreversible or dangerous; blocked unconditionally; Gopher must
               be present for any exceptions

Rules applied in order (first match wins):
  1. Path-based blacklist checks (config.py, .env, credentials)
  2. Action-type blacklist
  3. Action-type greylist
  4. Action-type whitelist (explicit)
  5. Default: greylist  <- unknown action types are NEVER silently permitted
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

#: Action types that are always safe to execute without approval.
WHITELIST_ACTIONS: frozenset[str] = frozenset(
    {
        "read_file",
        "list_directory",
        "search_notes",
        "search_web",       # placeholder — real impl in future
        "append_note",      # append-only to designated notes path
        "screenshot",
        "locate_on_screen",
        "get_window_list",
        "swap_avatar_sprite",   # installs an asset into current/ and broadcasts to Godot
    }
)

#: Action types that require Awareness approval before executing.
GREYLIST_ACTIONS: frozenset[str] = frozenset(
    {
        "write_file",
        "run_command",
        "download_url",
        "left_click",
        "right_click",
        "double_click",
        "click_element",
        "click_bbox",
        "type_text",
        "key_press",
        "mouse_move",       # moved from whitelist — focus/move before type_text risks wrong-window input
        "focus_window",     # moved from whitelist — focus before greylist action must itself be approved
        "get_visible_elements",
        "click_label",
        "drag_to",
        "drag_element",
    }
)

#: Action types that are blocked unconditionally.
BLACKLIST_ACTIONS: frozenset[str] = frozenset(
    {
        "delete_file",
        "delete_directory",
        "run_rm",
        "overwrite_config",
    }
)

#: Path fragments that are always blacklisted regardless of action type.
BLACKLISTED_PATH_FRAGMENTS: tuple[str, ...] = (
    "world_models/config.py",
    "world_models\\config.py",
    "config.py",
    ".env",
    "credentials",
    "id_rsa",
    "id_ed25519",
)


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PolicyDecision:
    action_type: str
    policy_class: str          # "whitelist" | "greylist" | "blacklist"
    reason: str
    path: str | None = None    # normalized path if relevant, else None


def classify_action(action_type: str, args: dict[str, Any]) -> PolicyDecision:
    """
    Classify an action request and return a PolicyDecision.

    Args:
        action_type: The type of action being requested (e.g. "read_file").
        args:        The action arguments dict (e.g. {"path": "..."}).

    Returns:
        A PolicyDecision with policy_class of "whitelist", "greylist", or
        "blacklist" and a human-readable reason.
    """
    path = _extract_path(args)

    # Rule 1 — path-based blacklist (applies regardless of action type)
    if path is not None and _path_is_blacklisted(path):
        return PolicyDecision(
            action_type=action_type,
            policy_class="blacklist",
            reason=f"path contains a blacklisted fragment: {path!r}",
            path=path,
        )

    # Rule 2 — action-type blacklist
    if action_type in BLACKLIST_ACTIONS:
        return PolicyDecision(
            action_type=action_type,
            policy_class="blacklist",
            reason=f"action type {action_type!r} is unconditionally blacklisted",
            path=path,
        )

    # Rule 3 — action-type greylist
    if action_type in GREYLIST_ACTIONS:
        return PolicyDecision(
            action_type=action_type,
            policy_class="greylist",
            reason=f"action type {action_type!r} requires Awareness approval",
            path=path,
        )

    # Rule 4 — explicit whitelist
    if action_type in WHITELIST_ACTIONS:
        return PolicyDecision(
            action_type=action_type,
            policy_class="whitelist",
            reason=f"action type {action_type!r} is whitelisted",
            path=path,
        )

    # Rule 5 — default-deny: unknown action types require Awareness approval.
    # Unknown does NOT mean harmless — it means unreviewed. Add to WHITELIST_ACTIONS
    # or GREYLIST_ACTIONS once the action is understood and tested.
    return PolicyDecision(
        action_type=action_type,
        policy_class="greylist",
        reason=f"action type {action_type!r} not in taxonomy — defaulting to greylist (pending review)",
        path=path,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_path(args: dict[str, Any]) -> str | None:
    """Return the first path-like argument from args, normalised, or None."""
    raw = args.get("path") or args.get("file_path") or args.get("directory")
    if raw is None:
        return None
    return str(raw).replace("\\", "/")


def _path_is_blacklisted(path: str) -> bool:
    """Return True if the normalised path contains any blacklisted fragment."""
    normalised = path.replace("\\", "/").lower()
    for fragment in BLACKLISTED_PATH_FRAGMENTS:
        if fragment.replace("\\", "/").lower() in normalised:
            return True
    return False
