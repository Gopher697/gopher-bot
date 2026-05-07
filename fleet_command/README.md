# Fleet Command

Fleet Command is the Fleet Commander's strategic coordination layer above
individual ships. It exists to coordinate ships, receive structured reports,
extract reusable doctrine, and improve future ship and crew designs without
replacing ship-local command.

Starship Command is the first ship and remains in drydock. It is the first
command-system prototype under Fleet Command, not a mature fleet runtime.

Fleet Command does not absorb raw ship knowledge, raw session history, model
scratch work, or ship-local mission memory. Ships send structured reports.
Fleet Command extracts reusable lessons from those reports, promotes only
fleet-level doctrine when warranted, and leaves ship-local details with the
ship unless a deliberate promotion path is used.

Fleet Command should remain light until the first ship is commissioned. The
current purpose is doctrine, boundaries, report formats, lessons-learned
intake, commissioning criteria, and a first registry entry for Starship
Command.

Fleet Command may develop its own knowledgebase, skills, and tools, but those
assets should serve fleet coordination and doctrine extraction. They should not
become a warehouse for raw ship-local state.

This bootstrap is not autonomous fleet runtime, a dashboard redesign, model
testing, or Starship Command commissioning.

## Phase Framing

```text
drydock -> commissioning -> exploration -> fleet
```

- Drydock: components exist, but the full command loop is not reliable.
- Commissioning: one real task can travel from order to routed crew/tool/model
  work to useful artifact and back through the command interface.
- Exploration: a commissioned ship can begin mapping and working across real
  project territory.
- Fleet: multiple ships and workspaces coordinate through Fleet Command.

## Current Phase

- Fleet Command: bootstrap / pre-fleet
- Starship Command: drydock
- Commissioned ships: none
