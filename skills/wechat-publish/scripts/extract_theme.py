#!/usr/bin/env python3
"""
NeuraPress (md.newkit.site) WeChat theme tool — FIXED to the default theme.

Modes:
  list                Print the fixed default theme (offline, from themes.json).
  (no arg / theme-id) Download the live site JS, reconstruct the full CSS
                      (base styles K + theme overrides) for the default theme
                      and write <default-theme-id>.css to the current
                      directory (or -o/--out).

NOTE: this skill intentionally supports ONLY the default theme
(wechat-finance-data / 数据研报). Any other theme id is ignored/rejected;
there is no theme switching in the publishing pipeline either.

Examples:
  python3 extract_theme.py list
  python3 extract_theme.py -o ~/Downloads/themes/
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from themes_lib import build_theme_css, default_theme_id, print_catalog  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="NeuraPress WeChat theme tool (fixed default theme)")
    ap.add_argument("arg", nargs="?", default=None,
                    help="'list' → print the fixed default theme; anything else → extract CSS")
    ap.add_argument("-o", "--out", default=".",
                    help="output directory for extracted CSS")
    args = ap.parse_args()

    # Print the catalog only for a bare `list` WITHOUT an explicit -o.
    # If -o is given (even with `list` as arg), treat it as an extraction
    # request so `extract_theme.py -o <dir>` works as documented.
    if args.arg in (None, "list") and args.out == ".":
        print_catalog()
        return

    # Anything else (including an explicit -o) extracts the default theme CSS.
    # Theme switching is intentionally unsupported; only the default theme
    # (wechat-finance-data) exists in themes.json.
    try:
        full = build_theme_css()
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}")
        sys.exit(1)

    tid = default_theme_id()
    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, f"{tid}.css")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full)
    print(f"OK -> wrote {len(full)} chars to {out_path}")


if __name__ == "__main__":
    main()
