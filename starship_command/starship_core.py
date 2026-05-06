from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


BASE_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = BASE_DIR / "command_registry.yaml"
TEMPLATE_DIR = BASE_DIR / "templates"


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("command registry must be a YAML mapping")
    if "routing_rules" not in data:
        raise ValueError("command registry must define explicit routing_rules")
    return data


def normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def keyword_matches(text: str, keyword_weights: dict[str, int]) -> tuple[int, list[str]]:
    score = 0
    matches: list[str] = []
    for keyword, weight in keyword_weights.items():
        normalized_keyword = normalize(str(keyword))
        if normalized_keyword and normalized_keyword in text:
            score += int(weight)
            matches.append(str(keyword))
    return score, matches


def match_projects(task_text: str, registry: dict[str, Any]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for project in registry.get("known_projects", []):
        aliases = project.get("aliases", [])
        matched_aliases = [
            alias for alias in aliases if normalize(str(alias)) and normalize(str(alias)) in task_text
        ]
        if matched_aliases:
            project_match = dict(project)
            project_match["matched_aliases"] = matched_aliases
            matches.append(project_match)
    matches.sort(key=lambda item: (-max(len(alias) for alias in item["matched_aliases"]), item["name"]))
    return matches


def _has_any(text: str, phrases: list[str]) -> bool:
    return any(normalize(phrase) in text for phrase in phrases)


def route_task(task: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_registry()
    text = normalize(task)
    station_order = registry["station_order"]
    routing_rules = registry["routing_rules"]
    station_rules = routing_rules["stations"]
    risk_rules = registry["risk_keyword_rules"]

    station_scores: dict[str, dict[str, Any]] = {}
    for station in station_order:
        weights = station_rules.get(station, {}).get("keyword_weights", {})
        score, matches = keyword_matches(text, weights)
        station_scores[station] = {"score": score, "matches": matches}

    risk_score, risk_matches = keyword_matches(
        text,
        {keyword: 1 for keyword in risk_rules.get("risk_keywords", [])},
    )
    primary_review = _has_any(text, risk_rules.get("primary_review_phrases", []))
    repo_change = _has_any(text, routing_rules.get("repo_change_keywords", []))
    implementation_dominates = _has_any(text, routing_rules.get("implementation_dominance_keywords", []))
    archive_dominates = _has_any(text, routing_rules.get("archive_dominance_keywords", []))
    design_dominates = _has_any(text, routing_rules.get("design_dominance_keywords", []))
    game_dominates = _has_any(text, routing_rules.get("game_intelligence_dominance_keywords", []))
    modding_present = station_scores.get("modding", {}).get("score", 0) > 0

    low_confidence = False
    limitation_notes: list[str] = []
    non_tactical = [station for station in station_order if station != "tactical"]

    engineering_score = station_scores["engineering"]["score"]
    archives_score = station_scores["archives"]["score"]
    science_score = station_scores["science"]["score"]
    first_officer_score = station_scores["first_officer"]["score"]
    design_score = station_scores["design"]["score"]

    if primary_review and not repo_change:
        primary = "tactical"
    elif archive_dominates and archives_score >= engineering_score and archives_score > 0:
        primary = "archives"
    elif design_dominates and not archive_dominates and design_score > 0:
        primary = "design"
    elif game_dominates and science_score >= engineering_score and science_score > first_officer_score:
        primary = "science"
    elif implementation_dominates and engineering_score > 0:
        primary = "engineering"
    elif modding_present and not archive_dominates:
        primary = "modding"
    else:
        primary = max(
            non_tactical,
            key=lambda station: (station_scores[station]["score"], -station_order.index(station)),
        )

    if primary != "tactical" and station_scores[primary]["score"] < int(routing_rules.get("low_confidence_threshold", 1)):
        primary = "first_officer"
        low_confidence = True
        limitation_notes.append(
            "Low-confidence route: no division-specific signal met the configured threshold, so First Officer owns clarification."
        )

    supporting: list[str] = []
    for station in station_order:
        if station == primary or station == "tactical":
            continue
        if station_scores[station]["score"] > 0:
            supporting.append(station)

    if primary != "tactical" and risk_score > 0 and risk_rules.get("support_when_matched", True):
        supporting.append("tactical")
    if primary == "tactical":
        for station in non_tactical:
            if station_scores[station]["score"] > 0 and station not in supporting:
                supporting.append(station)

    supporting = sorted(
        dict.fromkeys(supporting),
        key=lambda station: (-station_scores[station]["score"], station_order.index(station)),
    )

    station_info = registry["stations"][primary]
    specialist_recommended = (
        not low_confidence
        and bool(station_info.get("specialist_default", False))
        and station_scores[primary]["score"] >= int(routing_rules.get("specialist_threshold", 1))
    )
    if primary == "tactical" and primary_review:
        specialist_recommended = True
    if primary == "first_officer" and station_scores[primary]["score"] >= int(
        routing_rules.get("specialist_threshold", 1)
    ):
        specialist_recommended = True
    if len(supporting) >= 2 or risk_score > 0 or modding_present:
        specialist_recommended = True

    if low_confidence:
        confidence = "low"
    elif station_scores[primary]["score"] >= 8 or primary == "tactical":
        confidence = "high"
    else:
        confidence = "medium"

    project_matches = match_projects(text, registry)
    return {
        "task": task,
        "primary_station": primary,
        "primary_station_name": station_info["display_name"],
        "primary_division_name": station_info.get("division_name", station_info["display_name"]),
        "standing_officer": station_info.get("standing_officer", station_info["display_name"]),
        "supporting_stations": supporting,
        "supporting_station_names": [registry["stations"][station]["display_name"] for station in supporting],
        "supporting_division_names": [
            registry["stations"][station].get("division_name", registry["stations"][station]["display_name"])
            for station in supporting
        ],
        "station_scores": station_scores,
        "risk_matches": risk_matches,
        "project_matches": project_matches,
        "specialist_recommended": specialist_recommended,
        "confidence": confidence,
        "low_confidence": low_confidence,
        "limitation_notes": limitation_notes,
        "repo_change": repo_change,
    }


def station_line(registry: dict[str, Any], station: str) -> str:
    info = registry["stations"][station]
    return (
        f"{info['display_name']} / {info.get('division_name', info['display_name'])} "
        f"(authority: {info['authority']}) - {info['mission']}"
    )


def format_project_matches(route: dict[str, Any]) -> str:
    if not route["project_matches"]:
        return "Known project: [[UNKNOWN: no configured project alias matched]]"
    lines = []
    for project in route["project_matches"]:
        entrypoints = ", ".join(project.get("entrypoints", []))
        aliases = ", ".join(project.get("matched_aliases", []))
        lines.append(
            f"- {project['display_name']} (`{project['name']}`, activity_status: {project.get('activity_status', 'unknown')}); "
            f"matched aliases: {aliases}; entrypoints: {entrypoints}"
        )
    return "\n".join(lines)


def required_context_lines(registry: dict[str, Any], route: dict[str, Any]) -> str:
    return "\n".join(f"- {line}" for line in required_context_items(registry, route))


def required_context_items(registry: dict[str, Any], route: dict[str, Any]) -> list[str]:
    defaults = registry["template_defaults"]
    lines = list(defaults.get("required_context", []))
    if route["project_matches"]:
        for project in route["project_matches"]:
            entrypoints = ", ".join(project.get("entrypoints", []))
            lines.append(f"{project['display_name']} entrypoints: {entrypoints}")
    else:
        lines.append(defaults["unknown_placeholder"])
    return lines


def bullet_lines(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def station_matches(route: dict[str, Any]) -> str:
    lines = []
    for station, result in route["station_scores"].items():
        if result["matches"]:
            lines.append(f"- {station}: {', '.join(result['matches'])}")
    return "\n".join(lines) if lines else "- [[UNKNOWN: no division keywords matched]]"


def render_template(path: Path, values: dict[str, str]) -> str:
    content = path.read_text(encoding="utf-8")
    for key, value in values.items():
        content = content.replace("{{ " + key + " }}", value)
        content = content.replace("{{" + key + "}}", value)
    return content


def template_values(task: str, registry: dict[str, Any], route: dict[str, Any]) -> dict[str, str]:
    defaults = registry["template_defaults"]
    station = registry["stations"][route["primary_station"]]
    support = ", ".join(route["supporting_station_names"]) if route["supporting_station_names"] else "None"
    git_status_instruction = (
        defaults["repo_change_git_status_instruction"] if route["repo_change"] else "Not required unless files change."
    )
    return {
        "limitation": defaults["limitation"],
        "unknown_placeholder": defaults["unknown_placeholder"],
        "no_agent_launched": defaults["no_agent_launched"],
        "mission": task,
        "primary_station": route["primary_station_name"],
        "primary_station_key": route["primary_station"],
        "primary_division": route["primary_division_name"],
        "standing_officer": route["standing_officer"],
        "supporting_stations": support,
        "station_mission": station["mission"],
        "authority": str(station["authority"]),
        "confidence": route["confidence"],
        "specialist_recommended": "yes" if route["specialist_recommended"] else "no",
        "matched_projects": format_project_matches(route),
        "matched_signals": station_matches(route),
        "required_context": required_context_lines(registry, route),
        "safety_boundaries": bullet_lines(defaults.get("safety_boundaries", [])),
        "expected_output": bullet_lines(defaults.get("expected_output", [])),
        "no_commit_boundary": defaults["no_commit_boundary"],
        "git_status_instruction": git_status_instruction,
        "retirement_condition": defaults["retirement_condition"],
        "escalation_rules": bullet_lines(defaults.get("escalation_rules", [])),
        "limitation_notes": "\n".join(f"- {note}" for note in route["limitation_notes"])
        if route["limitation_notes"]
        else "- None",
    }


def build_codex_prompt(task: str, registry: dict[str, Any] | None = None) -> str:
    registry = registry or load_registry()
    route = route_task(task, registry)
    return render_template(TEMPLATE_DIR / "codex_prompt.md", template_values(task, registry, route))


def build_specialist_brief(task: str, registry: dict[str, Any] | None = None) -> str:
    registry = registry or load_registry()
    route = route_task(task, registry)
    return render_template(TEMPLATE_DIR / "specialist_brief.md", template_values(task, registry, route))


def build_session_handoff(answers: dict[str, str], registry: dict[str, Any] | None = None) -> str:
    registry = registry or load_registry()
    defaults = registry["template_defaults"]
    values = {
        "limitation": defaults["limitation"],
        "project": answers.get("Project", ""),
        "mission": answers.get("Mission", ""),
        "date": answers.get("Stardate/Date", ""),
        "current_state": answers.get("Current State", ""),
        "open_threads": answers.get("Open Threads", ""),
        "next_action": answers.get("Next Action", ""),
        "suggested_next_station": answers.get(
            "Suggested Next Station",
            answers.get("Suggested Next Station/Division", ""),
        ),
    }
    return render_template(TEMPLATE_DIR / "session_handoff.md", values)


def format_route(route: dict[str, Any]) -> str:
    support = ", ".join(route["supporting_station_names"]) if route["supporting_station_names"] else "None"
    specialist = "yes" if route["specialist_recommended"] else "no"
    lines = [
        f"Mission: {route['task']}",
        f"Primary station: {route['primary_station_name']}",
        f"Primary division: {route['primary_division_name']}",
        f"Standing officer: {route['standing_officer']}",
        f"Supporting stations: {support}",
        f"Specialist recommended: {specialist}",
        f"Confidence: {route['confidence']}",
        "Matched project context:",
        format_project_matches(route),
        "Matched signals:",
        station_matches(route),
    ]
    if route["limitation_notes"]:
        lines.append("Limitations:")
        lines.extend(f"- {note}" for note in route["limitation_notes"])
    return "\n".join(lines)


def list_stations(registry: dict[str, Any]) -> str:
    return "\n".join(station_line(registry, station) for station in registry["station_order"])


def create_initial_state(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_registry()
    divisions = {}
    for station in registry["station_order"]:
        info = registry["stations"][station]
        divisions[station] = {
            "key": station,
            "name": info.get("division_name", info["display_name"]),
            "display_name": info["display_name"],
            "standing_officer": info.get("standing_officer", info["display_name"]),
            "authority": info["authority"],
            "mission": info["mission"],
            "responsibilities": list(info.get("responsibilities", [])),
            "status": "idle",
            "current_assignment": "",
            "specialists": [],
            "latest_output": "",
        }
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "divisions": divisions,
        "assignments": [],
        "output": "",
        "selected": {"type": "division", "id": registry["station_order"][0]},
    }


def state_snapshot(state: dict[str, Any], registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_registry()
    snapshot = deepcopy(state)
    snapshot["division_order"] = list(registry["station_order"])
    return snapshot


def add_route_assignment(state: dict[str, Any], task: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_registry()
    route = route_task(task, registry)
    output = format_route(route)
    assignment_id = f"A-{len(state['assignments']) + 1:03d}"
    record = {
        "id": assignment_id,
        "kind": "routed_mission",
        "mission": task,
        "primary_station": route["primary_station"],
        "primary_division": route["primary_division_name"],
        "supporting_stations": route["supporting_stations"],
        "supporting_divisions": route["supporting_division_names"],
        "status": "routed",
        "specialist_recommended": route["specialist_recommended"],
        "confidence": route["confidence"],
        "output": output,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    state["assignments"].insert(0, record)
    for station in [route["primary_station"], *route["supporting_stations"]]:
        division = state["divisions"][station]
        division["status"] = "routed" if station == route["primary_station"] else "assigned"
        division["current_assignment"] = task
        division["latest_output"] = output
    state["output"] = output
    state["selected"] = {"type": "assignment", "id": assignment_id}
    return {"route": route, "record": record, "output": output}


def deploy_specialist(state: dict[str, Any], task: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_registry()
    route = route_task(task, registry)
    brief = build_specialist_brief(task, registry)
    specialist_id = f"S-{sum(len(item['specialists']) for item in state['divisions'].values()) + 1:03d}"
    division = state["divisions"][route["primary_station"]]
    specialist = {
        "id": specialist_id,
        "name": f"{route['primary_station_name']} Specialist {specialist_id}",
        "division": route["primary_division_name"],
        "station": route["primary_station"],
        "role": "specialist",
        "mission": task,
        "authority": registry["stations"][route["primary_station"]]["authority"],
        "status": "assigned",
        "current_assignment": task,
        "required_context": required_context_items(registry, route),
        "latest_output": brief,
        "retirement_condition": registry["template_defaults"]["retirement_condition"],
        "note": registry["template_defaults"]["no_agent_launched"],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    division["specialists"].append(specialist)
    division["status"] = "assigned"
    division["current_assignment"] = task
    division["latest_output"] = brief
    assignment = {
        "id": f"A-{len(state['assignments']) + 1:03d}",
        "kind": "specialist_deployment",
        "mission": task,
        "primary_station": route["primary_station"],
        "primary_division": route["primary_division_name"],
        "supporting_stations": route["supporting_stations"],
        "supporting_divisions": route["supporting_division_names"],
        "status": "assigned",
        "specialist_id": specialist_id,
        "output": brief,
        "created_at": specialist["created_at"],
    }
    state["assignments"].insert(0, assignment)
    state["output"] = brief
    state["selected"] = {"type": "specialist", "id": specialist_id}
    return {"route": route, "specialist": specialist, "record": assignment, "output": brief}


def add_codex_order(state: dict[str, Any], task: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_registry()
    route = route_task(task, registry)
    output = build_codex_prompt(task, registry)
    assignment = {
        "id": f"A-{len(state['assignments']) + 1:03d}",
        "kind": "codex_mission_order",
        "mission": task,
        "primary_station": route["primary_station"],
        "primary_division": route["primary_division_name"],
        "supporting_stations": route["supporting_stations"],
        "supporting_divisions": route["supporting_division_names"],
        "status": "routed",
        "output": output,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    state["assignments"].insert(0, assignment)
    state["divisions"][route["primary_station"]]["status"] = "routed"
    state["divisions"][route["primary_station"]]["current_assignment"] = task
    state["divisions"][route["primary_station"]]["latest_output"] = output
    state["output"] = output
    state["selected"] = {"type": "assignment", "id": assignment["id"]}
    return {"route": route, "record": assignment, "output": output}


def add_handoff(state: dict[str, Any], answers: dict[str, str], registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_registry()
    output = build_session_handoff(answers, registry)
    assignment = {
        "id": f"A-{len(state['assignments']) + 1:03d}",
        "kind": "bridge_log_handoff",
        "mission": answers.get("Mission", "Bridge log / handoff"),
        "primary_station": "archives",
        "primary_division": registry["stations"]["archives"].get("division_name", "Computer Core / Archives"),
        "supporting_stations": [],
        "supporting_divisions": [],
        "status": "completed",
        "output": output,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    state["assignments"].insert(0, assignment)
    state["divisions"]["archives"]["status"] = "completed"
    state["divisions"]["archives"]["current_assignment"] = assignment["mission"]
    state["divisions"]["archives"]["latest_output"] = output
    state["output"] = output
    state["selected"] = {"type": "assignment", "id": assignment["id"]}
    return {"record": assignment, "output": output}
