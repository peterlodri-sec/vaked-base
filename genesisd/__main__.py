"""genesisd CLI entry point.

Usage::

    python3 -m genesisd [--bind-ip IP] [--bind-port PORT] [--genesis-id ID]

Or after packaging::

    vaked-genesis [--bind-ip IP] ...

Environment variables:

    GENESISD_LOG_DIR   Override the audit log directory (default: $STATE_DIR/vaked-genesis/log)
"""
from __future__ import annotations

import sys

from .server import run_server


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="vaked-genesis",
        description="Vaked genesis bootstrap daemon — bootstrap entry point for the mesh",
    )
    parser.add_argument("--bind-ip", default="127.0.0.1",
                        help="IP address to bind to (default: 127.0.0.1)")
    parser.add_argument("--bind-port", type=int, default=4433,
                        help="TCP port (default: 4433)")
    parser.add_argument("--genesis-id", default="genesis.vaked.dev",
                        help="Genesis node identifier (default: genesis.vaked.dev)")
    parser.add_argument("--log-dir",
                        help="Directory for the audit log")
    args = parser.parse_args(argv)

    run_server(**vars(args))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
