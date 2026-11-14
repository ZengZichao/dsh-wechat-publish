#!/usr/bin/env python3
"""
Shared helpers for the NeuraPress WeChat theme skill.

This skill is intentionally FIXED to the default theme (wechat-finance-data /
数据研报): no theme switching, no category browsing. The catalog in themes.json
holds exactly one entry and build_theme_css() always targets it.

- Catalog data (offline) from themes.json
- Live CSS extraction from md.newkit.site (base styles K + theme overrides)
"""

import json
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(HERE, "..", "themes.json")
SITE = "https://md.newkit.site/"


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def get_main_js_url(html):
    m = re.search(r'src="(/assets/js/index-[^"]+\.js)"', html)
    if not m:
        raise RuntimeError("Could not locate main JS bundle in the page HTML.")
    return SITE.rstrip("/") + m.group(1)


def get_base_k(js):
    m = re.search(r'\bK=\`(.*?)\`', js, re.DOTALL)
    if not m:
        raise RuntimeError("Could not locate base styles (K) in JS.")
    return m.group(1)


def get_theme_css(js, tid):
    pat = re.compile(
        r'id:"' + re.escape(tid) + r'",name:"[^"]*",description:"[^"]*",'
        r'category:"[^"]*",css:K\+\`(.*?)\`',
        re.DOTALL,
    )
    m = pat.search(js)
    return m.group(1) if m else None


def load_catalog():
    with open(CATALOG, encoding="utf-8") as f:
        return json.load(f)


def default_theme_id():
    """The single theme this skill is fixed to (from themes.json)."""
    themes = load_catalog()
    if not themes:
        raise RuntimeError(f"themes.json is empty; expected the default theme entry.")
    if len(themes) > 1:
        raise RuntimeError(
            f"themes.json must hold exactly ONE theme (fixed-theme design), "
            f"found {len(themes)}."
        )
    return themes[0]["id"]


def fetch_live_js():
    """Download the live main JS bundle and return its text."""
    html = fetch(SITE)
    js_url = get_main_js_url(html)
    return fetch(js_url)


def build_theme_css():
    """Fetch live and reconstruct the full CSS for the FIXED default theme."""
    tid = default_theme_id()
    js = fetch_live_js()
    k = get_base_k(js)
    theme_css = get_theme_css(js, tid)
    if theme_css is None:
        raise KeyError(f"theme '{tid}' not found in the live bundle")
    return k + theme_css


def list_themes():
    """Return the (single) theme catalog entry."""
    return load_catalog()


def print_catalog():
    """Print the fixed default theme."""
    themes = load_catalog()
    print(f"\n固定主题（唯一，不支持切换）:")
    for t in themes:
        print(f"  {t['id']:<28} {t['name']}  — {t['description']}")
    print("\n如需浏览全部主题，请访问 https://md.newkit.site/")
