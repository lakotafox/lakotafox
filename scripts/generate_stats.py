#!/usr/bin/env python3
"""Draw contribution stats as SVGs from the GitHub GraphQL API.

Standard library only — this runs nightly in CI and must not have
dependencies that can break. Writes svg/{stats,streak,langs,year}-{dark,light}.svg.

Determinism rules (so the nightly run produces no diff on quiet days):
  - the contribution window is pinned to whole UTC days
  - only public, non-fork, owned repositories count toward languages

Env: GITHUB_TOKEN (the workflow's built-in token), GH_LOGIN.
Pass --mock to render with synthetic data (local layout testing, no API).
"""
import base64
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "svg"
RAMP = " .`:-=+*cs#%@"

PALETTES = {
    "dark": {
        "accent": "#a78bfa", "bright": "#c4b5fd", "text": "#e6edf3",
        "dim": "#8b949e", "faint": "#30363d",
    },
    "light": {
        "accent": "#6d28d9", "bright": "#7c3aed", "text": "#24292f",
        "dim": "#57606a", "faint": "#d0d7de",
    },
}

FONT_B64 = base64.b64encode((ROOT / "assets" / "ui.woff2").read_bytes()).decode()
RAMP_B64 = base64.b64encode((ROOT / "assets" / "ramp.woff2").read_bytes()).decode()


