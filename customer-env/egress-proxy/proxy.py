"""Egress proxy for the simulated customer network.

The only way out of the private network. It accepts HTTPS tunnels (CONNECT) to
hosts on the allow-list and refuses everything else: plain HTTP, other hosts,
other ports. Every decision is logged as one JSON line, so the customer's
security team can see exactly what the application tried to reach.

Standard library only; no third-party code runs on the network boundary.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

LISTEN_PORT = int(os.environ.get("PROXY_PORT", "3128"))
ALLOWLIST_FILE = Path(os.environ.get("ALLOWLIST_FILE", Path(__file__).with_name("allowlist.txt")))
IDLE_TIMEOUT_S = 120


def load_allowlist(path: Path = ALLOWLIST_FILE) -> set[tuple[str, int]]:
    """Read 'host:port' lines; '#' starts a comment."""
    allowed: set[tuple[str, int]] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip().lower()
        if not line:
            continue
        host, _, port = line.partition(":")
        allowed.add((host, int(port or 443)))
    return allowed


ALLOWED = load_allowlist()


def log(event: str, **fields) -> None:
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, **fields}),
          flush=True)


def parse_target(request_line: str) -> tuple[str, str, int] | None:
    """'CONNECT host:443 HTTP/1.1' -> ('CONNECT', 'host', 443). None if malformed."""
    parts = request_line.split()
    if len(parts) != 3:
        return None
    method, target, _ = parts
    if method.upper() != "CONNECT":
        return method.upper(), target, 0
    host, _, port = target.rpartition(":")
    if not host or not port.isdigit():
        return None
    return "CONNECT", host.strip("[]").lower(), int(port)


def is_allowed(method: str, host: str, port: int, allowed: set[tuple[str, int]] | None = None) -> bool:
    return method == "CONNECT" and (host, port) in (ALLOWED if allowed is None else allowed)


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await asyncio.wait_for(reader.read(65536), IDLE_TIMEOUT_S):
            writer.write(data)
            await writer.drain()
    except (asyncio.TimeoutError, ConnectionError, OSError):
        pass
    finally:
        writer.close()


async def handle(client_r: asyncio.StreamReader, client_w: asyncio.StreamWriter) -> None:
    peer = client_w.get_extra_info("peername")
    source = peer[0] if peer else "unknown"
    try:
        head = await asyncio.wait_for(client_r.readuntil(b"\r\n\r\n"), 10)
    except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
        client_w.close()
        return
    request_line = head.split(b"\r\n", 1)[0].decode("latin-1")
    target = parse_target(request_line)
    if target is None:
        log("egress_denied", source=source, reason="malformed request")
        client_w.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
        await client_w.drain()
        client_w.close()
        return
    method, host, port = target
    if not is_allowed(method, host, port):
        log("egress_denied", source=source, method=method, host=host, port=port, reason="not on allow-list")
        client_w.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
        await client_w.drain()
        client_w.close()
        return
    try:
        up_r, up_w = await asyncio.wait_for(asyncio.open_connection(host, port), 10)
    except (OSError, asyncio.TimeoutError) as exc:
        log("egress_error", source=source, host=host, port=port, error=type(exc).__name__)
        client_w.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        await client_w.drain()
        client_w.close()
        return
    log("egress_allowed", source=source, host=host, port=port)
    client_w.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    await client_w.drain()
    await asyncio.gather(pipe(client_r, up_w), pipe(up_r, client_w))


async def main() -> None:
    server = await asyncio.start_server(handle, "0.0.0.0", LISTEN_PORT)
    log("proxy_started", port=LISTEN_PORT, allowlist=sorted(f"{h}:{p}" for h, p in ALLOWED))
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
