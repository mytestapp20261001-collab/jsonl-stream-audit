import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(HERE.name.replace("-", "_"), HERE / "tool.py")
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)

class CommonTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, str(HERE / "tool.py"), *args], cwd=HERE,
                              capture_output=True, text=True, timeout=10)
    def test_cli_pass(self):
        result = self.cli("examples/" + PASS, *ARGS)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "pass")
        self.assertEqual(result.stderr, "")
    def test_cli_fail(self):
        result = self.cli("examples/" + FAIL, *ARGS)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "fail")
    def test_cli_malformed(self):
        result = self.cli("examples/" + MALFORMED, *ARGS)
        self.assertEqual(result.returncode, MALFORMED_CODE, result.stdout + result.stderr)
        self.assertIn(json.loads(result.stdout)["status"], ("fail", "error"))
    def test_cli_missing_file(self):
        result = self.cli("nonexistent-input", *ARGS)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"], "unreadable_utf8_input")
    def test_cli_invalid_arguments_are_redacted(self):
        result = self.cli("--unrecognized-secret-value")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"], "invalid_arguments")
        self.assertNotIn("unrecognized-secret-value", result.stdout + result.stderr)
    def test_cli_help(self):
        result = self.cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout)
    def test_cli_stability(self):
        a = self.cli("examples/" + FAIL, *ARGS)
        b = self.cli("examples/" + FAIL, *ARGS)
        self.assertEqual(a.stdout, b.stdout)
    def test_file_limit_and_utf8(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"x" * (tool.MAX_BYTES + 1))
            with self.assertRaises(tool.InputError):
                tool.read_text(path)
            path.write_bytes(b"\xff")
            with self.assertRaises(UnicodeDecodeError):
                tool.read_text(path)
    def test_json_parser_safety(self):
        for text in ('{"x":1,"x":2}', '[NaN]', '[' * 130 + '0' + ']' * 130):
            with self.subTest(text=text[:20]), self.assertRaises(tool.InputError):
                tool.parse_json(text)
    def test_report_cap_preserves_count(self):
        report = tool.Report("test")
        for i in range(101):
            report.add("sample", record=i)
        result = report.finish()
        self.assertEqual(len(result["findings"]), 100)
        self.assertEqual(result["summary"]["finding_count"], 101)
        self.assertTrue(result["findings_truncated"])

    def test_adversarial_cli_and_read_only_corpus(self):
        samples = ['', 'null', 'true', '0', '[]', '{}', '[null]', '[true]', '[1]',
                   '["NaN"]', '[{}]', '[[]]', '{"x":1,"x":2}',
                   '[1e99999999999999999999999999]', '[NaN]', '[Infinity]',
                   '"\\ud800"', '["\\ud800"]', '{', '[', '["a","b"]',
                   '[1e-99999999999999999999999999]']
        before = {path: path.read_bytes() for path in (HERE / 'examples').iterdir()}
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            path = Path(directory) / 'input.txt'
            for sample in samples:
                with self.subTest(sample=sample):
                    path.write_text(sample, encoding='utf-8')
                    result = self.cli(str(path), *ARGS)
                    self.assertIn(result.returncode, (0, 1, 2), result.stderr)
                    self.assertEqual(result.stderr, '')
                    self.assertIn(json.loads(result.stdout)['status'], ('pass','fail','error'))
                    self.assertEqual(path.read_text(encoding='utf-8'), sample)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)

PASS = 'pass.jsonl'
FAIL = 'fail.jsonl'
MALFORMED = 'malformed.jsonl'
MALFORMED_CODE = 1
ARGS = []

class AuditTests(unittest.TestCase):
    def test_crlf_and_final_newline(self):
        result = tool.audit('{"x":1}\r\n{"x":2}\r\n')
        self.assertEqual(result['summary']['lines'],2)
        self.assertEqual(result['status'],'pass')
    def test_actual_unicode_separator_is_not_line_break(self):
        self.assertEqual(tool.audit('{"x":"a\u2028b"}\n')['status'],'pass')
    def test_blank_policy(self):
        self.assertEqual(tool.audit('{}\n\n')['status'],'fail')
        self.assertEqual(tool.audit('{}\n\n',allow_blank=True)['status'],'pass')
    def test_any_json(self):
        self.assertEqual(tool.audit('null\n0\n[]\n',objects_only=False)['status'],'pass')
        self.assertEqual(tool.audit('null\n')['findings'][0]['code'],'object_required')
    def test_multiple_objects_and_multiline_objects_rejected(self):
        for text in ('{}{}\n','{\n"x":1\n}\n'):
            self.assertEqual(tool.audit(text)['status'],'fail')
    def test_nonfinite_duplicate_and_depth(self):
        result=tool.audit('{"x":NaN}\n{"x":1,"x":2}\n'+'['*130+'0'+']'*130)
        self.assertEqual(result['summary']['finding_count'],3)
    def test_utf8_byte_limit(self):
        text='{"x":"é"}'
        self.assertEqual(tool.audit(text,max_line_bytes=len(text))['status'],'fail')
        self.assertEqual(tool.audit(text,max_line_bytes=len(text.encode()))['status'],'pass')
    def test_limit_validation(self):
        with self.assertRaises(tool.InputError): tool.audit('{}',max_line_bytes=0)
    def test_empty(self): self.assertEqual(tool.audit('')['findings'][0]['code'],'empty_stream')
    def test_bom_rejected(self): self.assertEqual(tool.audit('\ufeff{}')['status'],'fail')
    def test_record_limit(self):
        previous = tool.MAX_RECORDS
        try:
            tool.MAX_RECORDS = 1
            with self.assertRaises(tool.InputError): tool.audit('{}\n{}')
        finally: tool.MAX_RECORDS = previous
    def test_payload_redacted(self): self.assertNotIn('SUPERSECRET',json.dumps(tool.audit('{"SUPERSECRET":bad}')))

if __name__ == '__main__': unittest.main()
