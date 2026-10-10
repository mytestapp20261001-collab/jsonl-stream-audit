#!/usr/bin/env python3
"""Offline, read-only audit. Python 3.12+, standard library only."""
import argparse
import json
import math
import re
import stat
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 50000
MAX_FINDINGS = 100

class InputError(ValueError):
    """A safe, non-payload-bearing input error code."""

class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InputError("invalid_arguments")

def read_text(path):
    p = Path(path)
    if not stat.S_ISREG(p.stat().st_mode):
        raise InputError("regular_file_required")
    with p.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise InputError("file_size_limit")
    return data.decode("utf-8")

def reject_constant(value):
    raise InputError("non_finite_json_number")

def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate_json_member")
        result[key] = value
    return result

def parse_json(text):
    try:
        result = json.loads(text, object_pairs_hook=unique_pairs,
                            parse_float=Decimal, parse_constant=reject_constant)
    except InputError:
        raise
    except (ValueError, RecursionError, InvalidOperation):
        raise InputError("invalid_json") from None
    stack, nodes = [(result, 0)], 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if depth > 128 or nodes > 200000:
            raise InputError("json_structure_limit")
        if isinstance(value, dict):
            stack.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            stack.extend((v, depth + 1) for v in value)
    return result

class Report:
    def __init__(self, tool):
        self.tool, self.findings, self.count = tool, [], 0
    def add(self, code, **location):
        self.count += 1
        if len(self.findings) < MAX_FINDINGS:
            self.findings.append(dict(code=code, **location))
    def finish(self, **summary):
        return {"tool": self.tool, "status": "fail" if self.count else "pass",
                "summary": dict(summary, finding_count=self.count),
                "findings": self.findings,
                "findings_truncated": self.count > len(self.findings)}

def emit_main(run):
    try:
        result = run()
        code = 1 if result["status"] == "fail" else 0
    except InputError as exc:
        result, code = {"tool": TOOL, "status": "error", "error": str(exc)}, 2
    except (OSError, UnicodeError):
        result, code = {"tool": TOOL, "status": "error", "error": "unreadable_utf8_input"}, 2
    except (ValueError, RecursionError, InvalidOperation):
        result, code = {"tool": TOOL, "status": "error", "error": "invalid_input"}, 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False))
    return code

TOOL = "jsonl-stream-audit"

def audit(text, *, max_line_bytes=65536, allow_blank=False, objects_only=True):
    if type(max_line_bytes) is not int or not 1 <= max_line_bytes <= MAX_BYTES:
        raise InputError("invalid_line_limit")
    report = Report(TOOL)
    # Only LF is a JSONL record delimiter; CRLF is supported. Other Unicode
    # line separators remain inside their JSON records.
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    if len(lines) > MAX_RECORDS:
        raise InputError("line_count_limit")
    valid = blank = 0
    for number, line in enumerate(lines, 1):
        if line.endswith("\r"):
            line = line[:-1]
        if len(line.encode("utf-8")) > max_line_bytes:
            report.add("line_size_limit", line=number)
            continue
        if line.strip(" \t\r") == "":
            blank += 1
            if not allow_blank:
                report.add("blank_line", line=number)
            continue
        try:
            value = parse_json(line)
        except InputError as exc:
            report.add(str(exc), line=number)
            continue
        if objects_only and not isinstance(value, dict):
            report.add("object_required", line=number)
        else:
            valid += 1
    if not lines:
        report.add("empty_stream")
    return report.finish(lines=len(lines), valid_records=valid, blank_lines=blank,
                         max_line_bytes=max_line_bytes, objects_only=objects_only)

def run():
    parser = Parser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--max-line-bytes", type=int, default=65536)
    parser.add_argument("--allow-blank", action="store_true")
    parser.add_argument("--any-json", action="store_true")
    args = parser.parse_args()
    return audit(read_text(args.input), max_line_bytes=args.max_line_bytes,
                 allow_blank=args.allow_blank, objects_only=not args.any_json)

if __name__ == "__main__":
    sys.exit(emit_main(run))
