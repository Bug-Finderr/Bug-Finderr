#!/usr/bin/env python3
"""Generate the terminal SVG for the GitHub profile README."""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

GITHUB_USER = "bug-finderr"
TOP_LANGS = 5
BAR_WIDTH = 18
# Repos to exclude from language calculations (case-sensitive)
EXCLUDE_REPOS = {
    "bug-finderr",
    "loan-prediction-nn",
    "Spot_Micro",
}
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent


def gh_graphql(query):
    """Call GitHub GraphQL API via gh CLI."""
    result = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={query}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"gh api error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def get_contribution_stats():
    """Fetch full contribution history by querying year-long windows."""
    # First get account creation date
    user_q = '{ user(login: "%s") { createdAt } }' % GITHUB_USER
    created = gh_graphql(user_q)["data"]["user"]["createdAt"]
    start = datetime.fromisoformat(created.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)

    all_weeks = []  # list of (has_contributions, first_day_date)
    total = 0
    cursor = start

    # Query in 1-year windows (API limit)
    while cursor < now:
        window_end = min(cursor.replace(year=cursor.year + 1), now)
        from_str = cursor.strftime("%Y-%m-%dT%H:%M:%SZ")
        to_str = window_end.strftime("%Y-%m-%dT%H:%M:%SZ")

        query = (
            '{ user(login: "%s") { contributionsCollection(from: "%s", to: "%s")'
            " { contributionCalendar { totalContributions weeks {"
            " contributionDays { contributionCount date } } } } } }"
            % (GITHUB_USER, from_str, to_str)
        )
        data = gh_graphql(query)
        cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        total += cal["totalContributions"]

        for w in cal["weeks"]:
            week_total = sum(d["contributionCount"] for d in w["contributionDays"])
            first_day = w["contributionDays"][0]["date"]
            all_weeks.append((week_total > 0, first_day))

        cursor = window_end

    # current streak (weeks from end)
    current = 0
    for active, _ in reversed(all_weeks):
        if active:
            current += 1
        else:
            break
    current_start = all_weeks[-current][1] if current > 0 else None

    # longest streak with date tracking
    longest = run = 0
    longest_start_idx = 0
    run_start_idx = 0
    for i, (active, _) in enumerate(all_weeks):
        if active:
            if run == 0:
                run_start_idx = i
            run += 1
            if run > longest:
                longest = run
                longest_start_idx = run_start_idx
        else:
            run = 0
    longest_start = all_weeks[longest_start_idx][1] if longest > 0 else None
    longest_end = all_weeks[longest_start_idx + longest - 1][1] if longest > 0 else None

    since = start.strftime("%b %Y")

    return {
        "total": total,
        "since": since,
        "current_streak": current,
        "current_start": _fmt_date(current_start) if current_start else "",
        "longest_streak": longest,
        "longest_start": _fmt_date(longest_start) if longest_start else "",
        "longest_end": _fmt_date(longest_end) if longest_end else "",
    }


def _fmt_date(date_str):
    """Format 'YYYY-MM-DD' to 'Mon YYYY'."""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return d.strftime("%b %Y")


def get_language_stats():
    """Aggregate language bytes across owned repos."""
    query = (
        '{ user(login: "%s") { repositories(first: 100, ownerAffiliations: OWNER,'
        " isFork: false) { nodes { name languages(first: 10,"
        " orderBy: {field: SIZE, direction: DESC}) { edges { size node { name"
        " color } } } } } } }" % GITHUB_USER
    )
    data = gh_graphql(query)
    repos = data["data"]["user"]["repositories"]["nodes"]

    # Only exclude non-programming artifacts that inflate byte counts
    exclude = {"Jupyter Notebook"}
    lang_bytes = {}
    lang_colors = {}
    for repo in repos:
        if repo["name"] in EXCLUDE_REPOS:
            continue
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name in exclude:
                continue
            lang_bytes[name] = lang_bytes.get(name, 0) + edge["size"]
            if edge["node"].get("color"):
                lang_colors[name] = edge["node"]["color"]

    total = sum(lang_bytes.values())
    if total == 0:
        return []

    sorted_langs = sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True)
    top = sorted_langs[:TOP_LANGS]

    return [(name, (size / total) * 100, lang_colors.get(name, "#8b949e")) for name, size in top]


