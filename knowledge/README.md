# Knowledge Base

This folder contains JSON and Markdown knowledge used by the FastAPI RAG layer.

Supported formats:

- `.json`: list of entries with `title`, `source_type`, `keywords`, and `content`
- `.md`: split into chunks by headings

The backend also loads the root `RULEBOOK.md` as a Markdown knowledge source.
