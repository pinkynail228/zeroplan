"""Synthetic Responses HTTP/SSE and RFC6455 fixture, no external forwarding.

Event shapes match pinned Codex rust-v0.160.1 core/tests/common/responses.rs.
The proxy terminates CONNECT locally; an independently counted origin catches
any bypass. No requests, authorization headers or model inputs are logged.
"""

import base64
import hashlib
import http.server
import json
import re
import struct
import sys


def events(request):
    schema = request.get("text", {}).get("format", {}).get("schema", {})
    text = json.dumps(schema)
    if '"signals"' in text:
        candidates = re.findall(r"candidate_[0-9a-f]{64}", text)
        assert candidates
        result = {"output": {"candidate": candidates[0]}, "signals": {"verdict": "accepted"},
                  "diagnostic": {"message": "synthetic independent transport fixture"}}
    else:
        result = {"candidate": "pending"}
    return [
        {"type": "response.created", "response": {"id": "fixture-response"}},
        {"type": "response.output_item.done", "item": {"type": "message", "role": "assistant",
         "id": "fixture-message", "content": [{"type": "output_text", "text": json.dumps({"response": result})}]}},
        {"type": "response.completed", "response": {"id": "fixture-response", "usage": {
         "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}}},
    ]


def serve(port=8080, expected=None):
    counts = dict(authenticated=0, rejected=0, http=0, websocket=0, connect=0, direct=0)

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def answer(self, status, body, kind="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()

        def admitted(self):
            if expected is None:
                counts["direct"] += 1
                return True
            if getattr(self, "tunnel", False):
                return True
            if self.headers.get("Proxy-Authorization", "").encode() != expected:
                counts["rejected"] += 1
                self.answer(407, b'{"error":"fixture proxy authentication required"}')
                return False
            counts["authenticated"] += 1
            return True

        def do_CONNECT(self):
            if self.path != "fixture-origin:8080":
                self.answer(403, b'{"error":"external destination denied by fixture"}')
                return
            if not self.admitted():
                return
            counts["connect"] += 1
            self.tunnel = True
            self.send_response(200)
            self.end_headers()
            self.wfile.flush()
            self.handle_one_request()

        def do_GET(self):
            if self.path == "/counts":
                self.answer(200, json.dumps(counts).encode())
                return
            if not self.admitted():
                return
            if self.headers.get("Upgrade", "").lower() != "websocket":
                self.answer(200, b'{"models":[],"data":[]}')
                return
            counts["websocket"] += 1
            key = self.headers["Sec-WebSocket-Key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", base64.b64encode(hashlib.sha1(key.encode()).digest()).decode())
            self.end_headers()
            self.wfile.flush()
            first, second = self.rfile.read(2)
            assert first & 15 == 1 and second & 128
            size = second & 127
            if size == 126:
                size = struct.unpack("!H", self.rfile.read(2))[0]
            elif size == 127:
                size = struct.unpack("!Q", self.rfile.read(8))[0]
            assert size <= 1048576
            mask = self.rfile.read(4)
            raw = self.rfile.read(size)
            request = json.loads(bytes(b ^ mask[i % 4] for i, b in enumerate(raw)))
            assert request["type"] == "response.create"
            for event in events(request):
                payload = json.dumps(event).encode()
                prefix = bytes([129, len(payload)]) if len(payload) < 126 else bytes([129, 126]) + struct.pack("!H", len(payload))
                self.wfile.write(prefix + payload)
            self.wfile.flush()
            self.close_connection = True

        def do_POST(self):
            size = int(self.headers.get("Content-Length", "0"))
            assert 0 < size <= 1048576
            raw = self.rfile.read(size)
            if not self.admitted():
                return
            counts["http"] += 1
            body = b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events(json.loads(raw)))
            self.answer(200, body, "text/event-stream")

    class Server(http.server.ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            # Client closes idle/reused sockets during normal turn shutdown.
            # Never print request bytes or raw server/parser exceptions.
            pass
    Server(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    expected = sys.stdin.buffer.readline().strip()
    serve(expected=expected or None)
