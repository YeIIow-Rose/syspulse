#!/usr/bin/env python3
"""
SysPulse Mock Backend Server (Faz 1)
C Agent geliştiricisinin .NET backend olmadan HTTP/1.1 + JSON sözleşmesini
birebir doğrulayabilmesi için sıfır bağımlılıklı test sunucusu.
"""

import argparse
import json
import math
import re
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST_ID_RE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")

_lock = threading.Lock()
_next_id = 1


def _is_int(val):
    return isinstance(val, int) and not isinstance(val, bool)


def _is_number(val):
    if isinstance(val, bool):
        return False
    if not isinstance(val, (int, float)):
        return False
    return math.isfinite(float(val))


def validate_payload(data):
    errors = []
    if not isinstance(data, dict):
        return ["Root payload must be a JSON object"]

    if not _is_int(data.get("schema_version")) or data.get("schema_version") != 1:
        errors.append("schema_version must be integer 1")

    host_id = data.get("host_id")
    if not isinstance(host_id, str) or not HOST_ID_RE.match(host_id):
        errors.append("host_id must be a string (1..64 chars, [a-zA-Z0-9._-])")

    ts = data.get("timestamp_ms")
    if not _is_int(ts) or ts <= 0:
        errors.append("timestamp_ms must be integer > 0")

    interval = data.get("interval_sec")
    if not _is_int(interval) or not (1 <= interval <= 3600):
        errors.append("interval_sec must be integer in 1..3600")

    # cpu
    cpu = data.get("cpu")
    if not isinstance(cpu, dict):
        errors.append("cpu must be an object")
    else:
        u = cpu.get("usage_percent")
        if not _is_number(u) or not (0.0 <= float(u) <= 100.0):
            errors.append("cpu.usage_percent must be number in 0.0..100.0")
        for lf in ("load_1m", "load_5m", "load_15m"):
            lv = cpu.get(lf)
            if not _is_number(lv) or float(lv) < 0.0:
                errors.append(f"cpu.{lf} must be number >= 0.0")
        cores = cpu.get("core_count")
        if not _is_int(cores) or cores < 1:
            errors.append("cpu.core_count must be integer >= 1")

    # memory
    mem = data.get("memory")
    if not isinstance(mem, dict):
        errors.append("memory must be an object")
    else:
        for mf in (
            "total_bytes",
            "used_bytes",
            "available_bytes",
            "swap_total_bytes",
            "swap_used_bytes",
        ):
            mv = mem.get(mf)
            if not _is_int(mv) or mv < 0:
                errors.append(f"memory.{mf} must be integer >= 0")
        mu = mem.get("usage_percent")
        if not _is_number(mu) or not (0.0 <= float(mu) <= 100.0):
            errors.append("memory.usage_percent must be number in 0.0..100.0")

    # disk
    disk = data.get("disk")
    if not isinstance(disk, dict):
        errors.append("disk must be an object")
    else:
        for df in ("read_bytes_per_sec", "write_bytes_per_sec"):
            dv = disk.get(df)
            if not _is_int(dv) or dv < 0:
                errors.append(f"disk.{df} must be integer >= 0")

    # processes
    procs = data.get("processes")
    if not isinstance(procs, dict):
        errors.append("processes must be an object")
    else:
        for pf in ("total_count", "running_count"):
            pv = procs.get(pf)
            if not _is_int(pv) or pv < 0:
                errors.append(f"processes.{pf} must be integer >= 0")
        if "top" in procs and procs["top"] is not None and not isinstance(procs["top"], list):
            errors.append("processes.top must be an array or null if present")

    return errors


def _reject_nan_inf(token):
    raise ValueError(f"Invalid JSON number constant: {token}")


class MockHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Varsayılan gürültülü access log yerine temiz özet basılır
        return

    def _send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/v1/health":
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self):
        global _next_id

        if self.path != "/api/v1/metrics":
            self._send_json(404, {"error": "not_found"})
            return

        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("application/json"):
            msg = f"Invalid Content-Type: {content_type!r} (expected application/json)"
            print(f"[400] {msg}", file=sys.stderr, flush=True)
            self._send_json(400, {"error": msg})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            content_length = -1

        if content_length <= 0 or content_length > 1024 * 1024:
            msg = "Missing or invalid Content-Length"
            print(f"[400] {msg}", file=sys.stderr, flush=True)
            self._send_json(400, {"error": msg})
            return

        raw_body = self.rfile.read(content_length)
        try:
            data = json.loads(raw_body.decode("utf-8"), parse_constant=_reject_nan_inf)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            msg = f"Invalid JSON: {exc}"
            print(f"[400] {msg}", file=sys.stderr, flush=True)
            self._send_json(400, {"error": msg})
            return

        errors = validate_payload(data)
        if errors:
            print(f"[400] Validation errors: {errors}", file=sys.stderr, flush=True)
            self._send_json(400, {"error": "; ".join(errors)})
            return

        with _lock:
            assigned_id = _next_id
            _next_id += 1

        cpu_pct = data["cpu"]["usage_percent"]
        ram_pct = data["memory"]["usage_percent"]
        disk_r = data["disk"]["read_bytes_per_sec"]
        disk_w = data["disk"]["write_bytes_per_sec"]
        procs_run = data["processes"]["running_count"]
        procs_tot = data["processes"]["total_count"]
        print(
            f"[#{assigned_id}] host={data['host_id']} "
            f"cpu={cpu_pct:.1f}% ram={ram_pct:.1f}% "
            f"disk={disk_r}/{disk_w} B/s procs={procs_run}/{procs_tot}",
            flush=True,
        )
        self._send_json(201, {"status": "accepted", "id": assigned_id})


def main():
    parser = argparse.ArgumentParser(description="SysPulse contract-validating mock server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Bind port (default: 5000)")
    args = parser.parse_args()

    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((args.host, args.port), MockHandler)

    def _shutdown(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    print(f"SysPulse mock server listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down mock server...", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
