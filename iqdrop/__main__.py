"""Command line entry point: hook actions go to hook.py, setup commands to install.py."""

from __future__ import annotations

import sys


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    if action in ('capture', 'score', 'explain'):
        from iqdrop import hook
        hook.main(sys.argv[1:])
    elif action == 'stats':
        from iqdrop import stats
        stats.main(sys.argv[2:])
    elif action == 'models':
        from iqdrop import stats
        stats.models_main(sys.argv[2:])
    elif action == 'now':
        from iqdrop import stats
        stats.now_main(sys.argv[2:])
    else:
        from iqdrop import install
        install.main(sys.argv[1:])


if __name__ == '__main__':
    main()
