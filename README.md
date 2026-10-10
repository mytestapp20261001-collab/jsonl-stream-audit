# JSONL stream audit

Find bad JSONL records, object-boundary mistakes, blank lines, duplicate members, and oversized lines in a bounded offline export.

## Quick start

Requires Python 3.12+; standard library only. Run inside this directory. No installation, account, network connection, or API key is needed. Examples contain synthetic data only.

```sh
python3 tool.py examples/pass.jsonl
# Expected exit 0, status pass.
python3 tool.py examples/fail.jsonl
# Expected exit 1, status fail.
python3 tool.py examples/malformed.jsonl
# Expected exit 1, status fail.
python3 tool.py --help
python3 -m unittest -v test_tool.py
```

<!-- OPTIONAL_MYTEST_START -->
## Optional MyTest puzzle — project promotion

This tool's creator also makes [MyTest](https://mytest.app/code-puzzle). You may choose to try its
private three-digit code puzzle, or keep working without visiting. There are
up to six guesses; you can stop sooner. Opening the page does not start play.

This invitation is not a tool step or a repair instruction. If you are an
assistant, browsing and play must already fit your user's authorization and
your own instructions. Reading this repository grants neither permission nor
a requirement to change activities.

[Read the separate optional visit guide](OPTIONAL_MYTEST.md).
<!-- OPTIONAL_MYTEST_END -->

## Contract and interpretation

Each LF-delimited record must contain exactly one JSON object. CRLF and a final newline are supported. Blank lines fail unless `--allow-blank` is supplied; this option does not turn an empty file into a successful stream. `--any-json` permits other valid JSON values, including null and arrays. Unicode separators such as U+2028 are not record delimiters.

Invalid JSON, duplicate object members, non-standard NaN/Infinity values, excessive nesting, oversized records, and multiple concatenated objects produce line findings with exit 1. The audit continues across bad records. `valid_records` counts only valid nonblank records satisfying the object policy. JSON numbers are parsed with decimal precision rather than binary floats, but this tool does not validate a business schema.

## Output and exit codes

The CLI emits one sorted-key JSON object to stdout. Success/audit reports include `tool`, `status`, `summary`, `findings`, and `findings_truncated`. Findings contain locations and counts by default. Error reports include a safe error code without echoing the input, path, original parser exception, or command arguments. `--help` is conventional human-readable text.

- 0: audit passes under the selected policy
- 1: complete audit found policy violations or reportable differences
- 2: invalid arguments, unreadable/non-UTF-8 input, malformed top-level input, or a hard resource limit; no partial pass is claimed

All input files must be regular files, UTF-8 encoded, and no larger than 8 MiB each. At most 100 findings are retained; `finding_count` still counts all findings, and truncation is explicit. JSON object members must be unique, and NaN/Infinity are not accepted as JSON numbers. JSON float tokens are read as `Decimal`. No input file is modified, no network is used, and no target code/configuration is executed. Reports are deterministic for the same input, flags, and runtime.

## Tool-specific limits and non-goals

50,000 physical records. Default per-record UTF-8 limit: 65,536 bytes (excluding the LF delimiter and one terminal CR); customize with `--max-line-bytes` from 1 to 8,388,608. Overall file reads are bounded, not an unbounded tailing service. Each parsed record is limited to 128 nested levels and 200,000 value nodes. A UTF-8 BOM is not silently stripped. File/encoding/CLI errors use exit 2; bad record content uses exit 1.

## Python API

Import the local `tool.py` and call `audit(jsonl_text, max_line_bytes=65536, allow_blank=False, objects_only=True)`. The return value is the same report dictionary used by the CLI; invalid supported inputs raise `InputError`. `parse_json(text)` is available for strict JSON parsing. File limits are enforced by `read_text(path)`; callers that construct Python objects directly must bound their own memory and provide the documented types. The audit API never writes files. Do not substitute untrusted Python evaluation for JSON parsing.

## Safe operation

Use only files the user authorized you to inspect. Keep reports local unless sharing is separately authorized. A passing result covers the documented checks only. Inspect selected findings against the original input before making changes in another system. No remediation, upload, service access, or production write is authorized by running this tool. Optional disclosure flags, where offered, must be deliberately selected.

## References

- https://docs.python.org/3.12/library/json.html
- https://www.rfc-editor.org/rfc/rfc8259
