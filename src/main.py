from __future__ import annotations

import sys

from commands.cli import main


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("KeyboardInterrupt; exiting.", file=sys.stderr, flush=True)
        raise SystemExit(130)
    except Exception:
        print("fatal error: unhandled exception", file=sys.stderr, flush=True)
        raise
