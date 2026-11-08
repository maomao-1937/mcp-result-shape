"""Compare two policies for required fields in a saved MCP tool result."""

import json
import os
import posixpath
import re
import stat
import sys


MAX_BYTES = 256 * 1024
DEVICE = re.compile(r"CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[0-9¹²³]")
NATIVE_ROOTS = {"??", "device", "dosdevices", "global??", "systemroot", "globalroot"}


class InputError(Exception):
    """An input error with a fixed, shareable reason code."""


class JSONNumber:
    """Keep the JSON spelling so conversion cannot round or overflow."""

    __slots__ = ("token",)

    def __init__(self, token):
        self.token = token

    def is_integer(self):
        coefficient, _, exponent = self.token.lower().partition("e")
        whole, _, fraction = coefficient.lstrip("-").partition(".")
        digits = whole + fraction
        significant = digits.rstrip("0")
        if not significant:
            return True
        trailing_zeros = len(digits) - len(significant)
        minimum_exponent = len(fraction) - trailing_zeros

        magnitude = exponent.lstrip("+-").lstrip("0")
        negative = exponent.startswith("-")
        # The coefficient has at most MAX_BYTES digits. Longer exponent
        # magnitudes therefore decide the comparison without integer conversion.
        if len(magnitude) > len(str(MAX_BYTES)):
            return not negative
        power = int(magnitude or "0")
        return (-power if negative else power) >= minimum_exponent


KIND_TYPES = {
    "null": type(None),
    "boolean": bool,
    "integer": JSONNumber,
    "number": JSONNumber,
    "string": str,
    "array": list,
    "object": dict,
}


def check_path(path):
    spelling = path.replace("\\", "/")
    if not spelling or spelling == "-" or spelling.startswith("//") or spelling.endswith("/"):
        raise InputError("unsafe_path")
    if any(ord(char) < 32 for char in spelling):
        raise InputError("unsafe_path")
    if spelling.startswith("/"):
        for version in (spelling, posixpath.normpath(spelling)):
            root = version[1:].partition("/")[0].rstrip(" .").lower()
            if root in NATIVE_ROOTS:
                raise InputError("unsafe_path")
    tail = spelling[2:] if re.match(r"^[A-Za-z]:/", spelling) else spelling
    if ":" in tail:
        raise InputError("unsafe_path")
    for part in tail.split("/"):
        if part in {"", ".", ".."}:
            continue
        stem = part.partition(".")[0].rstrip(" ").upper()
        if part.endswith((" ", ".")) or DEVICE.fullmatch(stem):
            raise InputError("unsafe_path")


def check_file(info):
    if not stat.S_ISREG(info.st_mode) or info.st_size < 0:
        raise InputError("unreadable_file")
    if info.st_size > MAX_BYTES:
        raise InputError("byte_limit")


def read_bytes(path):
    try:
        check_file(os.stat(path))
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        try:
            check_file(os.fstat(descriptor))
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                data = stream.read(MAX_BYTES + 1)
        finally:
            os.close(descriptor)
    except (OSError, ValueError):
        raise InputError("unreadable_file") from None
    if len(data) > MAX_BYTES:
        raise InputError("byte_limit")
    return data


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        key.encode("utf-8")
        result[key] = value
    return result


def reject_constant(_token):
    raise ValueError


def read_json(path):
    data = read_bytes(path)
    try:
        document = json.loads(
            data.decode("utf-8"), object_pairs_hook=unique_object,
            parse_int=JSONNumber, parse_float=JSONNumber, parse_constant=reject_constant,
        )
        pending = [document]
        while pending:
            item = pending.pop()
            if isinstance(item, dict):
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
            elif isinstance(item, str):
                item.encode("utf-8")
    except (ValueError, RecursionError):
        raise InputError("invalid_json") from None
    return document


def read_shape(path):
    shape = read_json(path)
    if not isinstance(shape, dict) or shape.keys() != {"required"}:
        raise InputError("invalid_shape")
    required = shape["required"]
    if not isinstance(required, dict) or len(required) > 128:
        raise InputError("invalid_shape")
    for name, kind in required.items():
        if not 1 <= len(name) <= 128 or not isinstance(kind, str) or kind not in KIND_TYPES:
            raise InputError("invalid_shape")
    return required


def read_result(path):
    result = read_json(path)
    if not isinstance(result, dict) or not isinstance(result.get("isError", False), bool):
        raise InputError("invalid_result")
    # A result body can use RPC member names as extension fields.
    has_body_fields = not result.keys().isdisjoint({"content", "structuredContent", "isError"})
    if not has_body_fields and result.get("jsonrpc") == "2.0" and ("result" in result or "error" in result):
        raise InputError("invalid_result")
    return result


def compare(required, result):
    is_error = result.get("isError", False)
    content = result.get("structuredContent")
    missing = []
    wrong_type = []
    if isinstance(content, dict):
        state = "object"
        for ordinal, (name, kind) in enumerate(required.items(), 1):
            if name not in content:
                missing.append(ordinal)
                continue
            value = content[name]
            if not isinstance(value, KIND_TYPES[kind]) or (kind == "integer" and not value.is_integer()):
                wrong_type.append(ordinal)
    else:
        state = "non_object" if "structuredContent" in result else "missing"

    matches = state == "object" and not missing and not wrong_type
    outcome = "pass" if matches else "fail"
    return {
        "status": "ok" if matches else "mismatch",
        "is_error": is_error,
        "required_count": len(required),
        "structured_content": state,
        "policies": {"success_only": "skipped" if is_error else outcome, "always": outcome},
        "missing": missing,
        "wrong_type": wrong_type,
    }


def emit(data, code):
    remaining = memoryview(data)
    try:
        while remaining:
            written = os.write(1, remaining)
            if written <= 0:
                return 2
            remaining = remaining[written:]
    except OSError:
        return 2
    return code


def emit_report(report, code):
    return emit(json.dumps(report, separators=(",", ":")).encode("ascii") + b"\n", code)


def main(args):
    if args in (["--help"], ["-h"]):
        return emit(b"Usage: python mcp_result_shape.py SHAPE.json RESULT.json\n", 0)
    if len(args) != 2:
        return emit_report({"status": "invalid", "reason": "arguments"}, 2)

    try:
        for role, path in zip(("shape", "result"), args):
            check_path(path)
        role = "shape"
        required = read_shape(args[0])
        role = "result"
        result = read_result(args[1])
    except InputError as error:
        return emit_report({"status": "invalid", "reason": str(error), "role": role}, 2)
    report = compare(required, result)
    return emit_report(report, int(report["status"] == "mismatch"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
