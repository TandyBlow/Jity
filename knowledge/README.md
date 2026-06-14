# Knowledge Base

This folder contains JSON and Markdown knowledge used by the FastAPI RAG layer.

Primary sources:

- `npcs.json`: NPC profiles and behavior notes.
- `locations.json`: Places that can be retrieved by scene or action.
- `quests.json`: Quest templates and investigation hooks.
- `rules.md`: GM rules, constraints, and mechanical guidance.
- `world_lore.md`: Setting facts and long-running lore.

JSON entries should include:

- `source_type`: one of `npc`, `location`, `quest`, `rule`, or `world_lore`.
- `title`: display title for the chunk.
- `keywords`: terms that should improve exact-match retrieval.
- `content`: text sent to the prompt and shown in RAG hits.
- `importance`: optional integer from 1 to 5.

Markdown files are split by headings. Each section can include metadata lines directly after the heading:

```md
## 临时通行卡权限规则

source_type: rule
keywords: 临时通行卡, 通行卡, 权限
importance: 5

Section content...
```

The backend also loads the root `RULEBOOK.md` as a Markdown knowledge source when it exists.
