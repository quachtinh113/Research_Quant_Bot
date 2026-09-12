---
name: repomix-context-packaging
description: "Pack these repositories into LLM-ready context bundles with the pure-Python repomix engine: styles, ignore rules, signature compression, token budgeting and splitting."
---

# Repomix Context Packaging

Packing repositories into a single LLM-ingestible document, using the pure-Python
engine in `scripts/repomix_pack_engine.py`. It reproduces the `repomix` output contract
(the XML, Markdown and Plain templates and the summary blocks) without needing Node.js,
which is not installed on this machine.

## Why pack at all

An agent reading a repository file by file spends most of its budget on navigation.
A pack gives it the directory structure and the relevant contents in one read, which is
what makes a Claude Project or an Antigravity workspace useful across six repositories
at once.

The trade-off is that a pack is a snapshot. Regenerate it after pulling upstream
changes, and never let an agent believe a stale pack over the working tree.

## Basic usage

```bash
# whole repository to XML
python scripts/repomix_pack_engine.py --source . --output repomix_outputs/suite.xml

# several repositories, Python only, signature-compressed
python scripts/repomix_pack_engine.py \
    --source qlib=./qlib --source vbt=./vectorbt \
    --include "**/*.py" --compress --style markdown \
    --output repomix_outputs/alpha_pack.md

# drive it from a config file
python scripts/repomix_pack_engine.py --config repomix.config.json
```

Every run also writes `<output>.manifest.json` with the file count, character and token
estimates, a SHA-256 of each output and the top files by token count. Use it to check a
pack fits a context window before uploading it.

## Choosing a style

| Style | Use for |
|---|---|
| `xml` | the default; tag boundaries survive truncation and models parse them reliably |
| `markdown` | human review, or documentation-heavy repositories |
| `plain` | maximum compatibility, minimum overhead |
| `json` | programmatic consumption; the file map is a dictionary |

## Controlling size

A full pack of these six repositories is far too large for any context window. Three
levers, in the order to reach for them.

**1. Select.** `--include` is the biggest lever. Packing `**/*.py` from Qlib and
vectorbt gives the API surface without notebooks, data or documentation.

**2. Compress.** `--compress` keeps only structural signatures: classes, function
definitions, decorators and the first line of each docstring, separated by the same
`⋮----` delimiter repomix uses. Python compression is exact, through the `ast` module;
other languages use language-aware regular expressions. Typical reduction is 70 to 85%
for source-heavy repositories, and the result still answers "what is the API".

**3. Split.** `--max-tokens-per-file 150000` writes `pack.part1.xml`, `pack.part2.xml`
and so on, splitting on file boundaries so no file is cut in half.

Rough guidance for a 200k-token window: one repository uncompressed, or three to four
compressed and filtered.

## What is excluded automatically

Default ignore patterns cover version control, dependency and build directories,
caches, lock files, logs, binaries, archives, media, fonts, documents and the data
blobs quant repositories are full of (`.h5`, `.parquet`, `.pkl`, `.npy`, `.pt`,
`.onnx`). `.gitignore` and `.repomixignore` are read as well.

Disable with `--no-default-patterns` or `--no-gitignore` when you specifically need
something excluded by default. Note that `*.csv` is **not** excluded by default, so a
repository with large CSVs will bloat a pack unless you add `--ignore "**/*.csv"`.

## Security

A regex scanner checks every file for private keys, cloud credentials, provider API
keys, JWTs and generic secret assignments. Any file that matches is **withheld from the
pack entirely** and listed in the report and the manifest.

Disable with `--no-security-check` only when you have confirmed the matches are false
positives, and never on a pack you will upload anywhere. The scan is conservative, so
a test fixture containing a fake key will be caught; that is the correct behaviour.

## Notebooks

`.ipynb` files are flattened rather than embedded as raw JSON. Without `--compress`,
each cell becomes a labelled block with markdown as comments; with `--compress`, only
markdown headings and code cell sources survive. Outputs are dropped in both cases,
which is usually a large saving in a research repository.

## The suite's standard packs

Defined in `skills_src/manifest.json` and built by
`python scripts/build_quant_agents_suite.py --packs`:

| Pack | Contents | Purpose |
|---|---|---|
| `claude_quant_master_pack` | this repository's skills, rules, agents, engines and bot code | drop into a Claude Project for full suite context |
| `alpha_research_pack` | Qlib and vectorbt Python, compressed | factor mining and simulation API |
| `execution_pack` | LEAN framework, Python examples, orders and brokerages, compressed | execution and reality modelling |
| `methodology_pack` | ML4T markdown and shared utilities | the methodology without the notebooks |
| `discovery_pack` | the awesome-quant index | library and vendor lookup |

## Using a pack with Claude

1. Create a Project.
2. Upload the pack file as Project Knowledge.
3. Put `repomix-instruction.md` in the Project system instructions.
4. Refer to files by their path exactly as they appear in the pack, since the paths are
   namespaced by source label when several repositories are packed together.

For Antigravity-IDE, the skills in `.agents/skills/` already carry the distilled
knowledge, so a pack is only needed when the agent must read actual source.

## Extending the engine

The code is a single dependency-free module. The pieces most likely to need changing:

- `DEFAULT_IGNORE_PATTERNS` — add file types specific to your data
- `SECRET_PATTERNS` — add credential formats your organisation uses
- `_SIGNATURE_RES` — add a language to the compressor
- `estimate_tokens` — swap in `tiktoken` if you need exact counts rather than an
  estimate within roughly 10%

## References

- Full command reference and recipes: [playbook.md](references/playbook.md)

## Related skills

`mindshub-orchestrator` for what the suite pack contains, and every repository skill
for what is worth packing from each one.
