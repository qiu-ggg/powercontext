import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PYTHON = os.environ.get("SANDBOX_PYTHON", sys.executable)
API_KEY = os.environ.get("CODE_EXECUTION_API_KEY", "dify-sandbox")


class Handler(BaseHTTPRequestHandler):
    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/v1/sandbox/run":
            self._json(404, {"code": 404, "message": "not found", "data": {"stdout": None, "error": "not found"}})
            return
        if self.headers.get("X-Api-Key") != API_KEY:
            self._json(401, {"code": 401, "message": "unauthorized", "data": {"stdout": None, "error": "unauthorized"}})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            self._json(400, {"code": 400, "message": str(exc), "data": {"stdout": None, "error": str(exc)}})
            return

        code = (payload.get("preload") or "") + "\n" + (payload.get("code") or "")
        try:
            proc = subprocess.run(
                [PYTHON, "-I", "-c", code],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                env={"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"},
            )
        except subprocess.TimeoutExpired:
            self._json(200, {"code": 0, "message": "ok", "data": {"stdout": "", "error": "timeout"}})
            return

        if proc.returncode != 0:
            self._json(
                200,
                {
                    "code": 0,
                    "message": "ok",
                    "data": {"stdout": proc.stdout, "error": proc.stderr or f"exit {proc.returncode}"},
                },
            )
            return
        self._json(200, {"code": 0, "message": "ok", "data": {"stdout": proc.stdout, "error": None}})

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    port = int(os.environ.get("SANDBOX_PORT", "8194"))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
