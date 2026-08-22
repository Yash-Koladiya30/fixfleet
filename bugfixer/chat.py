"""Chat engine — natural-language flow control for FixFleet.

Stateless request/response over JSON (the VS Code chat panel calls
`fixfleet --chat-json --message "..."`). The engine answers read-only
requests itself (list, status, file import) and returns an `action` object
for anything that mutates the repo (fixing), so the caller can run it with
progress UI and user consent.

Intent detection: fast regex rules first; if nothing matches and an
OpenAI-compatible API backend is configured, one small AI call maps the
message to an intent.
"""

import json as _json
import re
from pathlib import Path

from . import buglist, config

SESSION_PATH = Path.home() / ".fixfleet-chat.json"

HELP_TEXT = (
    "I can manage your bug-fixing flow. Try:\n"
    "• `load <path to .xlsx / .docx / .pdf>` — import bugs from a file\n"
    "• `list bugs` — show tracked bugs and statuses\n"
    "• `status` — summary counts\n"
    "• `fix #3` — fix one bug\n"
    "• `fix all confident` — auto-fix, keeping only high-confidence fixes\n"
    "• `set threshold 0.8` — change the confidence bar\n"
    "• `skip #3` — mark a bug skipped"
)

_FILE_RE = re.compile(r"(?:^|\s)(['\"]?)((?:~|/|[A-Za-z]:\\)[^'\"\n]+?\.(?:xlsx|docx|pdf))\1",
                      re.IGNORECASE)
_FIX_ONE_RE = re.compile(r"\bfix\b.*?(?:#|bug\s*|issue\s*|number\s*)([\w-]+)", re.IGNORECASE)
_FIX_ALL_RE = re.compile(r"\bfix\b.*\b(all|everything|confident|high[- ]confidence)\b",
                         re.IGNORECASE)
_LIST_RE = re.compile(r"\b(list|show|display)\b.*\b(bugs?|issues?)\b|\bbugs?\s+list\b",
                      re.IGNORECASE)
_STATUS_RE = re.compile(r"\b(status|summary|progress|report)\b", re.IGNORECASE)
_THRESHOLD_RE = re.compile(r"\b(?:threshold|confidence)\b\D*?(0?\.\d+|[01](?:\.\d+)?)",
                           re.IGNORECASE)
_SKIP_RE = re.compile(r"\b(?:skip|ignore)\b.*?(?:#|bug\s*)([\w-]+)", re.IGNORECASE)
_HELP_RE = re.compile(r"\b(help|what can you do|commands?)\b", re.IGNORECASE)


def _session() -> dict:
    try:
        return _json.loads(SESSION_PATH.read_text())
    except (OSError, _json.JSONDecodeError):
        return {}


def _save_session(s: dict):
    try:
        SESSION_PATH.write_text(_json.dumps(s))
    except OSError:
        pass


def _fmt_bug_line(e: dict) -> str:
    conf = e.get("last_confidence")
    conf_s = f" (confidence {conf:.2f})" if isinstance(conf, (int, float)) else ""
    return f"• #{e.get('iid')} [{e.get('status')}] {e.get('title', '')[:70]}{conf_s}"


def _load_file(path: str) -> dict:
    from .files import FileSourceError, parse_bug_file
    try:
        bugs = parse_bug_file(path)
    except FileSourceError as e:
        return {"reply": f"Couldn't load that file: {e.message}", "action": None}
    source = f"file:{Path(path).expanduser().resolve()}"
    stats = buglist.sync(source, bugs)
    s = _session()
    s["last_source"] = source
    s["last_file"] = str(Path(path).expanduser().resolve())
    _save_session(s)
    lines = "\n".join(_fmt_bug_line(
        buglist.get(buglist.bug_key(source, b.get("iid"), b.get("title", ""))))
        for b in bugs[:15])
    more = f"\n…and {len(bugs) - 15} more." if len(bugs) > 15 else ""
    return {
        "reply": (f"Loaded {len(bugs)} open bug(s) from {Path(path).name} "
                  f"({stats['added']} new, {stats['known']} already tracked, "
                  f"{stats['duplicates']} duplicates).\n{lines}{more}\n\n"
                  "Say `fix all confident` to auto-fix, or `fix #<id>` for one."),
        "action": None,
    }


