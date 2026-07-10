"""Refresh the live GitHub statistics embedded in the profile SVGs."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


USERNAME = os.environ.get("PROFILE_USERNAME", "ved015")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
REST_API = "https://api.github.com"
GRAPHQL_API = "https://api.github.com/graphql"


def request_json(url: str, *, payload: dict | None = None) -> dict | list:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"{USERNAME}-profile-readme",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=data, headers=headers)
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def rest(path: str, **params: str | int) -> dict | list:
    query = f"?{urlencode(params)}" if params else ""
    return request_json(f"{REST_API}/{path}{query}")


def search_total(query: str, endpoint: str = "issues") -> int:
    result = rest(f"search/{endpoint}", q=query, per_page=1)
    return int(result["total_count"])


def repository_stats() -> tuple[int, int]:
    page = 1
    repositories: list[dict] = []
    while True:
        batch = rest(
            f"users/{USERNAME}/repos",
            type="owner",
            per_page=100,
            page=page,
        )
        repositories.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return len(repositories), sum(int(repo["stargazers_count"]) for repo in repositories)


def contribution_total(year: int, now: datetime) -> int:
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar { totalContributions }
        }
      }
    }
    """
    result = request_json(
        GRAPHQL_API,
        payload={
            "query": query,
            "variables": {
                "login": USERNAME,
                "from": f"{year}-01-01T00:00:00Z",
                "to": now.isoformat().replace("+00:00", "Z"),
            },
        },
    )
    return int(
        result["data"]["user"]["contributionsCollection"]["contributionCalendar"][
            "totalContributions"
        ]
    )


def github_uptime(created_at: str, now: datetime) -> str:
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    years = now.year - created.year - ((now.month, now.day) < (created.month, created.day))
    return f"{years} year{'s' if years != 1 else ''} on GitHub"


def update_svg(path: Path, values: dict[str, str | int]) -> None:
    content = path.read_text()
    for element_id, value in values.items():
        rendered = f"{value:,}" if isinstance(value, int) else value
        pattern = rf'(<tspan[^>]*id="{re.escape(element_id)}"[^>]*>)(.*?)(</tspan>)'
        content, replacements = re.subn(
            pattern,
            lambda match: f"{match.group(1)}{rendered}{match.group(3)}",
            content,
            count=1,
        )
        if replacements != 1:
            raise ValueError(f"Missing SVG element: {element_id} in {path}")
    path.write_text(content)


def main() -> None:
    now = datetime.now(timezone.utc)
    user = rest(f"users/{USERNAME}")
    repo_count, star_count = repository_stats()
    values: dict[str, str | int] = {
        "uptime_data": github_uptime(str(user["created_at"]), now),
        "repo_data": repo_count,
        "star_data": star_count,
        "follower_data": int(user["followers"]),
        "contributions_year": str(now.year),
        "contributions_data": contribution_total(now.year, now),
        "commit_data": search_total(f"author:{USERNAME}", endpoint="commits"),
        "pr_data": search_total(f"author:{USERNAME} type:pr"),
        "merged_pr_data": search_total(f"author:{USERNAME} type:pr is:merged"),
    }

    for filename in (Path("dark_mode.svg"), Path("light_mode.svg")):
        update_svg(filename, values)

    for key, value in values.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
