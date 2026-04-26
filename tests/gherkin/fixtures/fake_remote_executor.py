#!/usr/bin/env python3
from __future__ import annotations

import sys


def main() -> int:
    host, ip, username, password, command = sys.argv[1:6]
    if username != "tester" or password != "secret":
        print("authentication failed")
        return 1

    if command == "hostname":
        print(f"mock-hostname-for-{host}")
        return 0

    print(f"unsupported command: {command} on {host} ({ip})")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
