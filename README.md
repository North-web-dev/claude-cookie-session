# claude-cookie-session

Turn a **claude.ai cookie** into a **ready-to-use Claude Code session** — no
browser, no console URL. Give it an account's `sessionKey`, it runs the Claude
Code OAuth flow silently and hands you a working `.credentials.json` (access +
refresh token). With `--install` it drops the session into Claude Code and
clears the cached account so the switch actually takes.

## Install

```
pip install -r requirements.txt   # just `requests`
```

## Usage

Print a ready credentials block:

```
python claude_session.py --cookie "sessionKey=sk-ant-sid01-..."
```

Install straight into Claude Code (writes `~/.claude/.credentials.json` + clears
the cached account):

```
python claude_session.py --cookie cookies.json --install
```

Then restart `claude` — it re-fetches the profile under the new token.

`--cookie` accepts a raw `sessionKey=...` string, a file with one, a browser
extension JSON cookie dump, or a Netscape `cookies.txt`. `--out FILE` writes the
JSON; `--proxy` routes through a proxy.

## How it works

1. Load the `sessionKey` cookie into a session.
2. `GET /api/account` → resolve the organization UUID (and confirm the cookie is
   live).
3. `POST /v1/oauth/{org}/authorize` with a freshly generated **PKCE** challenge
   (S256) → the server returns an authorization `code`. No browser, no pasted
   URL — the tool is both the requester and the approver.
4. Exchange the `code` at `platform.claude.com/v1/oauth/token` → `access_token`
   + `refresh_token`.
5. Assemble the `claudeAiOauth` block Claude Code expects.

## The gotcha this solves: "I set a new session but it shows the old account"

Claude Code keeps the **token** and the **displayed account** in two different
places:

- `~/.claude/.credentials.json` → `claudeAiOauth` — the token.
- `~/.claude.json` → **`oauthAccount`** — a *cached* profile (email / org /
  plan).

Replacing only the token leaves `oauthAccount` stale, so Claude Code keeps
showing the old account. `--install` fixes this by removing `oauthAccount`
(plus `orgModelDefaultCache`, `cachedGrowthBookFeatures`) from `~/.claude.json`,
so the next `claude` launch re-fetches the profile for the new token.

To clear the cache by hand:

```bash
python3 -c "import json;p='$HOME/.claude.json';d=json.load(open(p));[d.pop(k,None) for k in ['oauthAccount','orgModelDefaultCache','cachedGrowthBookFeatures']];json.dump(d,open(p,'w'),indent=2)"
```

## Disclaimer

Provided **as is, without warranty of any kind**. Use **only** with accounts you
own and are authorized to access. Session cookies and OAuth tokens grant full
account access — treat them like passwords. Extracting or using session data
from accounts you do not own may be unlawful and violates the provider's Terms
of Service. The authors accept no liability for misuse.

## License

MIT — see [LICENSE](LICENSE).
