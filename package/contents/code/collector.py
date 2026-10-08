#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 berkkucukk <berkkucukk@proton.me>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Usage collector for the AI Usage plasmoid.

Prints one JSON object on stdout describing every coding agent found on this
machine. Each provider is probed silently; providers that are not installed
or signed in are left out entirely, so the widget only shows what the user
actually has.

Providers and where their numbers come from:

  claude    Claude Code login (~/.claude/.credentials.json) or OpenCode's
            Anthropic login -> api.anthropic.com/api/oauth/usage;
            Claude Code statusline tap; Claude Desktop's plan history file;
            today's tokens from Claude Code session logs.
  codex     Codex CLI login (~/.codex/auth.json) or OpenCode's ChatGPT login
            -> chatgpt.com/backend-api/wham/usage; rate limits recorded in
            Codex session logs; today's tokens from those logs.
  gemini    Gemini CLI Google login (~/.gemini/oauth_creds.json)
            -> cloudcode-pa.googleapis.com retrieveUserQuota (daily, per model).
  copilot   GitHub Copilot editor/CLI login or OpenCode's Copilot login
            -> api.github.com/copilot_internal/user (monthly quotas).
  opencode  OpenCode's local database: today's tokens and cost, plus
            estimated OpenCode Go limits from spend.

Access tokens are only ever read. They are never refreshed: refreshing would
rotate the refresh token behind the owning tool's back and sign it out. When
a token has expired the provider falls back to local data until its own tool
refreshes the token.

Only the Python standard library is used.
"""

import base64
import glob
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
XDG_CONFIG = os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config")
XDG_CACHE = os.environ.get("XDG_CACHE_HOME") or os.path.join(HOME, ".cache")
XDG_DATA = os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share")
CACHE_DIR = os.path.join(XDG_CACHE, "ai-usage-plasmoid")
TAP_CACHE = os.path.join(CACHE_DIR, "claude-statusline.json")

API_MIN_INTERVAL = 120          # seconds between calls to one endpoint
API_BACKOFF = 600               # after 429 / server errors
API_STALE_AFTER = 30 * 60
LOCAL_STALE_AFTER = 45 * 60
USER_AGENT = "ai-usage-plasmoid/2.0"

KIND_ORDER = ["session", "daily", "weekly", "monthly", "model"]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def now_ms():
    return int(time.time() * 1000)


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError:
        pass


def to_ms(value):
    """ISO string, unix seconds or unix milliseconds -> unix milliseconds."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value * 1000) if value < 1e11 else int(value)
    s = str(value).strip()
    if s.isdigit():
        return to_ms(int(s))
    try:
        if len(s) == 10:  # plain date, e.g. "2026-11-01"
            s += "T00:00:00"
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def pct(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return round(max(0.0, min(100.0, v)), 1)


def jwt_claims(token):
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part.encode()).decode())
    except Exception:
        return {}


def expired(expires_ms):
    return isinstance(expires_ms, (int, float)) and expires_ms and to_ms(expires_ms) <= now_ms() + 30000


def local_midnight_ms():
    lt = time.localtime()
    return int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)) * 1000)


def on_path(name):
    for d in os.environ.get("PATH", "").split(os.pathsep) + [os.path.join(HOME, ".local", "bin")]:
        if d and os.access(os.path.join(d, name), os.X_OK):
            return True
    return False


