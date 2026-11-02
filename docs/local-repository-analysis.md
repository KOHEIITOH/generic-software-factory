# Local Repository Analysis

The experimental `sf analyze` command sends a bounded text snapshot of one
explicitly selected local Git repository to the GitHub Copilot SDK. The SDK
session has an empty tool allowlist and runs in a separate empty temporary
directory; it does not receive the selected repository as its working
directory. Repository text is passed as prompt context, not stored in the
Factory task database or audit table.

Install the optional SDK dependency, authenticate with the local Copilot CLI,
then explicitly confirm that the repository may be sent:

```bash
uv sync --extra dev --extra copilot
copilot login
uv run sf analyze /path/to/repository --confirm-send
```

Only a path containing a `.git` directory or worktree `.git` file is accepted.
The command reads text files with supported source, documentation, and
configuration extensions. It excludes hidden and generated directories,
symlinks, likely-sensitive filenames, unsupported files, binary data, and
non-UTF-8 files. Files are opened relative to directory file descriptors with
no-follow flags so links inside the selected repository are not traversed.
Errors while reading the selected scope fail the analysis rather than falling
back to a broader scan.

The snapshot is bounded to 80 files, 32 KiB per file, 256 KiB total, 10,000
directory entries, 2,000 directories, and a depth of 32. The command reports
included files, exclusion counts, and any limits reached before printing the
analysis. A result may therefore describe only part of the repository.

Filename filters are only a precaution, not secret detection. Source and
configuration files can still contain secrets or confidential information.
Do not run this command on company or other sensitive code unless the relevant
organization permits sending its contents to Copilot. The empty tool allowlist
prevents SDK tool-based file and command access, but this is not OS-level
process isolation. The command does not edit the repository, create a Task or
Run, execute shell commands, create a PR, or provide a sandbox guarantee.
