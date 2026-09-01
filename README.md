# codebase-companion

Point it at a repo, get a map of what's in it and where the important code lives.

## The problem

Joining an unfamiliar codebase means opening two hundred files to find the ten
that matter. The README tells you what the project does, not where anything is.
Folder names lie. `utils/` could be three helpers or half the application.

## What it does

- Walks the repo and keeps only the files worth reading.
- Summarises each file in a few lines: what it does, what it exports, what it needs.
- Rolls those up into a summary per folder.
- Builds an import graph to find the files everything else depends on.
- Writes it all to `REPO_MAP.md`.

## Example output

<!-- TODO: paste real REPO_MAP.md output here once v1 runs -->

```
(sample output goes here)
```

## Usage

```bash
pip install -r requirements.txt
python main.py <path-or-url>
```

## How it works

**File selection.** One `os.walk` pass that prunes directories before descending,
so `.git` and `node_modules` are never opened rather than opened and discarded.

**Summarising.** One LLM call per file. Results are cached by file hash, so a
second run only pays for what changed.

**Finding the core.** Import counts, not guesswork. The modules imported most
often are the ones the project is built around.

## Design notes

**Pruning beats filtering.** `Path.rglob("*")` is lazy but not selective. It
descends into `.git` regardless and you filter afterwards, by which point you
have already paid to visit every entry.

**Extension blocklists fail open.** Listing the extensions you don't want means
anything unanticipated gets through. TensorBoard writes files ending in `.0`,
which no blocklist predicts. Skipping the folder catches what the extension
cannot.

**Directory names are not evidence.** `.git` and `__pycache__` are created and
maintained by a tool, so the name guarantees the contents. `build`, `out` and
`env` are names a person chose, and a repo can legitimately keep real work
there. A virtualenv is recognised by the `pyvenv.cfg` inside it, not by being
called `venv`.

## Status

v1 in progress: repo map.

Planned:
- Q&A over the codebase with file and line citations
- Documentation drift detection: flag docs that no longer match the code

## Built with

Python, `os.walk`, Anthropic API.