def running_process(names):
    try:
        out = subprocess.run(["ps", "-eo", "args="], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    for line in out.splitlines():
        exe = os.path.basename(line.split(" ", 1)[0]) if line else ""
        if exe in names:
            return True
    return False


def cached_request(key, url, headers, body=None, min_interval=API_MIN_INTERVAL):
    """GET/POST JSON with a per-endpoint cache and backoff.

    Returns (payload, fetched_at_ms) from the freshest successful call, or
    (None, None). Errors never raise.
    """
    path = os.path.join(CACHE_DIR, "api-%s.json" % key)
    cache = read_json(path) or {}
    t = now_ms()
    if t - cache.get("fetched_at", 0) >= min_interval * 1000 and t >= cache.get("retry_after", 0):
        data = json.dumps(body).encode() if body is not None else None
        hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        hdrs.update(headers)
        if data is not None:
            hdrs["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=hdrs, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                cache = {"fetched_at": t, "payload": json.loads(resp.read().decode("utf-8"))}
        except urllib.error.HTTPError as e:
            cache["retry_after"] = t + (API_MIN_INTERVAL if e.code in (401, 403, 404) else API_BACKOFF) * 1000
            cache["last_error"] = e.code
            if e.code in (401, 403):
                # credentials no longer valid: don't keep showing old numbers
                cache.pop("payload", None)
        except (urllib.error.URLError, OSError, ValueError):
            cache["retry_after"] = t + API_MIN_INTERVAL * 1000
        write_json(path, cache)
    if "payload" in cache:
        return cache["payload"], cache.get("fetched_at")
    return None, None


def limit(lid, kind, label, short, used, resets_at=None):
    return {"id": lid, "kind": kind, "label": label, "short": short,
            "used": pct(used), "resets_at": to_ms(resets_at)}


def kind_for_window(seconds):
    if not seconds:
        return "session"
    if seconds <= 6 * 3600:
        return "session"
    if seconds <= 26 * 3600:
        return "daily"
    if seconds <= 8 * 86400:
        return "weekly"
    return "monthly"


def window_short(seconds):
    if not seconds:
        return "?"
    h = seconds / 3600
    if h < 24:
        return "%dH" % round(h)
    d = h / 24
    return "%dD" % round(d) if d < 28 else "MO"


def finish_provider(p, stale_after):
    """Normalise limits, drop empty ones and mark stale/rolled-over data."""
    t = now_ms()
    limits = [l for l in p.get("limits", []) if l.get("used") is not None]
    for l in limits:
        if l.get("resets_at") and l["resets_at"] < t:
            l["used"], l["resets_at"] = 0.0, None
    limits.sort(key=lambda l: KIND_ORDER.index(l["kind"]) if l["kind"] in KIND_ORDER else 99)
    p["limits"] = limits
    upd = p.get("updated_at")
    p["stale"] = bool(limits) and (not upd or t - upd > stale_after * 1000)
    return p


# --------------------------------------------------------------------------
# OpenCode auth (shared: OpenCode can sign into Anthropic, OpenAI, Copilot)
# --------------------------------------------------------------------------

def opencode_dirs():
    cands = [os.path.join(XDG_DATA, "opencode"), os.path.join(HOME, ".local", "share", "opencode")]
    out = []
    for d in cands:
        if os.path.isdir(d) and d not in out:
            out.append(d)
    return out


def opencode_auth():
    for d in opencode_dirs():
        data = read_json(os.path.join(d, "auth.json"))
        if isinstance(data, dict):
            return data
    return {}


# --------------------------------------------------------------------------
# Claude
# --------------------------------------------------------------------------

CLAUDE_LIMITS = {
    "five_hour": ("session", "5-hour", "5H"),
    "seven_day": ("weekly", "Weekly", "7D"),
    "seven_day_opus": ("model", "Weekly · Opus", "OP"),
    "seven_day_sonnet": ("model", "Weekly · Sonnet", "SN"),
    "seven_day_oauth_apps": ("model", "Weekly · Apps", "AP"),
    "seven_day_cowork": ("model", "Weekly · Cowork", "CW"),
}


def claude_config_dirs():
    dirs = []
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        dirs.extend(d for d in env.split(",") if d)
    dirs += [os.path.join(HOME, ".claude"), os.path.join(XDG_CONFIG, "claude")]
    out = []
    for d in dirs:
        d = os.path.expanduser(d)
        if d not in out and os.path.isdir(d):
            out.append(d)
    return out


def claude_global_config():
    paths = [os.path.join(d, ".claude.json") for d in claude_config_dirs()] + [os.path.join(HOME, ".claude.json")]
    fallback = None
    for p in paths:
        data = read_json(p)
        if isinstance(data, dict):
            if data.get("oauthAccount"):
                return data
            fallback = fallback or data
    return fallback


def claude_desktop_dirs():
    cands = [os.path.join(XDG_CONFIG, "Claude")]
    cands += glob.glob(os.path.join(HOME, ".var/app/*/config/Claude"))
    cands += glob.glob(os.path.join(HOME, "snap/*/current/.config/Claude"))
    return [d for d in cands if os.path.isdir(d)]


def claude_plan(creds, gconf):
    account = (gconf or {}).get("oauthAccount") or {}
    kind = ((creds or {}).get("subscriptionType") or account.get("organizationType") or "").lower().replace("claude_", "")
    tier = " ".join(str(x).lower() for x in (
        (creds or {}).get("rateLimitTier"), account.get("organizationRateLimitTier"),
        account.get("userRateLimitTier"), account.get("seatTier")) if x)
    if "enterprise" in kind:
        return "ENTERPRISE"
    if "team" in kind:
        return "TEAM PREMIUM" if "premium" in tier else "TEAM"
    if "max" in kind:
        return "MAX 20X" if "20x" in tier else ("MAX 5X" if "5x" in tier else "MAX")
    if "pro" in kind:
        return "PRO"
    if "free" in kind:
        return "FREE"
    if kind:
        return kind.upper()
    if gconf and (gconf.get("primaryApiKey") or not account):
        return "API"
    return None


def claude_usage_limits(payload):
    out = []
    for key, val in (payload or {}).items():
        if not isinstance(val, dict) or key in ("extra_usage", "limits"):
            continue
        used = val.get("utilization", val.get("used_percentage"))
        kind, label, short = CLAUDE_LIMITS.get(key, ("model", key.replace("_", " ").title(), key[:2].upper()))
        out.append(limit(key, kind, label, short, used, val.get("resets_at")))
    return out


def claude_tokens_today():
    roots = [os.path.join(d, "projects") for d in claude_config_dirs()]
    roots = [r for r in roots if os.path.isdir(r)]
    if not roots:
        return None
    midnight = local_midnight_ms()
    cache_path = os.path.join(CACHE_DIR, "claude-tokens.json")
    cache = read_json(cache_path) or {}
    if cache.get("day") != midnight:
        cache = {"day": midnight, "files": {}}
    files = cache.setdefault("files", {})
    seen = set()
    for root in roots:
        for path in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
            try:
                st = os.stat(path)
            except OSError:
                continue
            if st.st_mtime * 1000 < midnight:
                continue
            seen.add(path)
            e = files.get(path)
            if e and e.get("size") == st.st_size and e.get("mtime") == st.st_mtime:
                continue
            msgs = {}
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if '"usage"' not in line:
                            continue
                        try:
                            rec = json.loads(line)
                        except ValueError:
                            continue
                        msg = rec.get("message") or {}
                        u = msg.get("usage")
                        ts = to_ms(rec.get("timestamp"))
                        if not isinstance(u, dict) or ts is None or ts < midnight:
                            continue
                        msgs["%s:%s" % (msg.get("id"), rec.get("requestId"))] = [
                            int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0),
                            int(u.get("cache_creation_input_tokens") or 0),
                            int(u.get("cache_read_input_tokens") or 0), ts]
            except OSError:
                pass
            files[path] = {"size": st.st_size, "mtime": st.st_mtime, "msgs": msgs}
    for gone in set(files) - seen:
        del files[gone]
    write_json(cache_path, cache)
    merged = {}
    for e in files.values():
        merged.update(e.get("msgs") or {})
    if not merged:
        return None
    tot = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
    last = 0
    for m in merged.values():
        tot["input"] += m[0]
        tot["output"] += m[1]
        tot["cache_write"] += m[2]
        tot["cache_read"] += m[3]
        last = max(last, m[4])
    tot["total"] = sum(tot.values())
    tot["last_active"] = last
    return tot


def provider_claude():
    creds = None
    for d in claude_config_dirs():
        data = read_json(os.path.join(d, ".credentials.json"))
        if isinstance(data, dict) and isinstance(data.get("claudeAiOauth"), dict):
            creds = data["claudeAiOauth"]
            break
    oc = opencode_auth().get("anthropic") or {}
    gconf = claude_global_config()
    desktop = claude_desktop_dirs()
    code_installed = bool(claude_config_dirs()) or on_path("claude")
    if not (creds or desktop or code_installed or oc.get("type") == "oauth"):
        return None

    candidates = []

    # 1. Anthropic usage endpoint with a Claude Code or OpenCode login.
    tokens = []
    if creds and creds.get("accessToken") and not expired(creds.get("expiresAt")):
        tokens.append(creds["accessToken"])
    if oc.get("type") == "oauth" and oc.get("access") and not expired(oc.get("expires")):
        tokens.append(oc["access"])
    for tok in tokens[:1]:
        payload, fetched = cached_request("claude", "https://api.anthropic.com/api/oauth/usage", {
            "Authorization": "Bearer " + tok, "anthropic-beta": "oauth-2025-04-20"})
        lims = claude_usage_limits(payload)
        if lims:
            extra = (payload or {}).get("extra_usage") or {}
            candidates.append({"source": "api", "updated_at": fetched, "limits": lims,
                               "extra": {"label": "Extra usage", "used": pct(extra.get("utilization"))}
                               if extra.get("is_enabled") else None})

    # 2. Statusline tap (opt-in).
    tap = read_json(TAP_CACHE) or {}
    lims = [limit(k, *CLAUDE_LIMITS.get(k, ("model", k, k[:2].upper())), v.get("used_percentage"), v.get("resets_at"))
            for k, v in (tap.get("rate_limits") or {}).items() if isinstance(v, dict)]
    if lims:
        candidates.append({"source": "statusline", "updated_at": tap.get("saved_at"), "limits": lims})

    # 3. Claude Desktop's own plan history (5h / 7d only, no reset times).
    best = None
    for d in desktop:
        samples = (read_json(os.path.join(d, "plan-usage-history.json")) or {}).get("samples") or []
        if samples:
            last = max(samples, key=lambda s: s.get("t", 0))
            if best is None or last.get("t", 0) > best.get("t", 0):
                best = last
    if best:
        u = best.get("u") or {}
        lims = [limit("five_hour", "session", "5-hour", "5H", u.get("fh")),
                limit("seven_day", "weekly", "Weekly", "7D", u.get("sd"))]
        candidates.append({"source": "desktop", "updated_at": best.get("t"), "limits": lims})

    p = {"id": "claude", "name": "Claude", "plan": claude_plan(creds, gconf), "limits": [],
         "source": None, "updated_at": None, "extra": None}
    if candidates:
        top = max(candidates, key=lambda c: c.get("updated_at") or 0)
        p.update({k: top.get(k) for k in ("source", "updated_at", "limits", "extra")})
        have = {l["id"] for l in p["limits"]}
        for c in candidates:
            for l in c["limits"]:
                if l["id"] not in have:
                    p["limits"].append(l)
                    have.add(l["id"])
                elif l.get("resets_at"):
                    for b in p["limits"]:
                        if b["id"] == l["id"] and not b.get("resets_at"):
                            b["resets_at"] = l["resets_at"]

    try:
        p["tokens_today"] = claude_tokens_today()
    except Exception:
        p["tokens_today"] = None
    apps = []
    if desktop:
        apps.append({"name": "Desktop", "running": running_process({"claude-desktop", "Claude", "claude-desktop-bin"})})
    if code_installed:
        apps.append({"name": "Code", "running": running_process({"claude"})})
    p["apps"] = apps
    return finish_provider(p, API_STALE_AFTER if p["source"] in ("api", "statusline") else LOCAL_STALE_AFTER)


# --------------------------------------------------------------------------
# Codex
# --------------------------------------------------------------------------

CODEX_PLANS = {"free": "FREE", "go": "GO", "plus": "PLUS", "pro": "PRO", "team": "TEAM",
               "business": "BUSINESS", "enterprise": "ENTERPRISE", "edu": "EDU", "education": "EDU",
               "free_workspace": "FREE"}


def codex_home():
    return os.path.expanduser(os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex"))


def codex_window(lid, win, label_prefix=""):
    if not isinstance(win, dict):
        return None
    secs = win.get("limit_window_seconds") or (win.get("window_minutes") or 0) * 60
    kind = kind_for_window(secs)
    short = window_short(secs) if secs else ("5H" if lid == "primary" else "7D")
    if not secs:
        kind = "session" if lid == "primary" else "weekly"
    label = {"session": "%s-hour" % short[:-1] if short.endswith("H") else "Session",
             "daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}[kind]
    return limit(label_prefix + lid, kind if not label_prefix else "model",
                 (label_prefix.strip("_").replace("_", " ").title() + " · " + label) if label_prefix else label,
                 short, win.get("used_percent"), win.get("reset_at") or win.get("resets_at"))


def codex_scan_sessions():
    """Latest rate limits and today's tokens from Codex session logs."""
    base = codex_home()
    roots = [os.path.join(base, "sessions"), os.path.join(base, "archived_sessions")]
    midnight = local_midnight_ms()
    files = []
    for r in roots:
        files += glob.glob(os.path.join(r, "**", "*.jsonl"), recursive=True)
    recent = []
    for f in files:
        try:
            m = os.stat(f).st_mtime
        except OSError:
            continue
        if m * 1000 >= midnight - 8 * 86400 * 1000:
            recent.append((m, f))
    recent.sort(reverse=True)

    latest_rl, latest_ts, plan = None, 0, None
    tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    last_active = 0
    for mtime, f in recent[:200]:
        before_midnight_total = None
        last_total = None
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"token_count"' not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    pl = rec.get("payload") or {}
                    if pl.get("type") != "token_count":
                        continue
                    ts = to_ms(rec.get("timestamp")) or 0
                    rl = pl.get("rate_limits")
                    if isinstance(rl, dict) and ts > latest_ts and (rl.get("primary") or rl.get("secondary")):
                        latest_rl, latest_ts = rl, ts
                        plan = rl.get("plan_type") or plan
                    tot = ((pl.get("info") or {}).get("total_token_usage")) or None
                    if isinstance(tot, dict):
                        if ts < midnight:
                            before_midnight_total = tot
                        else:
                            last_total = tot
                            last_active = max(last_active, ts)
        except OSError:
            continue
        if last_total:
            base_tot = before_midnight_total or {}
            d = lambda k: max(0, int(last_total.get(k) or 0) - int(base_tot.get(k) or 0))
            cached = d("cached_input_tokens")
            tokens["input"] += max(0, d("input_tokens") - cached)
            tokens["cache_read"] += cached
            tokens["output"] += d("output_tokens")

    limits = []
    if latest_rl:
        for lid in ("primary", "secondary"):
            win = latest_rl.get(lid)
            if isinstance(win, dict):
                win = dict(win)
                if win.get("resets_at") is None and win.get("resets_in_seconds") is not None:
                    win["resets_at"] = int(latest_ts / 1000 + float(win["resets_in_seconds"]))
                l = codex_window(lid, win)
                if l:
                    limits.append(l)
    tokens["total"] = sum(tokens.values())
    tokens["last_active"] = last_active or None
    return limits, latest_ts or None, plan, (tokens if tokens["total"] else None), bool(files)


def provider_codex():
    home = codex_home()
    auth = read_json(os.path.join(home, "auth.json")) or {}
    oc = opencode_auth().get("openai") or {}
    installed = os.path.isdir(home) or on_path("codex")
    if not (installed or oc.get("type") == "oauth"):
        return None

    p = {"id": "codex", "name": "Codex", "plan": None, "limits": [], "source": None,
         "updated_at": None, "extra": None, "apps": []}

    access, account = None, None
    toks = auth.get("tokens") if isinstance(auth.get("tokens"), dict) else {}
    if toks.get("access_token"):
        access, account = toks["access_token"], toks.get("account_id")
        claims = jwt_claims(toks.get("id_token") or "")
        plan = ((claims.get("https://api.openai.com/auth") or {}).get("chatgpt_plan_type") or "").lower()
        p["plan"] = CODEX_PLANS.get(plan, plan.upper() or None)
    elif oc.get("type") == "oauth" and oc.get("access"):
        access, account = oc["access"], oc.get("accountId") or oc.get("account_id")
    elif auth.get("OPENAI_API_KEY"):
        p["plan"] = "API"
    if access and expired((jwt_claims(access).get("exp") or 0) * 1000 or None):
        access = None

    if access:
        hdrs = {"Authorization": "Bearer " + access}
        if account:
            hdrs["ChatGPT-Account-Id"] = account
        payload, fetched = cached_request("codex", "https://chatgpt.com/backend-api/wham/usage", hdrs)
        if isinstance(payload, dict):
            rl = payload.get("rate_limit") or {}
            lims = [codex_window("primary", rl.get("primary_window")),
                    codex_window("secondary", rl.get("secondary_window"))]
            for extra in payload.get("additional_rate_limits") or []:
                name = (extra or {}).get("limit_name") or (extra or {}).get("metered_feature") or "extra"
                erl = (extra or {}).get("rate_limit") or {}
                lims.append(codex_window("primary", erl.get("primary_window"), label_prefix=name + "_"))
            lims = [l for l in lims if l]
            if lims:
                p.update({"limits": lims, "source": "api", "updated_at": fetched})
            plan = (payload.get("plan_type") or "").lower()
            if plan:
                p["plan"] = CODEX_PLANS.get(plan, plan.upper())
            credits = payload.get("credits") or {}
            if credits.get("has_credits") and credits.get("balance") is not None:
                p["extra"] = {"label": "Credits", "text": str(credits.get("balance"))}

    try:
        lims, ts, plan, tokens, has_logs = codex_scan_sessions()
    except Exception:
        lims, ts, plan, tokens, has_logs = [], None, None, None, False
    if lims and (not p["limits"] or (ts or 0) > (p["updated_at"] or 0)):
        p.update({"limits": lims, "source": "local", "updated_at": ts})
    if plan and not p["plan"]:
        p["plan"] = CODEX_PLANS.get(str(plan).lower(), str(plan).upper())
    p["tokens_today"] = tokens
    if on_path("codex") or os.path.isdir(home):
        p["apps"].append({"name": "CLI", "running": running_process({"codex"})})
    return finish_provider(p, API_STALE_AFTER if p["source"] == "api" else 6 * 3600)


# --------------------------------------------------------------------------
# Gemini CLI
# --------------------------------------------------------------------------

def gemini_model_short(model):
    m = model.lower()
    for key, short in (("flash-lite", "FL"), ("flash", "FL"), ("pro", "PRO")):
        if key in m:
            return short if key != "flash-lite" else "LT"
    return m.replace("gemini-", "")[:3].upper()


def provider_gemini():
    gdir = os.path.join(HOME, ".gemini")
    if not (os.path.isdir(gdir) or on_path("gemini")):
        return None
    p = {"id": "gemini", "name": "Gemini", "plan": None, "limits": [], "source": None,
         "updated_at": None, "extra": None, "tokens_today": None, "apps": []}
    settings = read_json(os.path.join(gdir, "settings.json")) or {}
    auth_type = ((settings.get("security") or {}).get("auth") or {}).get("selectedType") or settings.get("selectedAuthType")
    if auth_type in ("gemini-api-key", "vertex-ai"):
        p["plan"] = "API" if auth_type == "gemini-api-key" else "VERTEX"
    creds = read_json(os.path.join(gdir, "oauth_creds.json")) or {}
    access = creds.get("access_token")
    if access and not expired(creds.get("expiry_date")) and auth_type not in ("gemini-api-key", "vertex-ai"):
        hdrs = {"Authorization": "Bearer " + access}
        ca, _ = cached_request("gemini-ca", "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist", hdrs,
                               body={"metadata": {"ideType": "GEMINI_CLI", "pluginType": "GEMINI"}},
                               min_interval=1800)
        ca = ca or {}
        tier = (ca.get("paidTier") or {}).get("name") or (ca.get("currentTier") or {}).get("name")
        tier_id = (ca.get("currentTier") or {}).get("id") or ""
        if "free" in tier_id:
            p["plan"] = "FREE"
        elif tier:
            p["plan"] = tier.upper()[:16]
        project = ca.get("cloudaicompanionProject")
        if isinstance(project, dict):
            project = project.get("id")
        quota, fetched = cached_request("gemini", "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota",
                                        hdrs, body={"project": project} if project else {})
        per_model = {}
        for b in (quota or {}).get("buckets") or []:
            model, frac = b.get("modelId"), b.get("remainingFraction")
            if not model or frac is None:
                continue
            used = (1 - float(frac)) * 100
            if model not in per_model or used > per_model[model]["used"]:
                per_model[model] = limit("gemini:" + model, "daily", "Gemini " + model.replace("gemini-", "").replace("-", " ").title(),
                                         gemini_model_short(model), used, b.get("resetTime"))
        if per_model:
            # most used first; the panel shows the first one
            p["limits"] = sorted(per_model.values(), key=lambda l: -(l["used"] or 0))
            p["source"], p["updated_at"] = "api", fetched
    if on_path("gemini"):
        p["apps"].append({"name": "CLI", "running": running_process({"gemini"})})
    return finish_provider(p, API_STALE_AFTER)


# --------------------------------------------------------------------------
# GitHub Copilot
# --------------------------------------------------------------------------

def copilot_token():
    for name in ("apps.json", "hosts.json"):
        data = read_json(os.path.join(XDG_CONFIG, "github-copilot", name))
        if isinstance(data, dict):
            for key, val in data.items():
                if key.startswith("github.com") and isinstance(val, dict) and val.get("oauth_token"):
                    return val["oauth_token"]
    oc = opencode_auth().get("github-copilot") or {}
    if oc.get("type") == "oauth" and oc.get("refresh"):
        return oc["refresh"]  # OpenCode keeps the GitHub OAuth token here
    return None


def provider_copilot():
    token = copilot_token()
    if not token:
        return None
    p = {"id": "copilot", "name": "Copilot", "plan": None, "limits": [], "source": None,
         "updated_at": None, "extra": None, "tokens_today": None, "apps": []}
    payload, fetched = cached_request("copilot", "https://api.github.com/copilot_internal/user", {
        "Authorization": "token " + token,
        "Editor-Version": "vscode/1.96.2",
        "Editor-Plugin-Version": "copilot-chat/0.26.7",
        "X-Github-Api-Version": "2025-04-01",
    }, min_interval=300)
    if not isinstance(payload, dict):
        return finish_provider(p, API_STALE_AFTER)
    plan = (payload.get("copilot_plan") or payload.get("access_type_sku") or "").lower()
    p["plan"] = {"individual": "PRO", "individual_pro": "PRO+", "business": "BUSINESS",
                 "enterprise": "ENTERPRISE", "free": "FREE", "free_limited_copilot": "FREE"}.get(plan, plan.upper()[:12] or None)
    reset = payload.get("quota_reset_date") or payload.get("limited_user_reset_date")
    snaps = payload.get("quota_snapshots") or {}
    for key, label, short in (("premium_interactions", "Premium requests", "PR"), ("chat", "Chat", "CH"),
                              ("completions", "Completions", "CO")):
        s = snaps.get(key)
        if not isinstance(s, dict) or s.get("unlimited"):
            continue
        if s.get("percent_remaining") is not None:
            used = 100 - float(s["percent_remaining"])
        elif s.get("entitlement"):
            used = (1 - float(s.get("remaining") or 0) / float(s["entitlement"])) * 100
        else:
            continue
        p["limits"].append(limit("copilot:" + key, "monthly", label, short, used, reset))
    # Free plan reports remaining counts instead of snapshots.
    monthly, left = payload.get("monthly_quotas") or {}, payload.get("limited_user_quotas") or {}
    for key, label, short in (("chat", "Chat", "CH"), ("completions", "Completions", "CO")):
        if not snaps.get(key) and monthly.get(key) and left.get(key) is not None:
            used = (1 - float(left[key]) / float(monthly[key])) * 100
            p["limits"].append(limit("copilot:" + key, "monthly", label, short, used, reset))
    if p["limits"]:
        p["source"], p["updated_at"] = "api", fetched
    return finish_provider(p, API_STALE_AFTER)


# --------------------------------------------------------------------------
# OpenCode
# --------------------------------------------------------------------------

OPENCODE_GO_LIMITS = (("session", 5 * 3600, 12.0, "5-hour", "5H"),
                      ("weekly", None, 30.0, "Weekly", "7D"),
                      ("monthly", None, 60.0, "Monthly", "MO"))


def opencode_rows(since_ms):
    """(created_ms, provider, cost, tokens) for assistant messages since since_ms."""
    rows = []
    for d in opencode_dirs():
        db = os.path.join(d, "opencode.db")
        if os.path.exists(db):
            try:
                con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=2)
                try:
                    cur = con.execute(
                        "SELECT data FROM message WHERE time_created >= ? OR time_created IS NULL",
                        (since_ms,))
                except sqlite3.Error:
                    cur = con.execute("SELECT data FROM message")
                for (data,) in cur:
                    try:
                        m = json.loads(data)
                    except (TypeError, ValueError):
                        continue
                    if m.get("role") != "assistant":
                        continue
                    ts = to_ms((m.get("time") or {}).get("created"))
                    if ts and ts >= since_ms:
                        rows.append((ts, m.get("providerID") or "", float(m.get("cost") or 0), m.get("tokens") or {}))
                con.close()
                continue
            except sqlite3.Error:
                pass
        # Older OpenCode: one JSON file per message.
        for path in glob.glob(os.path.join(d, "storage", "message", "*", "*.json")):
            try:
                if os.stat(path).st_mtime * 1000 < since_ms:
                    continue
            except OSError:
                continue
            m = read_json(path) or {}
            if m.get("role") != "assistant":
                continue
            ts = to_ms((m.get("time") or {}).get("created"))
            if ts and ts >= since_ms:
                rows.append((ts, m.get("providerID") or "", float(m.get("cost") or 0), m.get("tokens") or {}))
    return rows


def provider_opencode():
    dirs = opencode_dirs()
    if not (dirs or on_path("opencode")):
        return None
    p = {"id": "opencode", "name": "OpenCode", "plan": None, "limits": [], "source": None,
         "updated_at": None, "extra": None, "tokens_today": None, "apps": []}
    t = now_ms()
    midnight = local_midnight_ms()
    utc = datetime.now(timezone.utc)
    week_start = int(datetime(utc.year, utc.month, utc.day, tzinfo=timezone.utc).timestamp() * 1000) - utc.weekday() * 86400000
    month_start = int(datetime(utc.year, utc.month, 1, tzinfo=timezone.utc).timestamp() * 1000)
    since = min(midnight, week_start, month_start, t - 5 * 3600 * 1000)
    try:
        rows = opencode_rows(since)
    except Exception:
        rows = []

    today = [r for r in rows if r[0] >= midnight]
    if today:
        tot = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
        cost = 0.0
        for _, _, c, tk in today:
            cache = tk.get("cache") or {}
            tot["input"] += int(tk.get("input") or 0)
            tot["output"] += int(tk.get("output") or 0) + int(tk.get("reasoning") or 0)
            tot["cache_read"] += int(cache.get("read") or 0)
            tot["cache_write"] += int(cache.get("write") or 0)
            cost += c
        tot["total"] = sum(tot.values())
        tot["cost"] = round(cost, 2)
        tot["last_active"] = max(r[0] for r in today)
        p["tokens_today"] = tot

    # OpenCode Go: limits are spend-based ($12 / 5h, $30 / week, $60 / month);
    # estimated from local spend on this machine only.
    go = [r for r in rows if r[1] == "opencode-go"]
    has_go = "opencode-go" in opencode_auth() or bool(go)
    if has_go:
        p["plan"] = "GO"
        session_rows = [r for r in go if r[0] >= t - 5 * 3600 * 1000]
        session_reset = (min(r[0] for r in session_rows) + 5 * 3600 * 1000) if session_rows else None
        week_reset = week_start + 7 * 86400000
        nm = datetime(utc.year + (utc.month == 12), utc.month % 12 + 1, 1, tzinfo=timezone.utc)
        spent = {"session": sum(r[2] for r in session_rows),
                 "weekly": sum(r[2] for r in go if r[0] >= week_start),
                 "monthly": sum(r[2] for r in go if r[0] >= month_start)}
        resets = {"session": session_reset, "weekly": week_reset, "monthly": int(nm.timestamp() * 1000)}
        for kind, _, cap, label, short in OPENCODE_GO_LIMITS:
            p["limits"].append(limit("opencode-go:" + kind, kind, label, short,
                                     spent[kind] / cap * 100, resets[kind]))
        p["source"], p["updated_at"], p["estimated"] = "estimate", t, True
    if on_path("opencode"):
        p["apps"].append({"name": "CLI", "running": running_process({"opencode", ".opencode"})})
    return finish_provider(p, LOCAL_STALE_AFTER)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

PROVIDERS = [provider_claude, provider_codex, provider_gemini, provider_copilot, provider_opencode]


def collect():
    providers = []
    for fn in PROVIDERS:
        try:
            p = fn()
        except Exception as e:  # one broken provider must never hide the others
            p = None
            sys.stderr.write("%s: %s\n" % (fn.__name__, e))
        if p:
            p.setdefault("tokens_today", None)
            p.setdefault("estimated", False)
            providers.append(p)
    return {"version": 2, "generated_at": now_ms(), "providers": providers}


def demo():
    t = now_ms()
    L = limit
    return {"version": 2, "generated_at": t, "providers": [
        {"id": "claude", "name": "Claude", "plan": "MAX 5X", "source": "api", "updated_at": t - 90000,
         "stale": False, "estimated": False, "extra": None,
         "limits": [L("five_hour", "session", "5-hour", "5H", 63, t + 8000000),
                    L("seven_day", "weekly", "Weekly", "7D", 91, t + 190000000),
                    L("seven_day_opus", "model", "Weekly · Opus", "OP", 22, t + 190000000)],
         "tokens_today": {"input": 1200, "output": 84000, "cache_write": 310000, "cache_read": 4200000,
                          "total": 4595200, "last_active": t},
         "apps": [{"name": "Desktop", "running": True}, {"name": "Code", "running": False}]},
        {"id": "codex", "name": "Codex", "plan": "PLUS", "source": "api", "updated_at": t - 60000,
         "stale": False, "estimated": False, "extra": None,
         "limits": [L("primary", "session", "5-hour", "5H", 34, t + 6000000),
                    L("secondary", "weekly", "Weekly", "7D", 58, t + 300000000)],
         "tokens_today": {"input": 52000, "output": 18000, "cache_read": 610000, "cache_write": 0,
                          "total": 680000, "last_active": t}, "apps": [{"name": "CLI", "running": True}]},
        {"id": "gemini", "name": "Gemini", "plan": "FREE", "source": "api", "updated_at": t - 120000,
         "stale": False, "estimated": False, "extra": None,
         "limits": [L("gemini:pro", "daily", "Gemini 2.5 Pro", "PRO", 12, t + 40000000),
                    L("gemini:flash", "daily", "Gemini 2.5 Flash", "FL", 3, t + 40000000)],
         "tokens_today": None, "apps": [{"name": "CLI", "running": False}]},
        {"id": "copilot", "name": "Copilot", "plan": "PRO", "source": "api", "updated_at": t - 200000,
         "stale": False, "estimated": False, "extra": None,
         "limits": [L("copilot:premium_interactions", "monthly", "Premium requests", "PR", 77, t + 1500000000)],
         "tokens_today": None, "apps": []},
        {"id": "opencode", "name": "OpenCode", "plan": "GO", "source": "estimate", "updated_at": t,
         "stale": False, "estimated": True, "extra": None,
         "limits": [L("opencode-go:session", "session", "5-hour", "5H", 18, t + 9000000),
                    L("opencode-go:weekly", "weekly", "Weekly", "7D", 41, t + 400000000),
                    L("opencode-go:monthly", "monthly", "Monthly", "MO", 27, t + 1900000000)],
         "tokens_today": {"input": 90000, "output": 30000, "cache_read": 400000, "cache_write": 20000,
                          "total": 540000, "cost": 1.84, "last_active": t}, "apps": [{"name": "CLI", "running": False}]},
    ]}


def tap(argv):
    """Claude Code statusline passthrough: `collector.py tap [-- original command...]`."""
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
        if isinstance(data.get("rate_limits"), dict) and data["rate_limits"]:
            write_json(TAP_CACHE, {"saved_at": now_ms(), "rate_limits": data["rate_limits"]})
    except ValueError:
        pass
    if argv and argv[0] == "--":
        argv = argv[1:]
    if argv:
        cmd = argv[0] if len(argv) == 1 else subprocess.list2cmdline(argv)
        res = subprocess.run(cmd, shell=True, input=raw, text=True, capture_output=True)
        sys.stdout.write(res.stdout)
        return res.returncode
    return 0


def main():
    if os.environ.get("AI_USAGE_DEMO") or os.environ.get("CLAUDE_PIXEL_USAGE_DEMO"):
        print(json.dumps(demo()))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "tap":
        sys.exit(tap(sys.argv[2:]))
    try:
        out = collect()
    except Exception as e:
        out = {"version": 2, "generated_at": now_ms(), "providers": [], "error": str(e)}
    sys.stdout.write(json.dumps(out, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