def _ai_intent(message: str) -> dict:
    """LLM fallback: map free text to one of the known intents."""
    cfg = (config.load().get("api") or {})
    if not (cfg.get("base_url") and cfg.get("model")):
        return {}
    from .backends.registry import build_api_backend
    backend = build_api_backend(base_url=cfg["base_url"],
                                api_key=cfg.get("api_key", ""),
                                model=cfg["model"], apply_diff=False)
    prompt = (
        "Map the user's message to ONE intent. Reply with ONLY JSON:\n"
        '{"intent": "load_file|list|status|fix_one|fix_all|set_threshold|skip|help",'
        ' "arg": "<file path, bug id, or threshold if applicable>"}\n\n'
        f"Message: {message}"
    )
    try:
        result = backend.run(prompt, project_dir=".", timeout=45)
        m = re.search(r"\{[^{}]*\}", result.stdout or "")
        return _json.loads(m.group(0)) if m else {}
    except Exception:
        return {}


def handle_message(message: str) -> dict:
    """Return {"reply": str, "action": dict|None, "session": dict}."""
    msg = (message or "").strip()
    s = _session()
    threshold = float(s.get("min_confidence", 0.70))

    def done(reply, action=None):
        return {"reply": reply, "action": action, "session": _session()}

    if not msg or _HELP_RE.search(msg):
        return done(HELP_TEXT)

    fm = _FILE_RE.search(msg)
    if fm:
        return done(**_load_file(fm.group(2)))

    tm = _THRESHOLD_RE.search(msg)
    if tm and "threshold" in msg.lower() or (tm and "set" in msg.lower()):
        val = max(0.0, min(1.0, float(tm.group(1))))
        s["min_confidence"] = val
        _save_session(s)
        return done(f"Confidence threshold set to {val:.2f}. "
                    "Auto-fix will keep only fixes scoring at or above it.")

    sk = _SKIP_RE.search(msg)
    if sk:
        target = _find_bug(sk.group(1), s)
        if not target:
            return done(f"I don't have a bug #{sk.group(1)} in the list.")
        buglist.mark(target["key"], "skipped")
        return done(f"Skipped #{target['iid']} — {target['title'][:60]}")

    if _FIX_ALL_RE.search(msg):
        source = s.get("last_source", "")
        return done(
            f"Starting auto-fix (threshold {threshold:.2f}) — I'll keep only "
            "high-confidence fixes and revert the rest. Watch progress below.",
            action={"type": "auto_fix", "source": source,
                    "file": s.get("last_file", ""), "min_confidence": threshold},
        )

    fo = _FIX_ONE_RE.search(msg)
    if fo:
        target = _find_bug(fo.group(1), s)
        if not target:
            return done(f"I don't have a bug #{fo.group(1)}. "
                        "Say `list bugs` to see what's tracked.")
        return done(
            f"Fixing #{target['iid']} — {target['title'][:60]}…",
            action={"type": "fix_one", "key": target["key"], "iid": target["iid"],
                    "source": target["source"],
                    "file": target["source"][5:] if target["source"].startswith("file:") else "",
                    "min_confidence": threshold},
        )

    if _LIST_RE.search(msg):
        bugs = buglist.list_bugs()
        if not bugs:
            return done("No bugs tracked yet. Load a file (`load /path/bugs.xlsx`) "
                        "or fetch from your tracker in the sidebar.")
        lines = "\n".join(_fmt_bug_line(e) for e in bugs[:20])
        more = f"\n…and {len(bugs) - 20} more." if len(bugs) > 20 else ""
        return done(f"Tracked bugs:\n{lines}{more}")

    if _STATUS_RE.search(msg):
        counts = buglist.summary()
        if not counts:
            return done("Nothing tracked yet — load a bug file or fetch from a tracker.")
        parts = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        return done(f"Bug status: {parts}. Threshold: {threshold:.2f}.")

    # Regex didn't understand → AI fallback, re-dispatch once.
    ai = _ai_intent(msg)
    intent = ai.get("intent", "")
    arg = str(ai.get("arg", "")).strip()
    redispatch = {
        "load_file": f"load {arg}",
        "list": "list bugs",
        "status": "status",
        "fix_one": f"fix #{arg}",
        "fix_all": "fix all confident",
        "set_threshold": f"set threshold {arg}",
        "skip": f"skip #{arg}",
    }.get(intent)
    if redispatch and redispatch != msg:
        return handle_message(redispatch)
    return done("I didn't catch that.\n\n" + HELP_TEXT)


def _find_bug(iid: str, session: dict) -> dict:
    """Locate a bug by iid — prefer the most recently loaded source."""
    candidates = [e for e in buglist.list_bugs() if str(e.get("iid")) == str(iid)]
    if not candidates:
        return {}
    last = session.get("last_source")
    for e in candidates:
        if e.get("source") == last:
            return e
    return candidates[0]
