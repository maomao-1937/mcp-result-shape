# Research

The MCP 2025-11-25 tools specification gives a tool's optional output schema an object shape and describes conformance of structured results to a declared schema. The CLI projects this down to required property names and primitive kinds. [MCP Tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)

A TypeScript SDK issue describes a client validating error result content that the server skips. A Python SDK issue describes server-side output validation preventing a tool from sending its own error result. These reports motivate the two comparison policies. The CLI compares saved fixtures under those policies independently of any SDK release. [TypeScript SDK issue 1943](https://github.com/modelcontextprotocol/typescript-sdk/issues/1943), [Python SDK issue 2429](https://github.com/modelcontextprotocol/python-sdk/issues/2429)
