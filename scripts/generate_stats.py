"""Generate GitHub stats and top-language SVG cards from the live GitHub API."""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from html import escape

USER = os.environ.get("GH_USER", "RaisulAp")
TOKEN = os.environ["GH_TOKEN"]
OUT = sys.argv[1] if len(sys.argv) > 1 else "dist"

BG, BORDER, TITLE, TEXT, MUTED = "#0d1117", "#30363d", "#58a6ff", "#c9d1d9", "#8b949e"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"


def gql(query, variables=None):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "stats-gen"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def fetch():
    base = gql(
        """query($u:String!){user(login:$u){createdAt followers{totalCount}
        pullRequests{totalCount} issues{totalCount}
        repositories(ownerAffiliations:OWNER,isFork:false,privacy:PUBLIC){totalCount}}}""",
        {"u": USER},
    )["user"]

    # contributionsCollection only spans 1 year, so walk every year since signup
    start = int(base["createdAt"][:4])
    commits = reviews = 0
    for y in range(start, datetime.now(timezone.utc).year + 1):
        c = gql(
            """query($u:String!,$f:DateTime!,$t:DateTime!){user(login:$u){
            contributionsCollection(from:$f,to:$t){totalCommitContributions
            restrictedContributionsCount totalPullRequestReviewContributions}}}""",
            {"u": USER, "f": f"{y}-01-01T00:00:00Z", "t": f"{y}-12-31T23:59:59Z"},
        )["user"]["contributionsCollection"]
        commits += c["totalCommitContributions"] + c["restrictedContributionsCount"]
        reviews += c["totalPullRequestReviewContributions"]

    stars, langs, cursor = 0, {}, None
    while True:
        page = gql(
            """query($u:String!,$c:String){user(login:$u){repositories(first:100,after:$c,
            ownerAffiliations:OWNER,isFork:false,privacy:PUBLIC){pageInfo{hasNextPage endCursor}
            nodes{stargazerCount languages(first:10,orderBy:{field:SIZE,direction:DESC}){
            edges{size node{name color}}}}}}}""",
            {"u": USER, "c": cursor},
        )["user"]["repositories"]
        for repo in page["nodes"]:
            stars += repo["stargazerCount"]
            for e in repo["languages"]["edges"]:
                n = e["node"]
                cur = langs.setdefault(n["name"], {"size": 0, "color": n["color"] or "#8b949e"})
                cur["size"] += e["size"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    return {
        "commits": commits, "reviews": reviews, "stars": stars, "langs": langs,
        "prs": base["pullRequests"]["totalCount"], "issues": base["issues"]["totalCount"],
        "repos": base["repositories"]["totalCount"], "followers": base["followers"]["totalCount"],
    }


def card(w, h, title, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{escape(title)}"><rect x=".5" y=".5" width="{w-1}" height="{h-1}" '
        f'rx="6" fill="{BG}" stroke="{BORDER}"/><text x="25" y="35" font-family="{FONT}" '
        f'font-size="18" font-weight="600" fill="{TITLE}">{escape(title)}</text>{body}</svg>'
    )


def stats_svg(d):
    rows = [("Total Commits", d["commits"]), ("Pull Requests", d["prs"]),
            ("Issues", d["issues"]), ("Code Reviews", d["reviews"]),
            ("Stars Earned", d["stars"]), ("Public Repos", d["repos"])]
    body = ""
    for i, (k, v) in enumerate(rows):
        y = 68 + i * 25
        body += (f'<text x="25" y="{y}" font-family="{FONT}" font-size="14" fill="{TEXT}">{k}:</text>'
                 f'<text x="215" y="{y}" font-family="{FONT}" font-size="14" font-weight="700" '
                 f'fill="{TEXT}">{v:,}</text>')
    return card(300, 195, f"{USER}'s GitHub Stats", body)


def langs_svg(d):
    items = sorted(d["langs"].items(), key=lambda kv: -kv[1]["size"])[:7]
    total = sum(v["size"] for _, v in items) or 1
    bar, x = "", 25
    for name, v in items:
        w = 250 * v["size"] / total
        bar += f'<rect x="{x:.2f}" y="52" width="{w:.2f}" height="8" fill="{v["color"]}"/>'
        x += w
    body = (f'<clipPath id="c"><rect x="25" y="52" width="250" height="8" rx="4"/></clipPath>'
            f'<g clip-path="url(#c)">{bar}</g>')
    for i, (name, v) in enumerate(items):
        cx, cy = 25 + (i % 2) * 130, 85 + (i // 2) * 25
        body += (f'<circle cx="{cx+5}" cy="{cy-4}" r="5" fill="{v["color"]}"/>'
                 f'<text x="{cx+16}" y="{cy}" font-family="{FONT}" font-size="12" fill="{TEXT}">'
                 f'{escape(name)} <tspan fill="{MUTED}">{100*v["size"]/total:.1f}%</tspan></text>')
    return card(300, 195, "Top Languages", body)


if __name__ == "__main__":
    data = fetch()
    os.makedirs(OUT, exist_ok=True)
    for name, svg in (("github-stats.svg", stats_svg(data)), ("github-langs.svg", langs_svg(data))):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(svg)
    print({k: v for k, v in data.items() if k != "langs"}, list(data["langs"]))