def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {os.environ['GITHUB_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as r:
        body = json.load(r)
    if "errors" in body:
        raise SystemExit(f"GraphQL errors: {body['errors']}")
    return body["data"]


QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC,
                 isFork: false, orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""


def fetch():
    today = dt.datetime.now(dt.timezone.utc).date()
    frm = f"{today - dt.timedelta(days=364)}T00:00:00Z"
    to = f"{today}T23:59:59Z"
    data = gql(QUERY, {"login": os.environ["GH_LOGIN"], "from": frm, "to": to})
    user = data["user"]
    days = [
        (dt.date.fromisoformat(d["date"]), d["contributionCount"])
        for w in user["contributionsCollection"]["contributionCalendar"]["weeks"]
        for d in w["contributionDays"]
    ]
    total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    langs = {}
    for repo in user["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            b, n = langs.get(name, (0, 0))
            langs[name] = (b + e["size"], n + 1)
    return total, days, langs


def mock():
    import random
    random.seed(7)
    today = dt.datetime.now(dt.timezone.utc).date()
    days = [
        (today - dt.timedelta(days=364 - i), random.choice([0, 0, 0, 1, 2, 3, 5, 8, 12]))
        for i in range(365)
    ]
    langs = {
        "Python": (410_000, 9), "JavaScript": (350_000, 11), "HTML": (120_000, 8),
        "CSS": (90_000, 7), "GDScript": (60_000, 2), "Java": (30_000, 3),
    }
    return sum(c for _, c in days), days, langs


def streaks(days):
    cur = longest = 0
    cur_range = longest_range = None
    run_start = None
    for date, count in days:
        if count > 0:
            if run_start is None:
                run_start = date
            run = (date - run_start).days + 1
            if run > longest:
                longest, longest_range = run, (run_start, date)
        else:
            run_start = None
    # current streak counts back from the last day (today) or yesterday
    tail = [c for _, c in days]
    i = len(tail) - 1
    if tail[i] == 0:
        i -= 1  # today may simply have no contributions yet
    while i >= 0 and tail[i] > 0:
        cur += 1
        i -= 1
    if cur:
        end_i = len(tail) - 1 if tail[-1] > 0 else len(tail) - 2
        cur_range = (days[end_i - cur + 1][0], days[end_i][0])
    return cur, cur_range, longest, longest_range


def fmt_range(rng):
    if not rng:
        return "—"
    a, b = rng
    if a == b:
        return a.strftime("%b %-d")
    return f"{a.strftime('%b %-d')} – {b.strftime('%b %-d')}"


def svg_open(w, h, label, p, with_ramp=False):
    fonts = f"@font-face{{font-family:'JBM';src:url(data:font/woff2;base64,{FONT_B64}) format('woff2');}}"
    if with_ramp:
        fonts += f"@font-face{{font-family:'JBMRamp';src:url(data:font/woff2;base64,{RAMP_B64}) format('woff2');}}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-label="{label}">'
        f"<defs><style>{fonts}"
        f"text{{font-family:'JBM','JetBrains Mono',monospace;}}"
        f".num{{fill:{p['text']};font-size:44px;}}"
        f".big{{fill:{p['text']};font-size:26px;}}"
        f".lab{{fill:{p['dim']};font-size:13px;}}"
        f".acc{{fill:{p['accent']};font-size:13px;}}"
        "</style></defs>"
    )


def render_stats(total, days, p):
    w, h = 820, 150
    weeks = [days[i:i + 7] for i in range(0, len(days), 7)]
    sums = [sum(c for _, c in wk) for wk in weeks]
    peak = max(max(sums), 1)
    # area sparkline of weekly totals (weekly aggregation makes a line honest)
    x0, y0, cw, chh = 330, 30, 460, 84
    step = cw / (len(sums) - 1)
    pts = [(x0 + i * step, y0 + chh - (s / peak) * chh) for i, s in enumerate(sums)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{x0:.1f},{y0 + chh} " + line + f" {x0 + cw:.1f},{y0 + chh}"
    return (
        svg_open(w, h, f"{total} contributions in the last year", p)
        + f'<text x="24" y="72" class="num">{total:,}</text>'
        + f'<text x="24" y="100" class="lab">contributions · last 365 days</text>'
        + f'<text x="24" y="122" class="acc">busiest week · {peak} contributions</text>'
        + f'<polygon points="{area}" fill="{p["accent"]}" opacity="0.16"/>'
        + f'<polyline points="{line}" fill="none" stroke="{p["accent"]}" stroke-width="1.6"/>'
        + f'<line x1="{x0}" y1="{y0 + chh}" x2="{x0 + cw}" y2="{y0 + chh}" stroke="{p["faint"]}" stroke-width="1"/>'
        + f'<text x="{x0}" y="{y0 + chh + 20}" class="lab">52 weeks, weekly totals</text>'
        + "</svg>"
    )


def render_streak(days, p):
    cur, cur_rng, longest, longest_rng, = streaks(days)
    active = sum(1 for _, c in days if c > 0)
    w, h = 820, 130
    cols = [
        (f"{cur}", "day current streak" if cur == 1 else "day current streak", fmt_range(cur_rng), 24),
        (f"{longest}", "day longest streak" if longest == 1 else "day longest streak", fmt_range(longest_rng), 310),
        (f"{active}", "active days this year", f"{active}/365", 596),
    ]
    out = svg_open(w, h, f"current streak {cur} days, longest {longest} days", p)
    for i, (num, lab, rng, x) in enumerate(cols):
        if i:
            out += f'<line x1="{x - 24}" y1="28" x2="{x - 24}" y2="102" stroke="{p["faint"]}" stroke-width="1"/>'
        out += (
            f'<text x="{x}" y="62" class="num">{num}</text>'
            f'<text x="{x}" y="86" class="lab">{lab}</text>'
            f'<text x="{x}" y="106" class="acc">{rng}</text>'
        )
    return out + "</svg>"


def render_langs(langs, p):
    top = sorted(langs.items(), key=lambda kv: -kv[1][0])[:6]
    total_bytes = sum(b for b, _ in langs.values()) or 1
    w, row_h, top_pad = 820, 34, 30
    h = top_pad + row_h * len(top) + 10
    out = svg_open(w, h, "top languages in public repositories", p)
    bar_x, bar_w = 220, 420
    for i, (name, (b, n)) in enumerate(top):
        y = top_pad + i * row_h
        pct = b / total_bytes * 100
        out += (
            f'<text x="24" y="{y + 16}" class="acc" font-size="14">{name.lower()}</text>'
            f'<rect x="{bar_x}" y="{y + 5}" width="{bar_w}" height="10" rx="5" fill="{p["faint"]}"/>'
            f'<rect x="{bar_x}" y="{y + 5}" width="{max(bar_w * pct / 100, 6):.1f}" height="10" rx="5" fill="{p["accent"]}"/>'
            f'<text x="{bar_x + bar_w + 18}" y="{y + 15}" class="lab">{pct:.1f}% · {n} repo{"s" if n != 1 else ""}</text>'
        )
    return out + "</svg>"


def render_year(days, p):
    # one character per day, portrait ramp, columns are weeks
    char_w, line_h, fs = 9.6, 16, 16
    weeks = [days[i:i + 7] for i in range(0, len(days), 7)]
    peak = max((c for _, c in days), default=1) or 1
    x0, y0 = 24, 26
    w = 820
    h = int(y0 + 7 * line_h + 26)
    out = svg_open(w, h, "a year of contributions, one character per day", p, with_ramp=True)
    out += (
        f"<style>.ramp{{font-family:'JBMRamp','JetBrains Mono',monospace;"
        f"font-size:{fs}px;fill:{p['accent']};}}</style>"
    )
    for r in range(7):
        chars = []
        for wk in weeks:
            if r < len(wk):
                _, c = wk[r]
                lvl = 0 if c == 0 else max(1, round((c / peak) ** 0.5 * (len(RAMP) - 1)))
                chars.append(RAMP[lvl])
            else:
                chars.append(" ")
        row = "".join(chars).replace("&", "&amp;").replace("<", "&lt;")
        out += (
            f'<text x="{x0}" y="{y0 + r * line_h + fs - 3}" xml:space="preserve" class="ramp" '
            f'textLength="{len(chars) * char_w:.1f}" lengthAdjust="spacing">{row}</text>'
        )
    out += f'<text x="{x0}" y="{h - 8}" class="lab">last 365 days · one character per day, drawn with the portrait ramp</text>'
    return out + "</svg>"


def main():
    total, days, langs = mock() if "--mock" in sys.argv else fetch()
    OUT.mkdir(exist_ok=True)
    for theme, p in PALETTES.items():
        for name, svg in {
            "stats": render_stats(total, days, p),
            "streak": render_streak(days, p),
            "langs": render_langs(langs, p),
            "year": render_year(days, p),
        }.items():
            (OUT / f"{name}-{theme}.svg").write_text(svg)
            print(f"wrote svg/{name}-{theme}.svg")


if __name__ == "__main__":
    main()
