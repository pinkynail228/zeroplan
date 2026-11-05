"""The local web view: read-only HTML pages on port 8731."""
import html
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import store

PORT = 8731


class Pages(BaseHTTPRequestHandler):
    def do_GET(self):
        rows = "".join("<li>%s</li>" % html.escape(book["title"]) for book in store.load())
        body = ("<h1>shelf</h1><ul>%s</ul>" % rows).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", PORT), Pages).serve_forever()
