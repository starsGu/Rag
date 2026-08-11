# OpenSpec project instructions

The following rules are mandatory throughout the complete OpenSpec workflow, including exploration, proposal creation, design, specification authoring, task planning, implementation, spec synchronization, and archiving.

## User-owned `plan/` directory

- Treat `plan/` as user-owned and authoritative for detailed implementation constraints.
- Keep `plan/` read-only by default. Do not create, edit, delete, rename, or move anything under `plan/` on the AI's own initiative.
- The AI may discuss a plan and provide suggestions in conversation. It may polish wording in a plan file only when the user explicitly requests that edit; preserve every technical meaning, constraint, and decision. If a wording change could alter meaning, ask the user instead.
- Before writing or changing a Python source file, an OpenSpec artifact, or a task that concerns that file, read the matching plan file when it exists and follow it.
- If a required implementation decision is absent from the matching plan, provide a suggestion and ask the user to decide; do not write the decision into `plan/` or silently treat the suggestion as approved.
- If source code or an OpenSpec artifact conflicts with a matching plan, stop and report the conflict. Do not resolve it by changing the plan or ignoring it.

## Directory correspondence

Use one unchanged relative path for all representations of a Python module:

```text
plan/<relative-path>.txt
<relative-path>.py
openspec/specs/<relative-path>/spec.md
openspec/changes/<change-name>/specs/<relative-path>/spec.md
```

For example:

```text
plan/a/b/c.txt
a/b/c.py
openspec/specs/a/b/c/spec.md
openspec/changes/<change-name>/specs/a/b/c/spec.md
```

- Treat any OpenSpec `specs/<relative-path>/spec.md` path, whether in the main specs or inside a change, as representing `<relative-path>.py` and `plan/<relative-path>.txt`.
- Preserve directory names, filename stems, and case. Do not flatten, rename, or substitute a capability-style directory that breaks this mapping.
- Before creating or modifying a source file or spec, derive and check all corresponding paths.
- Never create a missing plan file. If implementation requires a plan that does not exist, report the missing path and ask the user to maintain it before proceeding.

