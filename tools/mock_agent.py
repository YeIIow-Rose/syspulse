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


def build_payload(host_id, interval_sec, spike=False):
    total_bytes = 16 * 1024 * 1024 * 1024
    swap_total = 4 * 1024 * 1024 * 1024

    if spike:
        cpu_usage = round(random.uniform(90.5, 98.5), 1)
        ram_usage = round(random.uniform(92.1, 96.5), 1)
        load_1m = round(random.uniform(4.2, 7.5), 2)
        disk_read = random.randint(25_000_000, 90_000_000)
        disk_write = random.randint(15_000_000, 60_000_000)
        running_procs = random.randint(8, 22)
    else:
        cpu_usage = round(random.uniform(8.0, 42.0), 1)
        ram_usage = round(random.uniform(35.0, 62.0), 1)
        load_1m = round(random.uniform(0.3, 1.8), 2)
        disk_read = random.randint(0, 2_500_000)
        disk_write = random.randint(0, 1_500_000)
        running_procs = random.randint(1, 5)

    used_bytes = int(total_bytes * (ram_usage / 100.0))
    available_bytes = total_bytes - used_bytes
    swap_used = int(swap_total * (0.25 if spike else 0.03))

    return {
        "schema_version": 1,
        "host_id": host_id,
        "timestamp_ms": int(time.time() * 1000),
        "interval_sec": int(max(1, round(interval_sec))),
        "cpu": {
            "usage_percent": cpu_usage,
            "load_1m": load_1m,
            "load_5m": round(max(0.1, load_1m * 0.85), 2),
            "load_15m": round(max(0.1, load_1m * 0.72), 2),
            "core_count": 8,
        },
        "memory": {
            "total_bytes": total_bytes,
            "used_bytes": used_bytes,
            "available_bytes": available_bytes,
            "usage_percent": ram_usage,
            "swap_total_bytes": swap_total,
            "swap_used_bytes": swap_used,
        },
        "disk": {
            "read_bytes_per_sec": disk_read,
            "write_bytes_per_sec": disk_write,
        },
        "processes": {
            "total_count": 280 + running_procs,
            "running_count": running_procs,
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
        help="Every 5th tick emits CPU > 90%% and RAM > 92%% to trigger backend alerts",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    tick = 0
    while _running:
        tick += 1
        # Modulo 5 == 3: periyot 5 (3, 8, 13...) hem kısa 3-tik testlerinde hem uzun akışta spike üretir
        is_spike = bool(args.spike and (tick % 5 == 3))
        payload = build_payload(args.host_id, args.interval, spike=is_spike)
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
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                body = resp.read().decode("utf-8", errors="replace").strip()
                print(
                    f"[tick {tick}]{tag} cpu={cpu_pct:.1f}% ram={ram_pct:.1f}% "
                    f"-> HTTP {resp.status} {body}",
                    flush=True,
                )
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace").strip()
            print(
                f"[tick {tick}]{tag} cpu={cpu_pct:.1f}% ram={ram_pct:.1f}% "
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
