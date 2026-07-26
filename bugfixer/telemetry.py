"""Anonymous usage analytics via GA4 Measurement Protocol (Firebase Analytics).

Privacy rules (do not weaken):
  - Sends ONLY event names + coarse metadata (provider key, backend name,
    success bool, error codes, version). NEVER tokens, URLs, project names,
    issue titles, file paths, or code.
  - Anonymous random client id stored locally in ~/.bugfixer-analytics.json.
  - Opt-out: `fixfleet --config-set telemetry.enabled=false`, or env
    FIXFLEET_TELEMETRY=0 / DO_NOT_TRACK=1.
  - Fire-and-forget on a daemon thread with a short timeout; a telemetry
    failure must never break or slow the tool.

Setup: create a Firebase project with Analytics enabled, add a Web app,
then in GA4 Admin → Data Streams → Measurement Protocol API secrets create
a secret, and fill the two constants below before release.
"""

import json
import os
import threading
import urllib.request
import uuid
from pathlib import Path

from . import __version__

# Fill these from your Firebase/GA4 project (see module docstring).
# Not filled = telemetry silently disabled.
MEASUREMENT_ID = ""  # e.g. "G-XXXXXXXXXX"
API_SECRET = ""      # GA4 Measurement Protocol API secret

ENDPOINT = "https://www.google-analytics.com/mp/collect"
DEBUG_ENDPOINT = "https://www.google-analytics.com/debug/mp/collect"

_ID_PATH = Path.home() / ".bugfixer-analytics.json"

_NOTICE = (
    "FixFleet collects anonymous usage events (event names + coarse metadata "
    "only — never your code, tokens, URLs, or issue content) to find bugs and "
    "improve the tool. Disable anytime:\n"
    "  fixfleet --config-set telemetry.enabled=false\n"
    "This notice is shown once."
)


def _load_id_state() -> dict:
    try:
        return json.loads(_ID_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save_id_state(state: dict):
    try:
        _ID_PATH.write_text(json.dumps(state))
    except OSError:
        pass


def client_id() -> str:
    state = _load_id_state()
    cid = state.get("client_id")
    if not cid:
        cid = str(uuid.uuid4())
        state["client_id"] = cid
        _save_id_state(state)
    return cid


def enabled() -> bool:
    if not MEASUREMENT_ID or not API_SECRET:
        return False
    if os.environ.get("DO_NOT_TRACK", "") not in ("", "0"):
        return False
    if os.environ.get("FIXFLEET_TELEMETRY", "") in ("0", "false", "off"):
        return False
    try:
        from . import config
        t = config.load().get("telemetry")
        if isinstance(t, dict) and t.get("enabled") is False:
            return False
    except Exception:
        pass
    return True


def maybe_show_notice():
    """Print the one-time telemetry disclosure to stderr (interactive CLI only)."""
    if not enabled():
        return
    state = _load_id_state()
    if state.get("notified"):
        return
    state["notified"] = True
    _save_id_state(state)
    import sys
    print(f"\n{_NOTICE}\n", file=sys.stderr)


def _sanitize(params: dict) -> dict:
    """Keep only short scalar values — defense against accidental PII."""
    out = {}
    for k, v in (params or {}).items():
        if isinstance(v, bool):
            out[k] = "true" if v else "false"
        elif isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, str):
            out[k] = v[:80]
    return out


def track(event_name: str, params: dict = None):
    """Send one GA4 event. Non-blocking, never raises."""
    if not enabled():
        return

    body = {
        "client_id": client_id(),
        "events": [{
            "name": event_name,
            "params": {
                "app_version": __version__,
                "platform": os.name,
                "engagement_time_msec": 1,
                **_sanitize(params),
            },
        }],
    }
    debug = os.environ.get("FIXFLEET_TELEMETRY_DEBUG", "") == "1"
    if debug:
        body["events"][0]["params"]["debug_mode"] = 1
    endpoint = DEBUG_ENDPOINT if debug else ENDPOINT
    url = f"{endpoint}?measurement_id={MEASUREMENT_ID}&api_secret={API_SECRET}"

    def _send():
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                if debug:
                    import sys
                    print(f"[telemetry] {event_name}: {resp.read().decode()[:300]}",
                          file=sys.stderr)
        except Exception:
            pass  # telemetry must never break the tool

    threading.Thread(target=_send, daemon=True).start()
