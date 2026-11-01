# PR #8: First isolated AI code-editing smoke test

Run from the repository root, after installing dependencies and Codex CLI:

```bash
uv run sf dev-smoke
```

The command copies the **bundled calculator fixture only** into a disposable
temporary directory, asks Codex to implement `add(a, b)` with
`workspace-write` permissions, checks that **only calculator.py** changed,
and runs the bundled unittest tests. The temporary directory is removed after
execution. No commits, pushes, PRs or deployments are performed.

**Security:** This is an opt-in local experiment, not a general-purpose secure
sandbox. Codex may have access to inherited credentials and network depending
on its host configuration. Do not run it with secrets or on company projects.
The file-change allowlist is checked **after** execution and is not a
preventive filesystem security boundary. Test code execution is safe here
because the fixture and test files are bundled and unchanged. Future work must
provide stronger process isolation before accepting arbitrary repositories.