def make_bar(pct):
    """Unicode progress bar."""
    filled = round(pct / 100 * BAR_WIDTH)
    return "\u2588" * filled + "\u2591" * (BAR_WIDTH - filled)


def build_lang_lines(languages):
    """Build HTML for language bars."""
    lines = []
    for name, pct, color in languages:
        padded = name[:12].ljust(12)
        bar = make_bar(pct)
        lines.append(
            f'            <div class="lang-line">'
            f'<span style="color:{color}">\u25cf</span> '
            f'<span class="hl">{padded}</span> '
            f'<span class="bar">{bar}</span> '
            f'<span class="muted">{pct:5.1f}%</span>'
            f"</div>"
        )
    return "\n".join(lines)


def generate_svg(stats, languages, cat_b64):
    """Assemble the terminal SVG."""
    lang_html = build_lang_lines(languages)
    total = stats["total"]
    since = stats["since"]
    current_streak = stats["current_streak"]
    current_start = stats["current_start"]
    longest_streak = stats["longest_streak"]
    longest_start = stats["longest_start"]
    longest_end = stats["longest_end"]

    return f'''<svg fill="none" viewBox="0 0 800 840" width="800" height="840" xmlns="http://www.w3.org/2000/svg">
  <foreignObject width="100%" height="100%">
    <div xmlns="http://www.w3.org/1999/xhtml">
      <style>
        @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
        @keyframes blink {{ 50% {{ opacity: 0; }} }}
        @keyframes scanline {{ 0% {{ top: -10px; }} 100% {{ top: 100%; }} }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        .term {{
          width: 100%; height: 840px; background: #0d1117;
          font-family: 'SFMono-Regular','SF Mono',Menlo,Consolas,'Liberation Mono',monospace;
          font-size: 13px; color: #8b949e;
          border: 1px solid #30363d; border-radius: 8px;
          position: relative; overflow: hidden; line-height: 1.7;
        }}
        .term::before {{
          content: ''; position: absolute; top: -10px; left: 0;
          width: 100%; height: 1px;
          background: linear-gradient(90deg, transparent, rgba(88,166,255,0.06), transparent);
          animation: scanline 10s linear infinite; pointer-events: none; z-index: 10;
        }}
        .chrome {{
          display: flex; align-items: center; padding: 10px 16px;
          border-bottom: 1px solid #30363d; background: #161b22;
        }}
        .dots {{ display: flex; gap: 6px; }}
        .dot {{ width: 10px; height: 10px; border-radius: 50%; }}
        .dot.r {{ background: #ff5f57; }}
        .dot.y {{ background: #febc2e; }}
        .dot.g {{ background: #28c840; }}
        .title {{ flex:1; text-align:center; color:#484f58; font-size:12px; margin-right:48px; }}
        .body {{ padding: 18px 24px; }}
        .top {{ display: flex; gap: 20px; align-items: flex-start; }}
        .boot {{ flex: 1; }}
        .cat {{
          width: 170px; height: 170px; border-radius: 6px;
          border: 1px solid #30363d; flex-shrink: 0;
          opacity: 0; animation: fadeIn 0.5s forwards 3.2s;
        }}
        .line {{ opacity: 0; animation: fadeIn 0.3s forwards; }}
        .l1 {{ animation-delay: 0.4s; }} .l2 {{ animation-delay: 0.9s; }}
        .l3 {{ animation-delay: 1.3s; }} .l4 {{ animation-delay: 1.7s; }}
        .l5 {{ animation-delay: 2.1s; }} .l6 {{ animation-delay: 2.5s; }}
        .l7 {{ animation-delay: 2.9s; }}
        .dim {{ color: #484f58; }}
        .blue {{ color: #58a6ff; }}
        .green {{ color: #3fb950; }}
        .orange {{ color: #d29922; }}
        .cyan {{ color: #39c5cf; }}
        .sep {{
          border: none; border-top: 1px solid #21262d;
          margin: 12px 0; opacity: 0; animation: fadeIn 0.3s forwards;
        }}
        .s1 {{ animation-delay: 3.4s; }} .s2 {{ animation-delay: 4.1s; }}
        .s3 {{ animation-delay: 4.6s; }} .s4 {{ animation-delay: 5.0s; }}
        .s5 {{ animation-delay: 5.8s; }}
        .section {{ opacity: 0; animation: fadeIn 0.4s forwards; }}
        .sa {{ animation-delay: 3.6s; }} .ss {{ animation-delay: 4.3s; }}
        .sst {{ animation-delay: 4.8s; }} .sl {{ animation-delay: 5.2s; }}
        .section-head {{
          color: #484f58; font-size: 11px;
          letter-spacing: 2px; text-transform: uppercase; margin-bottom: 6px;
        }}
        .about-text {{ color: #c9d1d9; line-height: 1.7; }}
        .stack-list {{ color: #6e7681; line-height: 1.9; }}
        .stack-list .hl {{ color: #8b949e; }}
        .stat-line {{ color: #c9d1d9; }}
        .stat-line .num {{ color: #58a6ff; font-weight: 600; }}
        .stat-line .lbl {{ color: #6e7681; }}
        .lang-line {{ line-height: 1.9; font-size: 12.5px; }}
        .lang-line .hl {{ color: #c9d1d9; }}
        .lang-line .bar {{ color: #3fb950; letter-spacing: -1px; font-size: 11px; }}
        .lang-line .muted {{ color: #6e7681; font-size: 11.5px; }}
        .prompt {{
          opacity: 0; animation: fadeIn 0.3s forwards; animation-delay: 6.0s;
        }}
        .cursor {{
          display: inline-block; width: 7px; height: 13px;
          background: #58a6ff; vertical-align: text-bottom; margin-left: 2px;
          opacity: 0; animation: fadeIn 0.1s forwards 6.4s, blink 1s step-end infinite 6.4s;
        }}
        @media (prefers-color-scheme: light) {{
          .term {{ background: #fff; border-color: #d0d7de; }}
          .chrome {{ background: #f6f8fa; border-color: #d0d7de; }}
          .title {{ color: #656d76; }}
          .dim {{ color: #afb8c1; }} .blue {{ color: #0969da; }}
          .green {{ color: #1a7f37; }} .orange {{ color: #9a6700; }}
          .cyan {{ color: #0550ae; }}
          .about-text {{ color: #1f2328; }} .stat-line {{ color: #1f2328; }}
          .stat-line .num {{ color: #0969da; }}
          .stack-list {{ color: #656d76; }} .stack-list .hl {{ color: #1f2328; }}
          .lang-line .hl {{ color: #1f2328; }} .lang-line .bar {{ color: #1a7f37; }}
          .cursor {{ background: #0969da; }}
          .sep {{ border-color: #d0d7de; }} .section-head {{ color: #656d76; }}
          .cat {{ border-color: #d0d7de; }}
        }}
      </style>
      <div class="term">
        <div class="chrome">
          <div class="dots">
            <div class="dot r"></div><div class="dot y"></div><div class="dot g"></div>
          </div>
          <div class="title">bug-finderr &#8212; zsh &#8212; 80&#215;24</div>
        </div>
        <div class="body">
          <div class="top">
            <div class="boot">
              <div class="line l1"><span class="dim">[boot]</span> initializing system...</div>
              <div class="line l2"><span class="dim">[core]</span> <span class="blue">bug-finderr</span> v3.0 loaded</div>
              <div class="line l3"><span class="dim">[  </span><span class="green">OK</span><span class="dim">  ]</span> caffeine levels: optimal</div>
              <div class="line l4"><span class="dim">[  </span><span class="green">OK</span><span class="dim">  ]</span> web protocols: active</div>
              <div class="line l5"><span class="dim">[info]</span> scanning for bugs...</div>
              <div class="line l6"><span class="dim">[</span><span class="orange">warn</span><span class="dim">]</span> it&#8217;s late. the world is quiet.</div>
              <div class="line l7"><span class="dim">[</span><span class="cyan">ready</span><span class="dim">]</span> system operational</div>
            </div>
            <img class="cat" src="data:image/gif;base64,{cat_b64}" alt="cat" />
          </div>

          <hr class="sep s1" />
          <div class="section sa">
            <div class="section-head"><span class="dim">&#9472;&#9472;</span> about <span class="dim">&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;</span></div>
            <div class="about-text">I&#8217;m an engineer who likes talking about the web &#8212; everything<br/>from web apps to browsers &amp; the tech that powers them.<br/><br/>My best ideas usually come late at night when the world is quiet.</div>
          </div>

          <hr class="sep s2" />
          <div class="section ss">
            <div class="section-head"><span class="dim">&#9472;&#9472;</span> stack <span class="dim">&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;</span></div>
            <div class="stack-list"><span class="hl">ts</span> &#183; <span class="hl">react</span> &#183; <span class="hl">next.js</span> &#183; <span class="hl">react-native</span> &#183; <span class="hl">tailwind</span> &#183; <span class="hl">node</span> &#183; <span class="hl">bun</span><br/><span class="hl">go</span> &#183; <span class="hl">python</span> &#183; <span class="hl">fastapi</span> &#183; <span class="hl">java</span> &#183; <span class="hl">c++</span><br/><span class="hl">postgres</span> &#183; <span class="hl">mongo</span> &#183; <span class="hl">redis</span> &#183; <span class="hl">docker</span> &#183; <span class="hl">bash</span></div>
          </div>

          <hr class="sep s3" />
          <div class="section sst">
            <div class="section-head"><span class="dim">&#9472;&#9472;</span> stats <span class="dim">&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;</span></div>
            <div class="stat-line"><span class="num">{total}</span> <span class="lbl">total contributions</span> <span class="dim">&#183; since {since}</span></div>
            <div class="stat-line"><span class="num">{current_streak}</span> <span class="lbl">week streak</span> <span class="dim">&#183; {current_start} &#8212; present</span></div>
            <div class="stat-line"><span class="num">{longest_streak}</span> <span class="lbl">longest streak</span> <span class="dim">&#183; {longest_start} &#8212; {longest_end}</span></div>
          </div>

          <hr class="sep s4" />
          <div class="section sl">
            <div class="section-head"><span class="dim">&#9472;&#9472;</span> languages <span class="dim">&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;</span></div>
{lang_html}
          </div>

          <hr class="sep s5" />
          <div class="prompt">
            <span class="green">bug@finderr</span><span class="dim">:</span><span class="blue">~</span><span class="dim">$</span> <span class="cursor"></span>
          </div>
        </div>
      </div>
    </div>
  </foreignObject>
</svg>'''


def main():
    print("fetching contribution stats...", file=sys.stderr)
    stats = get_contribution_stats()
    print(
        f"  {stats['total']} contributions since {stats['since']}, "
        f"{stats['current_streak']}w streak from {stats['current_start']}, "
        f"{stats['longest_streak']}w longest ({stats['longest_start']} - {stats['longest_end']})",
        file=sys.stderr,
    )

    print("fetching language stats...", file=sys.stderr)
    languages = get_language_stats()
    for name, pct, color in languages:
        print(f"  {name}: {pct:.1f}%", file=sys.stderr)

    print("reading cat gif...", file=sys.stderr)
    cat_b64 = (SCRIPT_DIR / "cat.b64").read_text().strip()

    print("generating svg...", file=sys.stderr)
    svg = generate_svg(stats, languages, cat_b64)

    out_dir = REPO_ROOT / "assets"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "header.svg"
    out_path.write_text(svg)
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
