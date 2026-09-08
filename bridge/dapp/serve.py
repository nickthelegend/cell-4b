#!/usr/bin/env python3
"""Static server for the bench, with a /report sink.

Lives in the repo rather than /tmp, which gets swept: the last copy vanished
mid-session and took the request log with it.

/report exists so a page can hand a diagnostic back to whoever is driving --
it is a plain GET because the payload is a self-test result, not a secret, and
a GET is logged by anything.
"""
import http.server, os, socketserver, urllib.parse, json, sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
REPORTS = []


class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/report?"):
            q = urllib.parse.parse_qs(self.path.split("?", 1)[1])
            try:
                data = json.loads(q.get("r", ["{}"])[0])
            except Exception:
                data = {"raw": q.get("r", [""])[0][:400]}
            REPORTS.append(data)
            print("REPORT " + json.dumps(data), flush=True)
            self.send_response(204); self.end_headers()
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *a):
        print("  " + fmt % a, flush=True)


socketserver.TCPServer.allow_reuse_address = True
print("serving", os.getcwd(), "on 0.0.0.0:8080", flush=True)
socketserver.TCPServer(("0.0.0.0", 8080), H).serve_forever()
