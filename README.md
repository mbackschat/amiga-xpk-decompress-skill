# Amiga XPK/NUKE Decompressor

An agent plugin for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and OpenAI Codex that decompresses Amiga [XPK](http://aminet.net/package/util/pack/xpk_Develop)-compressed files using the **NUKE** and **DUKE** sub-packers.

Point it at a file or an entire directory tree and it will find and unpack every XPK/NUKE (or DUKE) compressed file, skipping everything else.

## What it does

| Feature | Detail |
|---------|--------|
| **Formats** | XPK/NUKE (LZ77 variant) and XPK/DUKE (NUKE + delta encoding) |
| **Scope** | Single files, directories, or recursive directory trees |
| **Safety** | Header magic, checksum, and preview verification before any write |
| **Dependencies** | Python 3 + [uv](https://github.com/astral-sh/uv) — no pip installs needed |

## Install

### Claude Code

```text
/plugin marketplace add mbackschat/amiga-xpk-decompress-skill
/plugin install xpk-decompress@xpk-decompress
```

For local testing from this checkout, use the repository path instead of the GitHub shorthand:

```text
/plugin marketplace add /path/to/amiga-xpk-decompress-skill
/plugin install xpk-decompress@xpk-decompress
```

### OpenAI Codex

```text
codex plugin marketplace add mbackschat/amiga-xpk-decompress-skill
codex plugin add xpk-decompress@xpk-decompress
```

For local testing from this checkout:

```text
codex plugin marketplace add /path/to/amiga-xpk-decompress-skill
codex plugin add xpk-decompress@xpk-decompress
```

Both hosts use the same shared skill under [skills/xpk-decompress](skills/xpk-decompress/SKILL.md). The host-specific packaging is limited to `.claude-plugin/`, `.codex-plugin/`, and `.agents/plugins/marketplace.json`.

## Usage

Inside Claude Code, use the installed skill as a namespaced slash command:

```
/xpk-decompress:xpk-decompress /path/to/compressed/files -o /path/to/output
```

In Codex, ask directly, e.g. "Use xpk-decompress to unpack `/path/to/compressed/files` into `/path/to/output`."

### Examples

**Decompress a single file:**
```
/xpk-decompress:xpk-decompress game.lha.nuke -o ./unpacked/
```

**Decompress an entire directory recursively (in place):**
```
/xpk-decompress:xpk-decompress /home/user/amiga-sources/
```

**Dry run — list compressed files without writing:**
```
/xpk-decompress:xpk-decompress /path/to/directory --dry-run
```

### Flags

| Flag | Description |
|------|-------------|
| `-o`, `--output` | Output directory (default: decompress in place, overwriting originals) |
| `-n`, `--dry-run` | List matching files without decompressing |
| `--no-recursive` | Don't recurse into subdirectories |

## How it works

The decompressor is a pure-Python port of the NUKE/DUKE codec from [ancient](https://github.com/temisu/ancient) by Teemu Suutari (ISC license).

1. **Header validation** — checks the `XPKF` magic, verifies the packer ID is `NUKE` or `DUKE`, and confirms the XOR checksum across bytes 0–35 is zero.
2. **Chunk iteration** — walks the XPK chunk stream, handling stored (type 0) and compressed (type 1) chunks until the end marker (type 15).
3. **NUKE decompression** — each compressed chunk is decoded using interleaved forward/backward byte streams, MSB and LSB bit readers, and a variable-length code table for LZ77 distances.
4. **DUKE delta decode** — if the packer is DUKE, an additional delta-decoding pass is applied to the output.
5. **Preview verification** — the first 16 bytes of the decompressed output are compared against the header's preview field.

Non-XPK files are silently skipped, so it is safe to point the tool at a mixed directory.

## Standalone usage

The Python script can also be used directly without an agent:

```bash
uv run python3 skills/xpk-decompress/scripts/xpk_nuke_decompress.py /path/to/files -o /output
```

Or with plain Python:

```bash
python3 skills/xpk-decompress/scripts/xpk_nuke_decompress.py /path/to/files -o /output
```

## Layout

```text
.
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── .codex-plugin/
│   └── plugin.json
├── .agents/
│   └── plugins/
│       └── marketplace.json
├── skills/
│   └── xpk-decompress/
│       ├── SKILL.md
│       ├── agents/openai.yaml
│       └── scripts/xpk_nuke_decompress.py
├── tests/
├── README.md
└── LICENSE
```

## License

MIT — see [LICENSE](LICENSE).

The NUKE/DUKE decompression algorithm is ported from [ancient](https://github.com/temisu/ancient) (ISC license) by Teemu Suutari.
