---
name: xpk-decompress
description: Decompress Amiga XPK/NUKE and DUKE compressed files. Use when user wants to unpack XPK, NUKE, or DUKE compressed Amiga files.
argument-hint: [file-or-directory] [--output DIR] [--dry-run]
allowed-tools: Bash(uv *) Read
---

Decompress Amiga XPK/NUKE (and DUKE) compressed files using the bundled Python decompressor.

## How to run

Use `uv run` to execute the script with no global installs required:

```bash
uv run python3 ${CLAUDE_SKILL_DIR}/xpk_nuke_decompress.py $ARGUMENTS
```

If no arguments were provided, ask the user for a file or directory path.

## Examples

Decompress a single file to an output directory:
```bash
uv run python3 ${CLAUDE_SKILL_DIR}/xpk_nuke_decompress.py /path/to/file.c -o /path/to/output/
```

Decompress an entire directory (recursive) in place:
```bash
uv run python3 ${CLAUDE_SKILL_DIR}/xpk_nuke_decompress.py /path/to/directory/
```

Dry run (list XPK/NUKE files without writing):
```bash
uv run python3 ${CLAUDE_SKILL_DIR}/xpk_nuke_decompress.py /path/to/directory/ --dry-run
```

## Flags

| Flag | Description |
|------|-------------|
| `-o`, `--output` | Output directory (default: decompress in place, overwriting originals) |
| `-n`, `--dry-run` | List matching files without decompressing |
| `--no-recursive` | Don't recurse into subdirectories |

## Validation

The script only touches files that pass all of these checks:
- Bytes 0–3 are `XPKF` magic
- Bytes 8–11 are `NUKE` or `DUKE` packer ID
- XOR header checksum (bytes 0–35) is zero
- Preview field (bytes 16–31) matches the first 16 bytes of output after decompression

Non-XPK files are silently skipped — safe to point at a mixed directory.

## Important

- **In-place mode overwrites originals.** Warn the user or suggest `-o` if they haven't specified an output directory.
- Requires only `uv` and Python 3 — no additional packages or global installs.
