#!/usr/bin/env python3
"""
SysPulse Mock Linux Agent (Faz 1)
.NET Backend geliştiricisinin C agent olmadan veritabanı, SignalR ve alert
mekanizmasını test edebilmesi için sıfır bağımlılıklı sahte metrik üreticisi.
"""

import argparse
import json
import random
import signal
import sys
import time
import urllib.error
import urllib.request

_running = True


def _handle_signal(signum, frame):
    global _running
    _running = False


def build_payload(host_id, spike=False):
    mem_total = 16 * 1024 * 1024 * 1024
    disk_total = 512_110_190_592

    if spike:
        cpu_usage = round(random.uniform(90.5, 98.5), 1)
        ram_usage = round(random.uniform(92.1, 96.5), 1)
        disk_usage = round(random.uniform(91.0, 96.0), 1)
        load_1m = round(random.uniform(4.2, 7.5), 2)
        disk_read = random.randint(25_000_000, 90_000_000)
        disk_write = random.randint(15_000_000, 60_000_000)
        running_procs = random.randint(8, 22)
    else:
        cpu_usage = round(random.uniform(8.0, 42.0), 1)
        ram_usage = round(random.uniform(35.0, 62.0), 1)
        disk_usage = round(random.uniform(38.0, 52.0), 1)
        load_1m = round(random.uniform(0.3, 1.8), 2)
        disk_read = random.randint(0, 2_500_000)
        disk_write = random.randint(0, 1_500_000)
        running_procs = random.randint(1, 5)

    mem_used = int(mem_total * (ram_usage / 100.0))
    disk_used = int(disk_total * (disk_usage / 100.0))

    if spike:
        top_procs = [
            {
                "pid": 9001,
                "name": "stress-ng",
                "cpu_percent": round(min(100.0, cpu_usage * 0.72), 1),
                "memory_bytes": 1_820_000_000,
            },
            {
                "pid": 1420,
                "name": "firefox",
                "cpu_percent": round(random.uniform(4.5, 9.5), 1),
                "memory_bytes": 620_000_000,
            },
            {
                "pid": 2105,
                "name": "clangd",
                "cpu_percent": round(random.uniform(2.0, 5.0), 1),
                "memory_bytes": 340_000_000,
            },
            {
                "pid": 884,
                "name": "dotnet",
                "cpu_percent": round(random.uniform(1.0, 3.0), 1),
                "memory_bytes": 280_000_000,
            },
            {
                "pid": 512,
                "name": "systemd-journal",
                "cpu_percent": round(random.uniform(0.2, 1.0), 1),
                "memory_bytes": 96_000_000,
            },
        ]
    else:
        top_procs = [
            {
                "pid": 1420,
                "name": "firefox",
                "cpu_percent": round(random.uniform(5.5, 14.0), 1),
                "memory_bytes": 480_000_000,
            },
            {
                "pid": 2105,
                "name": "clangd",
                "cpu_percent": round(random.uniform(2.5, 6.0), 1),
                "memory_bytes": 310_000_000,
            },
            {
                "pid": 884,
                "name": "dotnet",
                "cpu_percent": round(random.uniform(1.2, 3.5), 1),
                "memory_bytes": 240_000_000,
            },
            {
                "pid": 1102,
                "name": "zed-editor",
                "cpu_percent": round(random.uniform(0.6, 2.2), 1),
                "memory_bytes": 195_000_000,
            },
            {
                "pid": 512,
                "name": "systemd-journal",
                "cpu_percent": round(random.uniform(0.1, 0.8), 1),
                "memory_bytes": 84_000_000,
            },
        ]
    top_procs.sort(key=lambda p: (p["cpu_percent"], p["memory_bytes"]), reverse=True)

    return {
        "host_id": host_id,
        "timestamp_ms": int(time.time() * 1000),
        "cpu": {
            "usage_percent": cpu_usage,
            "load_1m": load_1m,
            "core_count": 8,
        },
        "memory": {
            "total_bytes": mem_total,
            "used_bytes": mem_used,
            "usage_percent": ram_usage,
        },
        "disk": {
            "total_bytes": disk_total,
            "used_bytes": disk_used,
            "usage_percent": disk_usage,
            "read_bytes_per_sec": disk_read,
            "write_bytes_per_sec": disk_write,
        },
        "processes": {
            "total_count": 280 + running_procs,
            "running_count": running_procs,
            "top": top_procs,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="SysPulse contract-compliant mock agent")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:5000/api/v1/metrics",
        help="Target ingest URL (default: http://127.0.0.1:5000/api/v1/metrics)",
    )
    parser.add_argument("--host-id", default="mock-linux-01", help="Host identifier")
    parser.add_argument("--interval", type=float, default=2.0, help="Send interval in seconds")
    parser.add_argument("--count", type=int, default=0, help="Number of ticks (0 = infinite)")
    parser.add_argument(
        "--spike",
        action="store_true",
        help="Every 5th tick emits CPU > 90%%, RAM > 92%%, and Disk > 91%% to trigger backend alerts",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    tick = 0
    while _running:
        tick += 1
        # Modulo 5 == 3: periyot 5 (3, 8, 13...) hem kısa 3-tik testlerinde hem uzun akışta spike üretir
        is_spike = bool(args.spike and (tick % 5 == 3))
        payload = build_payload(args.host_id, spike=is_spike)
        raw = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            args.url,
            data=raw,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Connection": "close",
            },
        )

        tag = " [SPIKE]" if is_spike else ""
        cpu_pct = payload["cpu"]["usage_percent"]
        ram_pct = payload["memory"]["usage_percent"]
        disk_pct = payload["disk"]["usage_percent"]
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                body = resp.read().decode("utf-8", errors="replace").strip()
                print(
                    f"[tick {tick}]{tag} cpu={cpu_pct:.1f}% ram={ram_pct:.1f}% disk={disk_pct:.1f}% "
                    f"-> HTTP {resp.status} {body}",
                    flush=True,
                )
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace").strip()
            print(
                f"[tick {tick}]{tag} cpu={cpu_pct:.1f}% ram={ram_pct:.1f}% disk={disk_pct:.1f}% "
                f"-> HTTP {exc.code} {err_body}",
                file=sys.stderr,
                flush=True,
            )
        except urllib.error.URLError as exc:
            print(
                f"[tick {tick}]{tag} connection failed (drop & retry): {exc.reason}",
                file=sys.stderr,
                flush=True,
            )

        if args.count > 0 and tick >= args.count:
            break

        time.sleep(max(0.05, args.interval))

    print("Mock agent stopped cleanly.", flush=True)


if __name__ == "__main__":
    main()
