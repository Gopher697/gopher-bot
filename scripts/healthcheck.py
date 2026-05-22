"""
healthcheck.py — "Is it safe to wake up?"

Checks the gopher-bot environment before starting the system.
Prints a structured pass/warn/fail report and exits 0 (all clear),
1 (warnings only), or 2 (hard failures present).

Usage:
    python scripts/healthcheck.py
    python scripts/healthcheck.py --fail-fast   # stop at first failure
    python scripts/healthcheck.py --json        # machine-readable output
"""

from __future__ import annotations

import argparse
import importlib
import json
import socket
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Report primitives
# ---------------------------------------------------------------------------

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

results: list[dict] = []


def check(status: str, name: str, detail: str = "") -> None:
    results.append({"status": status, "name": name, "detail": detail})
    icon = {"PASS": "  OK  ", "WARN": " WARN ", "FAIL": " FAIL "}[status]
    line = f"[{icon}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_python_version() -> None:
    v = sys.version_info
    if v >= (3, 11):
        check(PASS, "Python version", f"{v.major}.{v.minor}.{v.micro}")
    elif v >= (3, 10):
        check(WARN, "Python version", f"{v.major}.{v.minor}.{v.micro} (3.11+ recommended)")
    else:
        check(FAIL, "Python version", f"{v.major}.{v.minor}.{v.micro} — 3.10+ required")


def check_required_modules() -> None:
    required = [
        ("anthropic",      "pip install anthropic"),
        ("openai",         "pip install openai"),
        ("flask",          "pip install flask"),
        ("flask_socketio", "pip install flask-socketio"),
        ("flask_sock",     "pip install flask-sock"),
        ("flask_cors",     "pip install flask-cors"),
        ("neo4j",          "pip install neo4j"),
        ("pydantic",       "pip install pydantic"),
    ]
    optional = [
        ("mss",            "pip install mss  [vision]"),
        ("cv2",            "pip install opencv-python  [vision]"),
        ("ultralytics",    "pip install ultralytics  [vision]"),
        ("whisper",        "pip install openai-whisper  [audio]"),
        ("PySide6",        "pip install PySide6  [world-map UI]"),
    ]
    for mod, hint in required:
        try:
            importlib.import_module(mod)
            check(PASS, f"Module: {mod}")
        except ImportError:
            check(FAIL, f"Module: {mod}", f"missing — {hint}")

    for mod, hint in optional:
        try:
            importlib.import_module(mod)
            check(PASS, f"Module: {mod} (optional)")
        except ImportError:
            check(WARN, f"Module: {mod} (optional)", f"not installed — {hint}")


def check_config_loaded() -> None:
    config_path = REPO_ROOT / "world_models" / "config.py"
    if not config_path.exists():
        check(FAIL, "Config file", "world_models/config.py not found — copy from config.example.py")
        return
    try:
        import world_models.config as cfg
        # Verify required attributes exist without printing values
        required_attrs = ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "ANTHROPIC_API_KEY"]
        missing = [a for a in required_attrs if not getattr(cfg, a, None)]
        if missing:
            check(FAIL, "Config file", f"missing required attrs: {', '.join(missing)}")
        else:
            check(PASS, "Config file", "loaded (values hidden)")
    except Exception as e:
        check(FAIL, "Config file", f"import error: {e}")


