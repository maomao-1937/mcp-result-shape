# MCP Result Shape

[![tests](https://github.com/maomao-1937/mcp-result-shape/actions/workflows/tests.yml/badge.svg)](https://github.com/maomao-1937/mcp-result-shape/actions/workflows/tests.yml)

Compare two checks for the `structuredContent` of a saved Model Context Protocol `tools/call` result. `success_only` skips the shape check when `isError` is true. `always` runs it for both successful and error results. The JSON report uses 1-based positions for missing or mistyped members, so you can share it without exposing input names, values, or paths.

## Quick start

Use Python 3.11 or later on Windows or Linux. The CLI uses the standard library.

```sh
git clone https://github.com/maomao-1937/mcp-result-shape.git
cd mcp-result-shape
python mcp_result_shape.py examples/shape.json examples/error-mismatch.json
```

This command exits 1. `sample_count` is the first required member and has the wrong type. `items` is the second and is missing.

```json
{"status":"mismatch","is_error":true,"required_count":2,"structured_content":"object","policies":{"success_only":"skipped","always":"fail"},"missing":[2],"wrong_type":[1]}
```

```sh
python mcp_result_shape.py examples/shape.json examples/success.json
python mcp_result_shape.py examples/shape.json examples/error-no-content.json
python mcp_result_shape.py examples/shape.json examples/invalid-envelope.json
```

These return 0 for a match, 1 for an error result with missing structured content, and 2 for an invalid input envelope, respectively.

## Inputs and output

- `SHAPE.json` is an object with exactly one member, `required`. Its value maps up to 128 member names to `null`, `boolean`, `integer`, `number`, `string`, `array`, or `object`. Names must have 1–128 Unicode code points. The mapping's input order determines member positions. `integer` accepts exact integral numbers such as `1.00` and `100e-2`. `number` accepts any JSON number. Booleans are a separate kind.
- `RESULT.json` is the saved result body. For a successful JSON-RPC response, save the value of its `result` member to a file. `isError` is optional and defaults to false. A present `isError` must be a boolean. Other than `structuredContent`, the shape check ignores additional result fields. The shape check also ignores extra properties inside `structuredContent`.
- Each input is a regular local file with up to 256 KiB of UTF-8 JSON. BOMs, duplicate object keys, non-JSON numeric constants, unpaired surrogates, and JSON that exceeds the decoder's nesting limit are rejected. Path spelling checks reject URL, UNC, device, drive-relative, alternate stream, and trailing alias forms. Use a trusted local directory because spelling checks cannot determine where filesystem links or mounts lead.
- `structured_content` is `object`, `missing`, or `non_object`. Missing or non-object content fails a policy that runs the check, even for an empty `required` map. In either case, the two member-position lists are empty. Extra content fields never add positions.

| Exit | Meaning |
| --- | --- |
| 0 | Each policy passed or skipped, or `--help` displayed. |
| 1 | At least one policy ran and failed. |
| 2 | Invalid arguments or input, read failure, or unavailable stdout. |

Invalid input produces one JSON line with `status: "invalid"`, a fixed `reason`, and an input `role` where applicable. If stdout is unavailable, the command exits 2 quietly.

This tool implements a small projection of the MCP 2025-11-25 structured output shape for local fixtures. Its checks cover required member presence and primitive JSON kinds. Full JSON Schema, SDK conformance, and live calls are outside its scope. [MCP Tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)

## 中文

用这个命令检查已保存的 MCP `tools/call` 结果，比较两种结构校验策略。`success_only` 在 `isError` 为 `true` 时跳过检查，`always` 在成功和报错时都会检查。报告里的 `missing` 和 `wrong_type` 分别列出缺失字段和类型不符字段在 `required` 中的位置，从 1 开始。输出省略输入字段名、值和文件路径。

在 Windows 或 Linux 使用 Python 3.11 或更高版本，按上方命令克隆仓库并运行示例，无需安装第三方包。第一个示例中，第一个必填字段类型不符，第二个字段缺失，因此 `success_only` 跳过、`always` 失败，退出码为 1。

两个文件都必须是 256 KiB 以内的 UTF-8 JSON 常规文件。`SHAPE.json` 只含 `required`，最多定义 128 个必填字段。字段名长度为 1–128 个 Unicode 码点，支持 `null`、`boolean`、`integer`、`number`、`string`、`array`、`object`。`1.00` 和 `100e-2` 都是 `integer`。`RESULT.json` 应保存 JSON-RPC 响应中 `result` 的内容。`isError` 缺省为 `false`。只要执行校验，`structuredContent` 缺失或不是对象都会失败，即使 `required` 为空。

退出码 0 表示各策略通过或跳过，也用于成功显示帮助。退出码 1 表示至少一项校验失败。退出码 2 表示参数或输入无效、文件读取失败，或标准输出不可用。请使用可信本地目录。这个离线工具仅检查顶层必填字段及其 JSON 类型。

See [research](RESEARCH.md) and [tests](TESTING.md). MIT licensed.
