import json
import claude_session as cs


def test_load_cookie_raw():
    assert cs.load_cookie("sessionKey=abc") == "sessionKey=abc"


def test_load_cookie_json():
    dump = '[{"domain":".claude.ai","name":"sessionKey","value":"abc"},{"domain":"x.com","name":"y","value":"z"}]'
    assert cs.load_cookie(dump) == "sessionKey=abc"


def test_pkce_format():
    v, c = cs.pkce()
    assert 40 <= len(v) <= 96 and "=" not in c and "/" not in c and "+" not in c


def test_sub_type():
    assert cs.sub_type("claude_max") == "max"
    assert cs.sub_type("claude_team") == "team"
    assert cs.sub_type("something_free") == "default_claude_ai"


def test_build_credentials():
    tok = {"access_token": "sk-ant-oat01-x", "refresh_token": "sk-ant-ort01-y",
           "expires_in": 3600, "scope": "user:inference user:profile"}
    c = cs.build_credentials(tok, "claude_max")["claudeAiOauth"]
    assert c["accessToken"] == "sk-ant-oat01-x"
    assert c["refreshToken"] == "sk-ant-ort01-y"
    assert c["subscriptionType"] == "max"
    assert "user:inference" in c["scopes"]
    assert c["expiresAt"] > 0


def test_install_clears_cache(tmp_path):
    (tmp_path / ".claude.json").write_text(json.dumps({
        "userID": "keep", "oauthAccount": {"emailAddress": "old@x.com"},
        "orgModelDefaultCache": {}, "cachedGrowthBookFeatures": {}}))
    creds = {"claudeAiOauth": {"accessToken": "t"}}
    path = cs.install(creds, home=str(tmp_path))
    assert path.exists()
    cfg = json.loads((tmp_path / ".claude.json").read_text())
    assert "oauthAccount" not in cfg and "orgModelDefaultCache" not in cfg
    assert cfg["userID"] == "keep"
    assert json.loads(path.read_text())["claudeAiOauth"]["accessToken"] == "t"
