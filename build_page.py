#!/usr/bin/env python3
"""Fetch the leaderboard once, update history state, and render docs/index.html."""

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEFAULT_URL = "https://fr4.assettohosting.com:50161/leaderboards/embed/21a6ad87-8c99-4f54-a6e1-b601669c05ea"
DEFAULT_NAME = "Adriano Gastaldello"
CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
OUT_FILE = "docs/index.html"
MAX_HISTORY = 100


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        return {"url": cfg.get("url", DEFAULT_URL), "name": cfg.get("name", DEFAULT_NAME)}
    return {"url": DEFAULT_URL, "name": DEFAULT_NAME}


def rows_url(u: str) -> str:
    return u.rstrip("/") + "/rows"


def fetch_rows(u: str) -> list:
    req = urllib.request.Request(rows_url(u), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def fetch_track(u: str) -> str | None:
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    m = re.search(r'<p class="track">(.*?)</p>', html, re.DOTALL)
    return m.group(1).strip() if m else None


def clean_name(name: str) -> str:
    return re.sub(r"\s*\[[^\]]*\]\s*", " ", name).strip()


def parse_lap_time(text: str) -> float | None:
    m = re.match(r"^(\d+):(\d+)\.(\d+)$", text.strip())
    if not m:
        return None
    minutes, seconds, millis = m.groups()
    return int(minutes) * 60 + int(seconds) + int(millis) / (10 ** len(millis))


def find_driver(rows: list, name: str) -> dict | None:
    name_lower = name.lower()
    for row in rows:
        full_name = clean_name(row.get("FullName", ""))
        if full_name.lower() == name_lower or name_lower in row.get("FullName", "").lower():
            return row
    return None


def table_rows(rows: list, position: int, max_steps: int = 3) -> list[tuple]:
    by_pos = {r["Position"]: r for r in rows}
    driver = by_pos.get(position)
    if driver is None:
        return []
    driver_time = parse_lap_time(driver["BestLap"])

    entries = []
    for step in range(max_steps, 0, -1):
        target_pos = position - step
        if target_pos < 1:
            continue
        target = by_pos.get(target_pos)
        if target is None:
            continue
        target_time = parse_lap_time(target["BestLap"])
        if target_time is None or driver_time is None:
            continue
        gap = f"-{driver_time - target_time:.3f}s"
        entries.append((target["Position"], clean_name(target["FullName"]), target["BestLap"], gap))

    entries.append((driver["Position"], clean_name(driver["FullName"]), driver["BestLap"], ""))

    behind = by_pos.get(position + 1)
    if behind is not None:
        behind_time = parse_lap_time(behind["BestLap"])
        gap = f"+{behind_time - driver_time:.3f}s" if behind_time is not None and driver_time is not None else ""
        entries.append((behind["Position"], clean_name(behind["FullName"]), behind["BestLap"], gap))

    return entries


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)
    else:
        state = {}
    state.setdefault("position", None)
    state.setdefault("best_lap", None)
    state.setdefault("car", None)
    state.setdefault("track", None)
    state.setdefault("history", [])
    return state


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def render_html(entries: list, driver_pos: int | None, driver_name: str, state: dict, updated: str, stale: bool = False) -> str:
    rows_html = "".join(
        f'<tr class="{"me" if pos == driver_pos else ""}">'
        f"<td>#{pos:02d}</td><td>{name}</td><td>{time_}</td><td>{gap}</td></tr>\n"
        for pos, name, time_, gap in entries
    )

    history = state["history"]
    event_start = max(
        (i for i, h in enumerate(history) if h["text"].startswith("nuovo evento")),
        default=0,
    )
    current_week_history = history[event_start:]

    history_html = "".join(
        f"<li>{h['when']} — {h['text']}</li>\n" for h in reversed(current_week_history)
    )

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="120">
<title>Hotlap — {driver_name}</title>
<style>
html,body{{overflow-x:hidden}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,sans-serif;background:#18181b;color:#fff;padding:1.5rem;font-size:20px;max-width:900px;margin:0 auto;text-align:center}}
.logo-wrap{{display:flex;align-items:center;justify-content:center;margin-bottom:1rem}}
.logo{{max-height:220px;max-width:100%;width:auto}}
h1{{font-size:32px;margin-bottom:.25rem}}
.updated{{opacity:.5;font-size:15px;margin-bottom:1.5rem}}
.table-wrap{{width:90%;margin:0 auto 2rem;overflow-x:auto}}
table{{width:100%;margin:0 auto;border-collapse:collapse}}
thead tr{{background:#c0392b;text-align:center}}
th{{padding:.6rem .9rem;font-size:15px;text-transform:uppercase;opacity:.8;text-align:center;white-space:nowrap}}
td{{padding:.6rem .9rem;font-family:monospace;font-size:18px;text-align:center;white-space:nowrap}}
tbody tr{{border-bottom:1px solid #333}}
tr.me{{background:#2a2a2e;font-weight:700}}
h2{{font-size:20px;opacity:.7;margin-bottom:.5rem}}
ul{{list-style:none;font-size:16px;opacity:.8;line-height:1.7;width:90%;margin:0 auto}}
.event{{opacity:.7;font-size:16px;margin-bottom:.25rem}}
.stale{{color:#f39c12;font-size:14px;margin-bottom:1rem}}
@media (max-width:480px){{
  body{{padding:1rem;font-size:16px}}
  h1{{font-size:22px}}
  .logo{{max-height:140px}}
  td,th{{padding:.4rem .5rem;font-size:14px}}
  ul{{font-size:13px}}
}}
</style>
</head>
<body>
<div class="logo-wrap"><img class="logo" src="assets/ops.png" alt="Logo"></div>
<h1>Hotlap Position</h1>
<div class="event">{state.get('car') or '?'} — {state.get('track') or '?'}</div>
<div class="updated">Aggiornato: {updated}</div>
{'<div class="stale">Evento non raggiungibile, mostro ultimo dato disponibile</div>' if stale else ''}
<div class="table-wrap">
<table>
<thead><tr><th>#</th><th>Driver</th><th>Best Lap</th><th>Gap</th></tr></thead>
<tbody>
{rows_html}
</tbody>
</table>
</div>
<h2>Storico cambi (settimana corrente)</h2>
<ul>
{history_html}
</ul>
</body>
</html>
"""


def main():
    config = load_config()
    url = config["url"]
    name = config["name"]
    state = load_state()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    try:
        rows = fetch_rows(url)
        track = fetch_track(url)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        print(f"Evento non raggiungibile ({exc}), mantengo ultimo dato disponibile")
        if not os.path.exists(OUT_FILE):
            os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
            html = render_html([], None, name, state, now, stale=True)
            with open(OUT_FILE, "w", encoding="utf-8") as f:
                f.write(html)
        return

    driver = find_driver(rows, name)
    car = driver["CarName"] if driver else (rows[0]["CarName"] if rows else None)

    if car and track and (car, track) != (state.get("car"), state.get("track")):
        state["history"].append({"when": now, "text": f"nuovo evento: {car} — {track}"})
        state["car"] = car
        state["track"] = track
        state["position"] = None
        state["best_lap"] = None

    entries = []
    if driver is not None:
        pos = driver["Position"]
        best_lap = driver["BestLap"]

        if state["position"] is None:
            state["history"].append({"when": now, "text": f"trovato: #{pos}, best lap {best_lap}"})
        elif pos != state["position"]:
            direction = "su" if pos < state["position"] else "giu"
            state["history"].append(
                {"when": now, "text": f"{direction}: #{state['position']} -> #{pos} (best lap {best_lap})"}
            )
        elif best_lap != state["best_lap"]:
            state["history"].append({"when": now, "text": f"nuovo best lap: {best_lap} (ancora #{pos})"})

        state["position"] = pos
        state["best_lap"] = best_lap
        state["history"] = state["history"][-MAX_HISTORY:]
        entries = table_rows(rows, pos)

    save_state(state)

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    html = render_html(
        entries,
        driver["Position"] if driver else None,
        clean_name(driver["FullName"]) if driver else name,
        state,
        now,
    )
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
