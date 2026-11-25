"""Expose the read-only report to the extension page over stdio MCP."""
import json
import sys

from analytics import PERIODS, UsageError, read_usage

TOOL = {
    "name": "usage_analytics_report",
    "description": "Show local token totals, daily trends and paginated request records.",
    "inputSchema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "days": {"type": "integer", "enum": list(PERIODS), "default": 7},
            "model": {"type": "string", "maxLength": 128, "default": ""},
            "page": {"type": "integer", "minimum": 1, "maximum": 2**31 - 1, "default": 1},
        },
    },
    "annotations": {"readOnlyHint": True, "openWorldHint": False},
    "_meta": {"ui": {"visibility": ["app"]}},
}


def dispatch(method, params):
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "usage-analytics", "version": "0.1.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [TOOL]}
    if method == "tools/call" and params.get("name") == TOOL["name"]:
        try:
            data = read_usage(params.get("arguments", {}))
        except UsageError as error:
            return {
                "isError": True,
                "content": [{"type": "text", "text": str(error)}],
            }
        return {
            "content": [{"type": "text", "text": json.dumps(data, separators=(",", ":"))}],
            "structuredContent": data,
        }
    return None


def serve():
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except ValueError:
            print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {
                "code": -32700, "message": "Parse error",
            }}), flush=True)
            continue
        if not isinstance(message, dict) or "id" not in message:
            continue
        reply = {"jsonrpc": "2.0", "id": message["id"]}
        params = message.get("params", {})
        if not isinstance(params, dict):
            reply["error"] = {"code": -32602, "message": "Invalid params"}
        else:
            result = dispatch(message.get("method"), params)
            if result is None:
                reply["error"] = {"code": -32601, "message": "Method not found"}
            else:
                reply["result"] = result
        print(json.dumps(reply, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    serve()