def check_secrets_not_tracked() -> None:
    try:
        result = subprocess.run(
            ["git", "ls-files", "world_models/config.py", ".env"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        tracked = result.stdout.strip()
        if tracked:
            check(FAIL, "Secrets in git", f"tracked files: {tracked} — remove immediately")
        else:
            check(PASS, "Secrets not tracked by git")
    except FileNotFoundError:
        check(WARN, "Secrets git check", "git not found on PATH — skipped")


def check_neo4j_reachable() -> None:
    try:
        import world_models.config as cfg
        uri = getattr(cfg, "NEO4J_URI", "neo4j://127.0.0.1:7687")
        # Parse host/port from URI
        host = "127.0.0.1"
        port = 7687
        if "://" in uri:
            parts = uri.split("://")[1].split(":")
            host = parts[0]
            if len(parts) > 1:
                port = int(parts[1].split("/")[0])
        sock = socket.create_connection((host, port), timeout=3)
        sock.close()
        check(PASS, "Neo4j port reachable", f"{host}:{port}")
    except (ConnectionRefusedError, TimeoutError, OSError):
        check(WARN, "Neo4j port reachable", "not reachable — start the database before running the bot")
    except Exception as e:
        check(WARN, "Neo4j port reachable", f"check failed: {e}")


def check_web_port() -> None:
    port = 5000
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=1)
        sock.close()
        check(WARN, f"Web port {port}", "already in use — another instance may be running")
    except (ConnectionRefusedError, TimeoutError, OSError):
        check(PASS, f"Web port {port}", "free")


def check_coordinators_importable() -> None:
    # Import individual modules to avoid the __init__.py chain which requires
    # runtime dependencies (neo4j running, etc.)
    core_modules = [
        "coordinators.base",
        "coordinators.tier_config",
        "coordinators.hands_policy",
        "coordinators.percepts",
        "coordinators.bid",
    ]
    for mod in core_modules:
        try:
            importlib.import_module(mod)
            check(PASS, f"Import: {mod}")
        except Exception as e:
            check(FAIL, f"Import: {mod}", str(e))


def check_hands_policy() -> None:
    try:
        from coordinators.hands_policy import classify_action, WHITELIST_ACTIONS
        # Verify default-deny is in effect
        decision = classify_action("unknown_test_action_xyz", {})
        if decision.policy_class == "greylist":
            check(PASS, "Hands policy default-deny", "unknown actions → greylist")
        else:
            check(FAIL, "Hands policy default-deny",
                  f"unknown action returned {decision.policy_class!r} — expected greylist")
        # Verify mouse_move is NOT on the whitelist
        if "mouse_move" not in WHITELIST_ACTIONS:
            check(PASS, "Hands policy mouse_move", "correctly on greylist")
        else:
            check(FAIL, "Hands policy mouse_move", "still on whitelist — apply Ticket 3 fix")
    except Exception as e:
        check(FAIL, "Hands policy", f"import error: {e}")


def check_vision_sensor() -> None:
    try:
        import coordinators.vision_sensor as vs_mod
        has_mss  = getattr(vs_mod, "has_mss",  False)
        has_cv2  = getattr(vs_mod, "has_cv2",  False)
        has_yolo = getattr(vs_mod, "has_yolo", False)
        if has_mss and has_cv2 and has_yolo:
            check(PASS, "VisionSensor", "all backends available")
        elif has_mss:
            check(WARN, "VisionSensor", "partial — mss OK, cv2/YOLO missing (vision extras not installed)")
        else:
            check(WARN, "VisionSensor", "degraded — no vision backends (install vision extras for full sensing)")
    except Exception as e:
        check(WARN, "VisionSensor", f"import failed: {e}")


def check_config_validity() -> None:
    try:
        from utils.config_validator import validate_config
        issues = validate_config()
        fails = [i for i in issues if i.severity == "fail"]
        warns = [i for i in issues if i.severity == "warn"]
        if not issues:
            check(PASS, "Config validity", "API keys and model names look correct")
        else:
            for issue in fails:
                check(FAIL, f"Config: {issue.field}", issue.detail)
            for issue in warns:
                check(WARN, f"Config: {issue.field}", issue.detail)
    except Exception as e:
        check(FAIL, "Config validity", f"validator error: {e}")


def check_git_state() -> None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        dirty = result.stdout.strip()
        if dirty:
            lines = dirty.splitlines()
            check(WARN, "Git working tree", f"{len(lines)} uncommitted change(s) — commit before major work")
        else:
            check(PASS, "Git working tree", "clean")
    except FileNotFoundError:
        check(WARN, "Git state", "git not found on PATH — skipped")


def check_export_script() -> None:
    script = REPO_ROOT / "scripts" / "export_safe_zip.py"
    if not script.exists():
        check(FAIL, "Safe export script", "scripts/export_safe_zip.py missing — secrets may escape in zips")
        return
    try:
        import io
        import contextlib
        from scripts.export_safe_zip import verify_exclusions
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = verify_exclusions()
        if ok:
            check(PASS, "Safe export exclusions", "all secret patterns verified")
        else:
            check(FAIL, "Safe export exclusions", "some secret patterns not excluded — check scripts/export_safe_zip.py")
    except Exception as e:
        check(FAIL, "Safe export script", f"error: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Gopher-bot environment health check")
    parser.add_argument("--fail-fast", action="store_true", help="Stop at first failure")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable")
    args = parser.parse_args()

    if not args.json:
        print("=" * 60)
        print("  Gopher-bot Health Check")
        print("=" * 60)

    checks = [
        check_python_version,
        check_required_modules,
        check_config_loaded,
        check_config_validity,
        check_secrets_not_tracked,
        check_neo4j_reachable,
        check_web_port,
        check_coordinators_importable,
        check_hands_policy,
        check_vision_sensor,
        check_git_state,
        check_export_script,
    ]

    for fn in checks:
        fn()
        if args.fail_fast and results and results[-1]["status"] == FAIL:
            break

    # Summary
    passes = sum(1 for r in results if r["status"] == PASS)
    warns  = sum(1 for r in results if r["status"] == WARN)
    fails  = sum(1 for r in results if r["status"] == FAIL)

    if args.json:
        print(json.dumps({"results": results, "summary": {"pass": passes, "warn": warns, "fail": fails}}, indent=2))
        sys.exit(2 if fails else 1 if warns else 0)

    print()
    print("=" * 60)
    print(f"  {passes} passed  |  {warns} warnings  |  {fails} failed")
    if fails:
        print("  STATUS: NOT SAFE TO START — fix failures above")
        sys.exit(2)
    elif warns:
        print("  STATUS: OK with warnings — review above before starting")
        sys.exit(1)
    else:
        print("  STATUS: ALL CLEAR — safe to start")
        sys.exit(0)


if __name__ == "__main__":
    main()
