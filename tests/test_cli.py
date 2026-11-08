import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "mcp_result_shape.py"


def load_subject():
    spec = importlib.util.spec_from_file_location("subject", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ResultShapeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.shape = Path(directory.name) / "private-shape.json"
        self.result = Path(directory.name) / "private-result.json"
        self.save({"required": {}}, {"structuredContent": {}})

    def save(self, shape, result):
        self.shape.write_bytes(shape if isinstance(shape, bytes) else json.dumps(shape).encode())
        self.result.write_bytes(result if isinstance(result, bytes) else json.dumps(result).encode())

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)],
                              capture_output=True, timeout=10)

    def report(self, status, *args):
        process = self.run_cli(*(args or (self.shape, self.result)))
        self.assertEqual(process.returncode, status, process.stderr)
        self.assertEqual(process.stderr, b"")
        self.assertEqual(len(process.stdout.splitlines()), 1)
        self.assertNotIn(b"private-", process.stdout)
        return json.loads(process.stdout)

    def test_all_kinds_on_success_and_error_with_matching_content(self):
        kinds = ("null", "boolean", "integer", "number", "string", "array", "object")
        keys = tuple(f"private-{kind}" for kind in kinds)
        values = (None, False, -17, 4.5, "", [], {"private-extra": [True]})
        for error in (None, False, True):
            result = {"structuredContent": dict(zip(keys, values)), "extension": {"nested": []}}
            if error is not None:
                result["isError"] = error
            self.save({"required": dict(zip(keys, kinds))}, result)
            self.assertEqual(self.report(0), {
                "status": "ok", "is_error": bool(error), "required_count": 7,
                "structured_content": "object",
                "policies": {"success_only": "skipped" if error else "pass", "always": "pass"},
                "missing": [], "wrong_type": [],
            })

    def test_error_skips_only_success_policy_and_reports_ordinals_in_profile_order(self):
        self.save({"required": {"private-z": "integer", "private-A": "string", "private-b": "number",
                                "private-B": "null", "private-c": "object"}},
                  {"isError": True, "structuredContent": {"private-B": None, "private-b": False,
                                                         "private-z": True}})
        self.assertEqual(self.report(1), {
            "status": "mismatch", "is_error": True, "required_count": 5,
            "structured_content": "object", "policies": {"success_only": "skipped", "always": "fail"},
            "missing": [2, 5], "wrong_type": [1, 3],
        })

    def test_missing_and_non_object_content_even_for_empty_shape(self):
        for state, value in (("missing", None), ("non_object", None), ("non_object", []),
                             ("non_object", False), ("non_object", "private-string")):
            for error in (False, True):
                result = {"isError": error}
                if state != "missing":
                    result["structuredContent"] = value
                self.save({"required": {}}, result)
                report = self.report(1)
                self.assertEqual(report["structured_content"], state)
                self.assertEqual(report["policies"], {
                    "success_only": "skipped" if error else "fail", "always": "fail",
                })
                self.assertEqual((report["missing"], report["wrong_type"]), ([], []))

    def test_integer_kind_uses_exact_mathematics(self):
        integral = (b"1.00", b"100e-2", b"1e999999999999999999999", b"-0e-999999999999999999999",
                    b"9" * 5000, b"10.0e-00000001")
        fractional = (b"100e-3", b"1e-999999999999999999999",
                      b"1.000000000000000000000000000000001")
        for token in integral + fractional:
            self.save({"required": {"private-integer": "integer", "private-number": "number"}},
                      b'{"structuredContent":{"private-integer":' + token
                      + b',"private-number":' + token + b'}}')
            status = int(token in fractional)
            self.assertEqual(self.report(status)["wrong_type"], [1] if status else [])

    def test_shape_has_exact_keys_and_limited_kind_names(self):
        for shape in ({}, [], {"required": {}, "extra": 1}, {"required": []},
                      {"required": {"": "string"}}, {"required": {"雪" * 129: "string"}},
                      {"required": {"x": None}}, {"required": {"x": ["number"]}},
                      {"required": {"x": "Number"}},
                      {"required": {str(i): "number" for i in range(129)}}):
            self.save(shape, {"structuredContent": {}})
            self.assertEqual(self.report(2), {
                "status": "invalid", "reason": "invalid_shape", "role": "shape",
            })
        keys = ["雪" * 128, *map(str, range(127))]
        self.save({"required": dict.fromkeys(keys, "null")}, {"structuredContent": dict.fromkeys(keys)})
        self.assertEqual(self.report(0)["required_count"], 128)

    def test_result_object_boolean_and_envelope_contract(self):
        for result in ([], None, {"isError": 0}, {"isError": None}, {"isError": "false"},
                       {"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": {}}},
                       {"jsonrpc": "2.0", "id": None, "error": {"code": -32000}}):
            self.save({"required": {}}, result)
            self.assertEqual(self.report(2), {
                "status": "invalid", "reason": "invalid_result", "role": "result",
            })

    def test_result_body_can_include_rpc_named_extensions(self):
        extension = {"jsonrpc": "2.0", "id": 1, "result": {"private-result": True}}
        cases = (
            ({"content": [], "structuredContent": {}}, 0, "object", "pass"),
            ({"structuredContent": {}}, 0, "object", "pass"),
            ({"content": []}, 1, "missing", "fail"),
            ({"isError": True}, 1, "missing", "skipped"),
        )
        for body, code, state, policy in cases:
            with self.subTest(body=body):
                self.save({"required": {}}, {**body, **extension})
                report = self.report(code)
                self.assertEqual(report["structured_content"], state)
                self.assertEqual(report["policies"]["success_only"], policy)

    def test_entire_document_has_strict_utf8_and_json_even_when_a_policy_skips(self):
        invalid = [
            b'{"isError":true,"ignored":{"x":1,"x":2}}',
            br'{"isError":true,"ignored":{"x":1,"\u0078":2}}',
            b'{"isError":true,"ignored":NaN}', b'{"isError":true,"ignored":-Infinity}',
            br'{"isError":true,"ignored":["\ud800"]}', br'{"isError":true,"\udfff":0}',
            b'{"isError":true,"ignored":"\xff"}', b'\xef\xbb\xbf{}', b'{} {}',
        ]
        for content in invalid:
            with self.subTest(content=content):
                self.result.write_bytes(content)
                self.assertEqual(self.report(2), {
                    "status": "invalid", "reason": "invalid_json", "role": "result",
                })
        self.result.write_bytes(br'{"structuredContent":{"emoji":"\ud83d\ude03"}}')
        self.assertEqual(self.report(0)["structured_content"], "object")

    def test_file_byte_limit_missing_path_and_directory(self):
        raw = b'{"structuredContent":{}}'
        maximum = raw + b" " * (256 * 1024 - len(raw))
        self.result.write_bytes(maximum)
        self.report(0)
        self.result.write_bytes(maximum + b" ")
        self.assertEqual(self.report(2), {"status": "invalid", "reason": "byte_limit", "role": "result"})
        self.result.unlink()
        for path in (self.result, self.result.parent):
            self.assertEqual(self.report(2, self.shape, path), {
                "status": "invalid", "reason": "unreadable_file", "role": "result",
            })

    def test_path_guards_all_args_before_any_input_access(self):
        self.assertTrue(SCRIPT.exists(), "CLI entry point is missing")
        module = load_subject()
        invalid = ["https://private-host/thing", "file:///private-file", r"/\private-host\share",
                   r"\Device\file", r"\??\file", "/safe/../GlobalRoot/file", r"\safe\..\SystemRoot\f",
                   "/./DosDevices/f", "C:local.json", "local.json:stream", "C:/local.json:stream",
                   "x/COM¹.json", "x/NUL .json", "x/file. ", "x/file/"]
        for path in invalid:
            for index, role in enumerate(("shape", "result")):
                with (
                    self.subTest(path=path, role=role),
                    patch.object(module.os, "open", side_effect=AssertionError("unexpected open")),
                    patch.object(module.os, "stat", side_effect=AssertionError("unexpected stat")),
                    patch.object(module, "emit", return_value=2) as emit,
                ):
                    paths = list(map(str, (self.shape, self.result)))
                    paths[index] = path
                    self.assertEqual(module.main(paths), 2)
                    self.assertEqual(json.loads(emit.call_args.args[0]), {
                        "status": "invalid", "reason": "unsafe_path", "role": role,
                    })

    def test_rechecks_the_open_descriptor_before_reading(self):
        self.assertTrue(SCRIPT.exists(), "CLI entry point is missing")
        module = load_subject()
        for mode, size, reason in ((stat.S_IFCHR, 0, "unreadable_file"),
                                   (stat.S_IFREG, 256 * 1024 + 1, "byte_limit")):
            with (
                self.subTest(reason=reason),
                patch.object(module.os, "fstat", return_value=SimpleNamespace(st_mode=mode, st_size=size)) as fstat,
                patch.object(module.os, "fdopen", side_effect=AssertionError("unexpected read")),
                patch.object(module, "emit", return_value=2) as emit,
            ):
                self.assertEqual(module.main(list(map(str, (self.shape, self.result)))), 2)
                self.assertEqual(json.loads(emit.call_args.args[0]), {
                    "status": "invalid", "reason": reason, "role": "shape",
                })
            with self.assertRaises(OSError):
                os.fstat(fstat.call_args.args[0])

    def test_fifo_rejected_without_waiting_for_writer(self):
        expected = {
            "status": "invalid", "reason": "unreadable_file", "role": "result",
        }
        if hasattr(os, "mkfifo"):
            self.result.unlink()
            os.mkfifo(self.result)
            self.assertEqual(self.report(2), expected)
            return

        module = load_subject()
        real_stat = os.stat

        def stat_with_fifo(path):
            if path == str(self.result):
                return SimpleNamespace(st_mode=stat.S_IFIFO, st_size=0)
            return real_stat(path)

        with (
            patch.object(module.os, "stat", side_effect=stat_with_fifo),
            patch.object(module.os, "open", wraps=os.open) as opened,
            patch.object(module, "emit", return_value=2) as emit,
        ):
            self.assertEqual(module.main(list(map(str, (self.shape, self.result)))), 2)
            self.assertEqual(json.loads(emit.call_args.args[0]), expected)
        self.assertEqual([call.args[0] for call in opened.call_args_list], [str(self.shape)])

    def test_argument_error_and_help(self):
        self.assertEqual(self.report(2, "private-file"), {"status": "invalid", "reason": "arguments"})
        help_run = self.run_cli("--help")
        self.assertEqual((help_run.returncode, help_run.stderr), (0, b""))
        self.assertIn(b"SHAPE.json RESULT.json", help_run.stdout)

    def test_closed_stdout_is_quiet_for_report_error_and_help(self):
        for args in ([str(self.shape), str(self.result)], ["private-file"], ["--help"]):
            reader, writer = os.pipe()
            os.close(reader)
            with os.fdopen(writer, "wb") as pipe:
                completed = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                           stdout=pipe, stderr=subprocess.PIPE, timeout=10)
            self.assertEqual((completed.returncode, completed.stderr), (2, b""))


if __name__ == "__main__":
    unittest.main()
