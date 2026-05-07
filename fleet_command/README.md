# Fleet Command

Fleet Command is the Fleet Commander's strategic and generally user-facing
command layer above individual ships. It exists to coordinate ships, task ships
directly or through Fleet staff, receive structured reports, extract reusable
doctrine, and improve future ship and crew designs without replacing
ship-local command.

Fleet Command is not itself a ship.

Ships are persistent, reusable, modular operating packages. A ship has its own
Ship Command, Ship Captain, First Officer, crew, Model Operations, Mission
Control GUI, tools, skills, validation gates, local knowledgebase, mission
dossiers, and mission history. A ship can receive different projects or
missions over time.

Projects are mission targets, dossiers, theaters, or assignments. Projects such
as WorldBox Xianni, 5D Chess Tools, Cultivation GSG, or D&D Aelarion should not
be treated as ships by default.

Starship Command is the current registered drydock ship package and
command-system prototype under Fleet Command. Its current package path is
`starship_command`; that path is not Fleet Command itself and is not a special
architectural exception.

Fleet Command does not absorb raw ship knowledge, raw session history, model
scratch work, ship-local mission dossiers, or ship-local mission memory. Ships
send structured reports. Fleet Command extracts reusable lessons from those
reports, promotes only fleet-level doctrine when warranted, and leaves
ship-local details with the ship unless a deliberate promotion path is used.

Fleet Command should remain light until the current drydock ship package is
commissioned. The current purpose is doctrine, boundaries, report formats,
lessons-learned intake, commissioning criteria, and the initial registry entry
for the current ship package.

Fleet Command may develop its own knowledgebase, skills, and tools, but those
assets should serve fleet coordination and doctrine extraction. They should not
become a warehouse for raw ship-local state.

This bootstrap is not autonomous fleet runtime, a dashboard redesign, model
testing, or Starship Command commissioning.

Future Fleet Command interfaces should eventually show ships visually, show
their activity and status, and allow the Fleet Commander to task ships directly
or route work through Fleet Command staff. That future surface should still
treat projects as missions/dossiers assigned to ships, not as ship identities.

## Phase Framing

```text
drydock -> commissioning -> exploration -> fleet
```

- Drydock: components exist, but the full command loop is not reliable.
- Commissioning: one real task can travel from order to routed crew/tool/model
  work to useful artifact and back through the command interface.
- Exploration: a commissioned ship can begin taking, revisiting, and reporting
  on real project missions and dossiers.
- Fleet: multiple ships and workspaces coordinate through Fleet Command.

## Current Phase

- Fleet Command: bootstrap / pre-fleet
- Starship Command: drydock
- Commissioned ships: none
