# Repomix Packaging Playbook

## 1. Command reference

```text
--source [LABEL=]PATH        repository to pack; repeatable, label namespaces the paths
--output, -o PATH            output file
--style {xml,markdown,plain,json}
--config, -c PATH            load repomix.config.json
--include GLOB               only files matching; repeatable
--ignore GLOB                extra exclusions; repeatable
--no-gitignore               do not read .gitignore / .repomixignore
--no-default-patterns        do not apply the built-in ignore list
--compress                   keep only structural signatures
--remove-comments            strip comments from supported languages
--remove-empty-lines
--show-line-numbers
--no-truncate-base64         keep long base64 blobs (they are truncated by default)
--no-security-check          disable the credential scanner
--no-file-summary            omit the header block
--no-directory-structure     omit the tree
--directory-structure-only   tree only, no file contents
--header-text TEXT           a description embedded in the pack
--instruction-file PATH      appended as an <instruction> block
--top-files-len N            rows in the report table (default 20)
--max-file-size BYTES        skip files above this (default 2 MB)
--max-tokens-per-file N      split output into parts
--sort {path,size,tokens}
--quiet, -q
```

## 2. Recipes

**Just the API surface of a large Python library**

```bash
python scripts/repomix_pack_engine.py \
  --source qlib \
  --include "qlib/**/*.py" \
  --ignore "**/tests/**" --ignore "**/examples/**" \
  --compress --style xml \
  --output repomix_outputs/qlib_api.xml
```

**Documentation only, for a methodology question**

```bash
python scripts/repomix_pack_engine.py \
  --source ml4t=../machine-learning-for-trading \
  --include "*.md" --include "docs/**/*.md" --include "**/README.md" \
  --style markdown \
  --output repomix_outputs/ml4t_docs.md
```

**A map before deciding what to pack**

```bash
python scripts/repomix_pack_engine.py \
  --source Lean --directory-structure-only \
  --output repomix_outputs/lean_tree.xml
```

**Everything, split into context-sized parts**

```bash
python scripts/repomix_pack_engine.py \
  --source . --compress \
  --max-tokens-per-file 150000 \
  --output repomix_outputs/suite.xml
```

**Multi-repository with labelled paths**

```bash
python scripts/repomix_pack_engine.py \
  --source qlib=./qlib --source vbt=./vectorbt --source lean=./Lean \
  --include "**/*.py" --compress \
  --header-text "Alpha and execution stack for the MindsHub suite" \
  --instruction-file repomix-instruction.md \
  --output repomix_outputs/stack.xml
```

Paths inside that pack appear as `qlib/qlib/data/ops.py`, `vbt/vectorbt/portfolio/base.py`
and so on, so an agent can cite them unambiguously.

## 3. Config file

`repomix.config.json` at the repository root:

```json
{
  "output": {
    "filePath": "repomix_outputs/suite.xml",
    "style": "xml",
    "fileSummary": true,
    "directoryStructure": true,
    "files": true,
    "removeComments": false,
    "removeEmptyLines": false,
    "showLineNumbers": false,
    "truncateBase64": true,
    "compress": false,
    "topFilesLength": 20,
    "headerText": "MindsHub Quant Master Suite",
    "instructionFilePath": "repomix-instruction.md"
  },
  "include": ["**/*.py", "**/*.md"],
  "ignore": {
    "useGitignore": true,
    "useDefaultPatterns": true,
    "customPatterns": ["**/tests/**", "**/*.csv", "repomix/**"]
  },
  "security": { "enableSecurityCheck": true },
  "sources": [
    { "label": "suite", "path": "." },
    { "label": "qlib", "path": "qlib" }
  ]
}
```

The `sources` key is an extension over upstream repomix, which packs one root. Command
line flags override config values.

## 4. Reading the report

```text
Top 5 files by estimated token count:
    1. qlib/qlib/data/ops.py            12,430 tokens   1,204 lines
    ...

Summary:
  Files packed     : 612
  Files skipped    : binary=41 oversize=3 secrets=1
  Total characters : 4,182,993
  Estimated tokens : 1,046,112
  Compression      : on
  Output           : repomix_outputs/stack.xml  (4,084.6 KB)

  [security] files withheld because a credential pattern matched:
    - suite/tests/fixtures/config.yaml  (generic_secret)
```

Act on three lines. **Estimated tokens** against your context window decides whether to
compress or split. **Top files** shows where the budget goes, and usually one or two
files dominate and can be excluded. **Withheld files** must be checked: either the
match is a real credential that should not be in the repository at all, or it is a
fixture you can exclude explicitly.

## 5. Token budgeting

The estimator blends characters over four with a token-like word count, which lands
within roughly 10% of `tiktoken` on source code. For exact counts:

```python
import tiktoken
enc = tiktoken.get_encoding("o200k_base")
print(len(enc.encode(open("repomix_outputs/stack.xml", encoding="utf-8").read())))
```

Practical budgets for a 200k-token window, leaving room for the conversation:

| Content | Approximate tokens |
|---|---|
| awesome-quant README alone | 30k |
| Qlib Python, compressed | 60-80k |
| vectorbt Python, compressed | 50-70k |
| LEAN framework plus Python examples, compressed | 80-100k |
| ML4T markdown and utilities | 70-90k |
| This suite's skills and rules | 40-60k |

Two compressed repositories plus the suite skills is a realistic maximum for a single
window.

## 6. What compression keeps and drops

For Python, the `ast` module extracts module docstring first line, top-level imports,
class definitions with base classes and the first docstring line, method and function
signatures with decorators and the first docstring line, and top-level assignments
under 300 characters. Function bodies become `...`.

```python
class DataHandlerLP(DataHandler):
    """Data handler with layered preprocessing."""
    def __init__(self, instruments=None, start_time=None, end_time=None, ...):
        """Initialise the handler."""
        ...
⋮----
```

Dropped: all implementation, comments, and any docstring beyond its first line.

Use compression when the question is "what is the API". Do not use it when the question
is "why does this function behave this way", because the answer is in the body you just
removed.

## 7. Keeping packs fresh

```bash
# after pulling any upstream repository
python scripts/build_quant_agents_suite.py --packs

# check whether a pack is stale
python - <<'PY'
import hashlib, json, pathlib
m = json.loads(pathlib.Path("repomix_outputs/suite.xml.manifest.json").read_text())
cur = hashlib.sha256(pathlib.Path(m["outputs"][0]).read_bytes()).hexdigest()
print("unchanged" if cur == m["sha256"][0] else "output edited since generation")
PY
```

Put the manifest under version control and the pack itself in `.gitignore`. The
manifest records what was packed and when; the pack is a derived artefact.

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `no files matched the selection` | an `--include` glob that matches nothing | test with `--directory-structure-only` first |
| Pack far larger than expected | CSVs, JSON fixtures or generated HTML | add `--ignore "**/*.csv"`, check the top-files table |
| A needed file is missing | caught by `.gitignore` or the default patterns | `--no-gitignore`, or an explicit `--include` |
| A file was withheld for secrets | a real or fake credential in the file | remove the credential, or exclude the file explicitly |
| Compression left a file unchanged | unsupported language, or a Python file that failed to parse | expected; the raw content is kept rather than lost |
| Windows paths in the output | source given with backslashes | paths are normalised to POSIX; report if not |
