#!/usr/bin/env python3
"""Builds a self-hosted GitHub stats card (assets/stats.svg).

    GITHUB_TOKEN=... python scripts/build_stats.py <github-user> [out.svg]
    python scripts/build_stats.py <github-user> out.svg --mock   # fake data, for previewing the design

Uses only the standard library. In CI the built-in GITHUB_TOKEN is enough
(public data only).
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from collections import defaultdict
from html import escape
from pathlib import Path

# ------------------------------------------------------------------ EDIT ME
EXCLUDE_LANGS = {"Jupyter Notebook"}          # languages to hide from the bars
MAX_LANGS = 5
PROMPT_CMD = "git summary --last-12-months"
# ---------------------------------------------------------------------------

BG, PANEL, PANEL2 = "#1a1b26", "#16161e", "#24283b"
BORDER, FG, COMMENT = "#2a2e42", "#c0caf5", "#565f89"
BLUE, CYAN, GREEN, PURPLE = "#7aa2f7", "#7dcfff", "#9ece6a", "#bb9af7"
ORANGE, RED, YELLOW, TEAL = "#ff9e64", "#f7768e", "#e0af68", "#73daca"
LANG_COLORS = [BLUE, GREEN, YELLOW, PURPLE, ORANGE, CYAN, RED, TEAL]
FONT = "'JetBrains Mono','Fira Code','SF Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',monospace"

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 8, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""


def fetch(login, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "profile-stats-card"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload or not payload.get("data", {}).get("user"):
        raise SystemExit(f"GitHub API error: {payload.get('errors') or 'user not found'}")
    return payload["data"]["user"]


def streaks(user):
    days = sorted(
        (d["date"], d["contributionCount"])
        for w in user["contributionsCollection"]["contributionCalendar"]["weeks"]
        for d in w["contributionDays"]
    )
    longest = run = 0
    for _, c in days:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    # current streak: walk back from today (today may still be empty)
    cur, i = 0, len(days) - 1
    if i >= 0 and days[i][1] == 0:
        i -= 1
    while i >= 0 and days[i][1] > 0:
        cur += 1
        i -= 1
    return cur, longest


def summarise(user):
    cc = user["contributionsCollection"]
    repos = user["repositories"]["nodes"]
    langs = defaultdict(int)
    for r in repos:
        for e in r["languages"]["edges"]:
            if e["node"]["name"] not in EXCLUDE_LANGS:
                langs[e["node"]["name"]] += e["size"]
    total = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1])[:MAX_LANGS]
    cur, longest = streaks(user)
    return {
        "commits": cc["totalCommitContributions"],
        "prs": cc["totalPullRequestContributions"],
        "issues": cc["totalIssueContributions"],
        "repos": user["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "cur": cur,
        "longest": longest,
        "langs": [(n, 100 * v / total) for n, v in top],
    }


def mock():
    return {
        "commits": 412, "prs": 38, "issues": 9, "repos": 24, "stars": 17,
        "cur": 6, "longest": 31,
        "langs": [("Python", 46.0), ("TypeScript", 27.5), ("JavaScript", 14.0), ("Dart", 7.0), ("CSS", 5.5)],
    }


def render(login, st):
    W, H = 880, 330
    rows = [
        ("commits", st["commits"], BLUE),
        ("pull requests", st["prs"], PURPLE),
        ("issues", st["issues"], CYAN),
        ("public repos", st["repos"], GREEN),
        ("stars earned", st["stars"], YELLOW),
        ("current streak", f'{st["cur"]} days', ORANGE),
        ("longest streak", f'{st["longest"]} days', RED),
    ]
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    s = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t">
<title id="t">GitHub stats for {escape(login)}: {escape(", ".join(f"{l} {v}" for l, v, _ in rows))}. Top languages: {escape(", ".join(f"{n} {p:.0f}%" for n, p in st["langs"]))}</title>
<style>
  .l{{animation:in .45s ease-out both}}
  @keyframes in{{from{{opacity:0;transform:translateX(-8px)}}to{{opacity:1;transform:none}}}}
  .bar{{transform-origin:left;animation:grow .9s ease-out both}}
  @keyframes grow{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
  text{{white-space:pre}}
</style>
<defs>
  <clipPath id="win"><rect width="{W}" height="{H}" rx="14"/></clipPath>
  <pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#000" opacity="0.14"/></pattern>
  <radialGradient id="vig" cx="50%" cy="45%" r="75%"><stop offset="60%" stop-color="#000" stop-opacity="0"/><stop offset="100%" stop-color="#000" stop-opacity="0.35"/></radialGradient>
</defs>
<g clip-path="url(#win)">
<rect width="{W}" height="{H}" fill="{BG}"/>
<rect width="{W}" height="40" fill="{PANEL}"/>
<circle cx="26" cy="20" r="6" fill="{RED}"/><circle cx="46" cy="20" r="6" fill="{YELLOW}"/><circle cx="66" cy="20" r="6" fill="{GREEN}"/>
<text x="{W/2}" y="25" text-anchor="middle" font-family="{FONT}" font-size="12" fill="{COMMENT}">{escape(login)}@github — stats</text>
<g class="l"><text x="32" y="78" font-family="{FONT}" font-size="14"><tspan fill="{GREEN}">$</tspan><tspan fill="{FG}"> {escape(PROMPT_CMD)}</tspan></text></g>
'''
    for i, (label, val, col) in enumerate(rows):
        y = 112 + i * 27
        s += (
            f'<g class="l" style="animation-delay:{0.2+0.1*i:.2f}s">'
            f'<text x="32" y="{y}" font-family="{FONT}" font-size="14" fill="{COMMENT}">{escape(label)}</text>'
            f'<text x="250" y="{y}" text-anchor="end" font-family="{FONT}" font-size="14" font-weight="bold" fill="{col}">{escape(str(val))}</text></g>\n'
        )
    # languages
    s += f'<g class="l" style="animation-delay:0.2s"><text x="420" y="112" font-family="{FONT}" font-size="12" fill="{COMMENT}"># top languages</text></g>\n'
    bx, bw = 560, 220
    for i, (name, pct) in enumerate(st["langs"]):
        y = 140 + i * 31
        col = LANG_COLORS[i % len(LANG_COLORS)]
        w = max(4, bw * pct / 100)
        s += (
            f'<g class="l" style="animation-delay:{0.3+0.1*i:.2f}s">'
            f'<text x="420" y="{y}" font-family="{FONT}" font-size="14" fill="{FG}">{escape(name)}</text>'
            f'<rect x="{bx}" y="{y-11}" width="{bw}" height="12" rx="6" fill="{PANEL2}"/>'
            f'<rect class="bar" style="animation-delay:{0.5+0.1*i:.2f}s" x="{bx}" y="{y-11}" width="{w:.1f}" height="12" rx="6" fill="{col}"/>'
            f'<text x="{W-32}" y="{y}" text-anchor="end" font-family="{FONT}" font-size="13" fill="{COMMENT}">{pct:.1f}%</text></g>\n'
        )
    s += f'<text x="32" y="{H-22}" font-family="{FONT}" font-size="11.5" fill="{COMMENT}" font-style="italic"># updated {today} · refreshed daily by GitHub Actions</text>\n'
    s += (
        f'<rect width="{W}" height="{H}" fill="url(#scan)" pointer-events="none"/>'
        f'<rect width="{W}" height="{H}" fill="url(#vig)" pointer-events="none"/></g>\n'
        f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="14" fill="none" stroke="{BORDER}"/>\n</svg>\n'
    )
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("user")
    ap.add_argument("out", nargs="?", default="assets/stats.svg")
    ap.add_argument("--mock", action="store_true", help="use fake numbers (design preview only)")
    a = ap.parse_args()
    if a.mock:
        st = mock()
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            sys.exit("Set GITHUB_TOKEN (CI provides it; locally try: GITHUB_TOKEN=$(gh auth token))")
        st = summarise(fetch(a.user, token))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(a.user, st), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
