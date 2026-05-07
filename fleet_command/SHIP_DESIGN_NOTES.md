# Ship Design Notes

Future ships should be designed as isolated command systems with their own
local operating memory and validation boundaries.

## Ship Isolation

- Ships should have isolated registries, tools, prompts, model profiles,
  validation gates, and local mission history.
- Ship-local knowledge should stay with the ship unless a structured report
  promotes a reusable lesson to Fleet Command.
- Ship registries should distinguish local capabilities, callable tools,
  manual surfaces, blockers, and trust gates.

## Crew Isolation

- Crew agents should have role-specific prompts, tools, skills, failure notes,
  and output standards.
- Crew outputs should return through the ship command interface rather than
  expecting the Fleet Commander to reconcile raw tool output.
- Crew members, tools, and models should not be treated as trusted merely
  because they are callable.

## Fleet Relationship

- Fleet Command should not directly micromanage ship-local operations unless
  requested or safety requires escalation.
- Fleet Command should have its own knowledgebase, skills, and tools for
  fleet coordination, doctrine extraction, commissioning review, and future
  ship design.
- Fleet Command should receive reports, extract reusable lessons, and update
  fleet doctrine only when the lesson applies beyond one ship-local situation.
- Future ships should be designed using lessons from Starship Command's
  drydock and commissioning.
