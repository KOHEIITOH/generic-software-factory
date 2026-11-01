# Task / Run MVP (PR #7)

Local persistent orchestration. From repository root:

```bash
uv run sf task create "Reply with exactly HELLO"
uv run sf task show <task-id>
uv run sf task run <task-id> --runtime codex
uv run sf run show <run-id>
```

State is stored in `.sf-factory/factory.sqlite3`; each run receives an empty
`.sf-factory/workspaces/<run-id>` directory. Add `.sf-factory/` to local ignore
rules if needed. Do not commit its contents.

**Safety boundary:** Codex is read-only. Grok uses the existing adapter's
read-only tool policy; neither OS-level sandbox isolation nor network isolation
is guaranteed. Workspaces are empty, not copies of the target repository.
Do not use this MVP to process company source, secrets, or untrusted tasks.
No repository mutation, PR creation, approval, or autonomous recovery yet.
A process crash may leave a run marked `running`; future recovery work
will reconcile interrupted runs. SQLite audit records lifecycle events.
