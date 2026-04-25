"""Console script entry for GUI mode (`jamol-gui` command)."""

from __future__ import annotations

import sys

from jamol.__main__ import main as jamol_main


def main() -> int:
    argv = list(sys.argv[1:])
    if "--gui" not in argv:
        argv.append("--gui")
    return jamol_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
