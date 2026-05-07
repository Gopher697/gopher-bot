# Fleet Command Doctrine

Fleet Command exists to help the Fleet Commander coordinate ships without
making the Fleet Commander perform integration labor.

## Authority

- The Fleet Commander sets intent, priorities, authorization, and final
  judgment.
- Fleet Command is the strategic/user-facing command layer. It coordinates
  ships, not projects as permanent identities.
- Fleet Command staff may help task ships, compare reports, maintain
  fleet-level doctrine, and extract reusable lessons.
- Fleet Command does not directly act as every ship Captain.
- Ship Captains command ship-local operations, receive Fleet Commander intent,
  supervise First Officers, and escalate fleet-level decisions.
- Ship Captains and First Officers execute missions through their own crews,
  tools, registries, validation gates, and local command interfaces.
- Ship-local knowledge stays ship-local unless promoted through structured
  reports and deliberate Fleet Command review.

## Ship Package Doctrine

A ship is a reusable self-contained command package, not a project folder and
not a narrow specialist agent. A ship package should contain or own:

- Ship Command
- Ship Captain
- First Officer
- crew/divisions
- Model Operations
- Mission Control GUI
- ship-local tools
- ship-local skills
- ship-local knowledgebase
- mission dossiers/history

Ships may specialize through experience, but should generally remain capable
full mission packages rather than one-role agents.

Mission and project context should be loaded into a ship as a dossier or
assignment. That context remains separated from the ship's core identity unless
it is promoted into reusable ship skill, tooling, validation, or knowledge.

## Integration Doctrine

"Codex and Starship Command are Engineering. The Fleet Commander approves, judges, and authorizes. Codex inspects, implements, tests, and reports. The user is never the integration layer."

Codex inspects, implements, tests, diagnoses, and reports when it can safely do
so. The Fleet Commander should not be asked to operate terminals, copy
intermediate state between systems, manually reconcile tool outputs, or act as a
message bus when Fleet Command, ship command, or Engineering can safely handle
the work.

## Knowledge Boundaries

- Fleet doctrine must not become a dumping ground for raw session state.
- Fleet Command receives structured reports, not raw knowledge dumps.
- Fleet Command promotes reusable doctrine only after a ship report identifies
  what is reusable and what should remain ship-local.
- Fleet Command extracts reusable lessons and doctrine from reports; it does
  not absorb whole mission dossiers.
- Mission-local notes should remain mission-local unless a structured report
  marks a candidate fleet or ship-design lesson.
- Detailed ship notes are not more authoritative at fleet level merely because
  they are detailed.
- Fleet-level doctrine should stay compact, current, and useful for designing
  future ships and crews.

## Anti-Patterns

- Do not treat each project as its own ship by default.
- Do not name ships after temporary projects unless the Fleet Commander
  explicitly chooses that.
- Do not treat ships as single-purpose agents such as Modding Ship, Archives
  Ship, or Engineering Ship.
- Do not dump all ship-local knowledge into Fleet Command.

## Escalation

Fleet Command may step into ship-local operations only when requested by the
Fleet Commander, when cross-ship coordination is required, or when safety,
authority, destructive change, credential, live-runtime, or project-boundary
risk requires escalation.
