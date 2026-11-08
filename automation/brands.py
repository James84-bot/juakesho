"""
brands.py — one engine, several brands. KOR_BRAND picks the brand a run works for; unset, it is Kenya on Record,
exactly as before (its files stay where they always were).

Every other brand lives in automation/brands/<slug>/: its brand.json (name, look, Page, writer brief), calendar.json,
content/ (feeds, policy, weeks) and state/. Its pictures and Reels go to exports/<slug>/. Shared by all brands:
the code, the templates, the fonts, the music library and the face model.

Accounts never cross: for a brand other than the main one, every account key (Meta, YouTube, TikTok, Telegram bot)
comes from that brand's own GitHub secret (KEY__SLUG) and is cleared when the brand has none, so a sport post can
never go out on Kenya on Record's accounts. Its Facebook Page token comes from META_PAGES (one me/accounts dump that
covers every Page), matched by the Page id in its brand.json.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MAIN_SLUG = "kenyaonrecord"
ACCOUNT_KEYS = ("META_ACCESS_TOKEN", "META_PAGE_ID", "META_IG_USER_ID", "YT_REFRESH_TOKEN", "TIKTOK_REFRESH_TOKEN",
                "TELEGRAM_BOT_TOKEN")


def slug_of(raw: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", str(raw or "").lower()) or MAIN_SLUG


SLUG = slug_of(os.environ.get("KOR_BRAND"))
MAIN = SLUG == MAIN_SLUG
HOME = HERE if MAIN else HERE / "brands" / SLUG          # brand.json and calendar.json
CONTENT = HOME / "content"                               # feeds, policy, weeks
STATE = HOME / "state"
EXPORTS = ROOT / "exports" if MAIN else ROOT / "exports" / SLUG
URL_PATH = "exports" if MAIN else f"exports/{SLUG}"      # where GitHub Pages serves EXPORTS


def shared(rel: str) -> Path:
    """A file every brand may use when it has none of its own (the Kenyan newsrooms' photo feeds, the TV channels)."""
    own = HOME / rel
    return own if MAIN or own.exists() else HERE / rel


def brand(slug: str | None = None) -> dict:
    home = HOME if slug is None else (HERE if slug_of(slug) == MAIN_SLUG else HERE / "brands" / slug_of(slug))
    try:
        return json.loads((home / "brand.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def enabled() -> list[str]:
    """The brands the schedule runs: Kenya on Record first, then every brand folder whose brand.json says enabled."""
    out = [MAIN_SLUG]
    folder = HERE / "brands"
    if folder.is_dir():
        for d in sorted(folder.iterdir()):
            if d.is_dir() and brand(d.name).get("enabled") and d.name == slug_of(d.name):
                out.append(d.name)
    return out


def _pages(raw: str) -> list[dict]:
    """The Pages in a me/accounts response (pasted whole: {"data": [...]}), or a bare list of them."""
    try:
        got = json.loads(raw or "")
    except ValueError:
        return []
    got = got.get("data", []) if isinstance(got, dict) else got
    return [p for p in got if isinstance(p, dict) and p.get("id") and p.get("access_token")] if isinstance(got, list) else []


def apply_env(environ: dict | None = None) -> list[str]:
    """Points the account keys at this brand's own accounts (see the module note). Returns the keys it has no value
    for, so a run can say what is missing. The main brand is left exactly as it is."""
    env = os.environ if environ is None else environ
    if MAIN:
        return []
    try:
        secrets = json.loads(env.get("BRAND_SECRETS") or "{}")
    except ValueError:
        secrets = {}

    def get(key: str) -> str:
        return str(env.get(key) or secrets.get(key) or "")

    for key in ACCOUNT_KEYS:
        env[key] = get(f"{key}__{SLUG.upper()}")
    b = brand()
    page_id = str(b.get("facebook_page_id") or "")
    if page_id and not env["META_ACCESS_TOKEN"]:
        page = next((p for p in _pages(get("META_PAGES")) if str(p["id"]) == page_id), None)
        if page:
            env["META_ACCESS_TOKEN"], env["META_PAGE_ID"] = page["access_token"], page_id
    if b.get("instagram_id") and not env["META_IG_USER_ID"]:
        env["META_IG_USER_ID"] = str(b["instagram_id"])
    return [k for k in ACCOUNT_KEYS if not env.get(k)]
