# Research Influences

Projects and papers mined for architectural ideas during gopher-bot development.
Each entry notes what was taken and what was consciously left behind.

---

## H-MEM: Hybrid Tree+Graph Memory
**Source:** arXiv 2605.15701v1 — Yu, Fang, Liu, Ma (CUHK Shenzhen / Huawei Cloud), May 2026  
**YouTube overview:** https://youtu.be/LWmo_O10mag?si=l4LiZLoD5z14WcJ7

### What it validated
H-MEM is the only surveyed memory architecture achieving both temporal evolution (newer beliefs supersede contradicted older ones) and multi-hop reasoning. Gopher-bot's Neo4j graph + vector retrieval already covers the multi-hop and retrieval sides. The paper confirmed the design is on the right track.

### Gap it identified
Gopher-bot accumulates Observation nodes without principled contradiction suppression. Newer and older contradicted beliefs coexist; retrieval returns whichever wins vector similarity. H-MEM's temporal-semantic tree layer is the reference model for what Dream CONSOLIDATE should eventually do when it deprecates contradicted nodes.

### Ideas taken
- Dream CONSOLIDATE design: must suppress contradicted Observations, not just reinforce consistent ones (deferred — design work needed)
- Validation that the epistemic chain (Source → Claim → Belief → Principle → Doctrine) is the right shape for temporal consolidation

### Ideas not taken
- The specific tree + graph hybrid index structure — gopher-bot's Neo4j graph already handles the graph layer; the tree layer is approximated by the epistemic chain

---

## Voyager: An Open-Ended Embodied Agent with Large Language Models
**Source:** github.com/MineDojo/Voyager — Wang et al. (NVIDIA / Caltech / UT Austin), 2023  
**arXiv:** 2305.16291

### What it is
Lifelong learning agent in Minecraft. Three systems: automatic curriculum for exploration, skill library of executable code retrieved by vector search, iterative self-verification loop (attempt → observe → "did I succeed?" → retry with error).

### Ideas taken
- **SkillNode procedure storage** — store executable procedures, not just labels; retrieve by vector search; reuse without re-reasoning (backlogged)
- **Hands self-verification loop** — after multi-step computer-use, screenshot + ask Reason if goal achieved; feed errors back; retry (backlogged)
- **Task decomposition for Hands** — decompose multi-step goals into checkpointed sub-goals; failure at step N retries from N (backlogged)
- **Directed curriculum** — replace undirected Curiosity bids with gap-driven practice proposals (backlogged, depends on SkillNode procedure storage)

### Ideas not taken
- Minecraft-specific game loop and open-world exploration mechanics — not applicable to desktop automation

---

## Hermes Agent (formerly OpenClaw)
**Source:** github.com/NousResearch/hermes-agent — Nous Research  
**Stars:** 168k (as of May 2026) — most-starred personal AI agent project

### What it is
Self-improving personal AI agent. Multi-platform gateway (Telegram, Discord, Slack, etc.), built-in skills system where skills self-improve during use, FTS5 session search + LLM summarization for cross-session recall, Honcho dialectic user modeling, cron scheduler, parallel subagents.

### Ideas taken
- **Skill self-improvement** — when a stored skill executes, capture outcome and update the procedure; skills compound rather than staying static (backlogged, depends on SkillNode procedure storage)
- **FTS5 session search as third retrieval lane** — exact phrase/name matching alongside recent episodic + vector semantic lanes (backlogged)
- **Dialectic user modeling** — Archivist proposes hypothesis Claims flagged unverified; verified/contradicted through follow-up (backlogged)
- **Knowledge persistence nudges** — Awareness fires Archivist bid on high-value mid-conversation claims rather than waiting for Dream NREM (backlogged)

### Ideas consciously left behind
- Using Hermes as the base and layering gopher-bot on top: rejected. Hermes uses flat file memory (MEMORY.md, USER.md) — no graph, no typed node epistemology, no confidence decay. The multi-coordinator brain (Dream, Drive, BrainLoop bid queue) doesn't exist in Hermes and can't be cleanly layered onto it. Hermes is also early beta on native Windows. Gopher-bot's graph + coordinator architecture is the architectural bet; swapping the base abandons it.
- Multi-platform gateway (Telegram, WhatsApp, Signal): not needed.
- Parallel subagents, trajectory compression: Phase 3+ territory.
