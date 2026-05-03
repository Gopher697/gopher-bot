# AI Coding Loop

1. Read the request and inspect the relevant project context.
2. Check git status before editing.
3. Make the smallest coherent change.
4. Run targeted tests or the configured validation command.
5. Summarize changes, verification, gaps, and review items.

For repo-local text search, prefer the MCP `search_project_text(project, query, glob?)` tool over shelling out to `rg`. Use it for registered project searches. Only investigate shell `rg` directly when debugging the workbench/search tooling itself.
