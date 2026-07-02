#!/usr/bin/env python3
"""Turn a claude.ai cookie into a ready-to-use Claude Code session.

Given an account's `sessionKey` cookie, this runs the Claude Code OAuth flow
silently (its own PKCE — no browser, no console URL) and prints a ready
`.credentials.json` (accessToken + refreshToken). With --install it drops the
session straight into Claude Code and clears the cached account so the new
session actually takes effect.

DISCLAIMER
    Provided AS IS, WITHOUT WARRANTY OF ANY KIND. Use ONLY with accounts you own
    and are authorized to access. Session cookies and tokens grant full account
    access — treat them like passwords. The authors accept NO liability.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests

CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
REDIRECT = "https://platform.claude.com/oauth/code/callback"
SCOPES = "org:create_api_key user:profile user:inference user:sessions:claude_code user:mcp_servers user:file_upload"
CC_SCOPES = ["user:file_upload", "user:inference", "user:mcp_servers", "user:profile", "user:sessions:claude_code"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def load_cookie(src: str) -> str:
    p = Path(src)
    text = p.read_text(encoding="utf-8").strip() if p.exists() else src.strip()
    if text[:1] in "[{":
        data = json.loads(text)
        cookies = data.get("cookies", data) if isinstance(data, dict) else data
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies
                         if "claude" in (c.get("domain", "").lower()) and c.get("name"))
    if "\t" in text:
        return "; ".join(f"{c[5]}={c[6]}" for c in
                         (ln.split("\t") for ln in text.splitlines() if ln and not ln.startswith("#"))
                         if len(c) >= 7 and "claude" in c[0].lower())
    return text


def make_session(cookie: str, proxy=None) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    for pair in cookie.split(";"):
        if "=" in pair:
            n, v = pair.strip().split("=", 1)
            s.cookies.set(n.strip(), v.strip(), domain=".claude.ai")
    return s


def get_org(session):
    r = session.get("https://claude.ai/api/account", timeout=15)
    if r.status_code != 200:
        raise SystemExit(f"cookie rejected ({r.status_code}) — expired or wrong account")
    acc = r.json()
    memberships = acc.get("memberships") or acc.get("account", {}).get("memberships") or []
    for m in memberships:
        org = m.get("organization", {})
        if org.get("uuid"):
            email = acc.get("email_address") or acc.get("account", {}).get("email_address", "?")
            otype = (org.get("organization_type") or org.get("billing_type") or "").lower()
            return org["uuid"], email, otype
    raise SystemExit("no organization on this account")


def pkce():
    v = secrets.token_urlsafe(64)[:96]
    c = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    return v, c


def authorize(session, org_uuid):
    v, c = pkce()
    state = secrets.token_urlsafe(32)
    body = {"response_type": "code", "client_id": CLIENT_ID, "code_challenge": c,
            "code_challenge_method": "S256", "organization_uuid": org_uuid,
            "redirect_uri": REDIRECT, "scope": SCOPES, "state": state}
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "Origin": "https://claude.ai", "Referer": "https://claude.ai/oauth/authorize"}
    r = session.post(f"https://claude.ai/v1/oauth/{org_uuid}/authorize",
                     json=body, headers=headers, timeout=15, allow_redirects=False)
    loc = r.headers.get("Location") or ""
    if "code=" in loc:
        return v, parse_qs(urlparse(loc).query).get("code", [None])[0], state
    if r.headers.get("content-type", "").startswith("application/json"):
        d = r.json()
        code = d.get("code") or d.get("authorization_code")
        if not code:
            redir = d.get("redirect") or d.get("redirect_uri") or ""
            if "code=" in redir:
                code = parse_qs(urlparse(redir).query).get("code", [None])[0]
        if code:
            return v, code, state
    raise SystemExit(f"authorize failed: {r.status_code}: {r.text[:200]}")


def exchange(verifier, code, state, proxy=None):
    body = {"grant_type": "authorization_code", "client_id": CLIENT_ID, "code": code,
            "redirect_uri": REDIRECT, "code_verifier": verifier, "state": state}
    p = {"http": proxy, "https": proxy} if proxy else None
    r = requests.post(TOKEN_URL, json=body, headers={"Content-Type": "application/json"},
                      timeout=15, proxies=p)
    if r.status_code != 200:
        raise SystemExit(f"token exchange failed: {r.status_code}: {r.text[:200]}")
    return r.json()


def sub_type(otype: str) -> str:
    for k in ("max", "pro", "team", "enterprise"):
        if k in otype:
            return k
    return "default_claude_ai"


def build_credentials(tok, otype):
    exp = int(time.time() * 1000) + int(tok.get("expires_in", 31536000)) * 1000
    scopes = tok.get("scope", "").split() or CC_SCOPES
    return {"claudeAiOauth": {
        "accessToken": tok["access_token"],
        "refreshToken": tok.get("refresh_token", ""),
        "expiresAt": exp,
        "scopes": scopes,
        "subscriptionType": sub_type(otype),
    }}


def install(creds, home=None):
    home = Path(home or os.path.expanduser("~"))
    (home / ".claude").mkdir(exist_ok=True)
    cred_path = home / ".claude" / ".credentials.json"
    cred_path.write_text(json.dumps(creds, indent=2))
    os.chmod(cred_path, 0o600)
    # clear the cached account so Claude Code re-fetches the new profile
    cfg_path = home / ".claude.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text())
        for k in ("oauthAccount", "orgModelDefaultCache", "cachedGrowthBookFeatures"):
            cfg.pop(k, None)
        cfg_path.write_text(json.dumps(cfg, indent=2))
    return cred_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="claude.ai cookie -> ready Claude Code session")
    ap.add_argument("--cookie", required=True, help="sessionKey=... string or a cookie file (json/netscape/raw)")
    ap.add_argument("--install", action="store_true", help="write ~/.claude/.credentials.json and clear the cached account")
    ap.add_argument("--out", help="write the credentials JSON to a file")
    ap.add_argument("--proxy", help="optional proxy http://user:pass@host:port")
    a = ap.parse_args(argv)

    session = make_session(load_cookie(a.cookie), a.proxy)
    org_uuid, email, otype = get_org(session)
    print(f"account: {email} ({otype or '?'})", file=sys.stderr)
    verifier, code, state = authorize(session, org_uuid)
    tok = exchange(verifier, code, state, a.proxy)
    creds = build_credentials(tok, otype)

    if a.install:
        path = install(creds)
        print(f"installed -> {path}\nrestart Claude Code (`claude`) — it will re-fetch the new account", file=sys.stderr)
    text = json.dumps(creds, indent=2)
    if a.out:
        Path(a.out).write_text(text)
        print(f"wrote {a.out}", file=sys.stderr)
    elif not a.install:
        print(text)


if __name__ == "__main__":
    main()
