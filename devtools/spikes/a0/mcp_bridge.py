"""A0 spike: minimal MCP stdio server whose tools forward to a unix socket (stand-in for the live Controller)."""
import json, socket, sys

SOCK = sys.argv[1]
TOOLS = [
    {"name": "zplan_status", "description": "Return the zplan project status.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "zplan_merge", "description": "Ask zplan to merge a finished run.",
     "inputSchema": {"type": "object", "properties": {"run": {"type": "string"}}, "required": ["run"]}},
]


def forward(name, args):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(SOCK)
    s.sendall((json.dumps({"tool": name, "args": args}) + "\n").encode())
    data = b""
    while not data.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk:
            break
        data += chunk
    s.close()
    return json.loads(data)


def reply(mid, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    msg = json.loads(line)
    mid, method = msg.get("id"), msg.get("method")
    if method == "initialize":
        reply(mid, {"protocolVersion": msg["params"].get("protocolVersion", "2025-06-18"),
                    "capabilities": {"tools": {}}, "serverInfo": {"name": "zplan-tools", "version": "0"}})
    elif method == "tools/list":
        reply(mid, {"tools": TOOLS})
    elif method == "tools/call":
        try:
            out = forward(msg["params"]["name"], msg["params"].get("arguments") or {})
            reply(mid, {"content": [{"type": "text", "text": json.dumps(out)}], "isError": not out.get("ok")})
        except OSError as e:
            reply(mid, {"content": [{"type": "text", "text": "bridge error: %s" % e}], "isError": True})
    elif mid is not None:
        reply(mid, {})
