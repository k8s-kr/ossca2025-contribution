#!/usr/bin/env python3
"""GraphQL-accelerated fetcher for GitHub contributions in an organization.

This script uses the GitHub GraphQL API to obtain per-user contribution summary
from the `contributionsCollection` scoped to the organization. It also uses the
REST search endpoint to obtain an approximate "commented items" count (number
of distinct issues/PRs the user commented on in the org) which is efficient.

Output is JSON suitable for Hugo: `data/contributions.json`.

Notes:
- This implementation avoids per-repo comment enumeration for performance.
- If you need exact raw comment counts, enable the heavier collection mode.
"""

import argparse
import dotenv
import json
import os
import sys
import time
from typing import List

import requests

GITHUB_REST = "https://api.github.com"
GITHUB_GRAPHQL = "https://api.github.com/graphql"
REPO = "kubernetes/website"

USERS = [
    "hyorimlee",
    "jongwooo",
    "NOHHYEONGJUN",
    "developowl",
    "eundms",
    "wonyongg",
    "wooneojun",
    "ianychoi",
    "kamothi",
    "S0okJu",
    "daeun-ops",
    "Antraxmin",
    "ppiyakk2",
]

# runtime verbose flag (set from CLI)
VERBOSE = False


def vprint(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)


def redact_headers(hdrs: dict):
    """Return a copy of headers with Authorization redacted for safe logging."""
    if not hdrs:
        return hdrs
    out = dict(hdrs)
    if "Authorization" in out:
        out["Authorization"] = "REDACTED"
    return out


def graphql_query(query: str, variables=None):
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        token = token.strip()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ossca-dashboard/1.0"}
    if token:
        # use standard Bearer scheme
        headers["Authorization"] = f"Bearer {token}"
    # log query (redact authorization)
    vprint("GRAPHQL ->", GITHUB_GRAPHQL)
    vprint("GRAPHQL headers:", redact_headers(headers))
    vprint("GRAPHQL variables:", variables or {})
    resp = requests.post(GITHUB_GRAPHQL, json={"query": query, "variables": variables or {}}, headers=headers)
    if resp.status_code != 200:
        print("GraphQL query failed:", resp.status_code, resp.text, file=sys.stderr)
        resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        # surface first error
        print("GraphQL errors:", data["errors"], file=sys.stderr)
        # do not raise to allow graceful degradation
    return data.get("data", {})


def get_org_node_id(org_login: str):
    """Return GraphQL node ID for an organization given its login."""
    if not org_login:
        return None
    q = "query($login: String!){ organization(login: $login) { id } }"
    data = graphql_query(q, variables={"login": org_login})
    org = data.get("organization")
    if not org:
        return None
    return org.get("id")


def gh_get(url: str, params=None):
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        token = token.strip()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ossca-dashboard/1.0"}
    if token:
        # use standard Bearer scheme for consistency with GraphQL calls
        headers["Authorization"] = f"Bearer {token}"

    # retries with exponential backoff for transient errors
    attempts = 3
    backoff = 1.0
    timeout = 10  # seconds
    for attempt in range(1, attempts + 1):
        try:
            vprint(f"REST GET -> {url} params={params}")
            vprint("REST headers:", redact_headers(headers))
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        except requests.exceptions.RequestException as e:
            print(f"Request error (attempt {attempt}) for {url}: {e}", file=sys.stderr)
            if attempt == attempts:
                raise
            time.sleep(backoff)
            backoff *= 2
            continue

        # retry on 5xx server errors
        if 500 <= resp.status_code < 600:
            print(f"Server error {resp.status_code} on {url} (attempt {attempt})", file=sys.stderr)
            if attempt == attempts:
                resp.raise_for_status()
            time.sleep(backoff)
            backoff *= 2
            continue

        if resp.status_code >= 400:
            # client errors: surface immediately
            print(f"REST GET {url} failed: {resp.status_code} {resp.text}", file=sys.stderr)
            resp.raise_for_status()

        return resp


def paginate(url: str, params=None):
    """Paginate a REST endpoint that returns a list."""
    page = 1
    per_page = 100
    items = []
    while True:
        p = dict(params or {})
        p.update({"per_page": per_page, "page": page})
        try:
            resp = gh_get(url, params=p)
            data = resp.json()
        except Exception as e:
            print(f"Warning: paginate failed for {url} page={page}: {e}", file=sys.stderr)
            # attempt to skip this page after warning
            break
        vprint(f"paginate {url} page={page} got {len(data) if isinstance(data, list) else 'non-list'} items")
        if not isinstance(data, list):
            break
        items.extend(data)
        if len(data) < per_page:
            break
        page += 1
        time.sleep(0.1)
    return items


def rest_search_paginate(q: str):
    """Paginate the REST search/issues endpoint for a given query string."""
    items = []
    page = 1
    per_page = 100
    while True:
        vprint(f"search/issues q={q} page={page}")
        resp = gh_get(f"{GITHUB_REST}/search/issues", params={"q": q, "per_page": per_page, "page": page})
        data = resp.json()
        batch = data.get("items", [])
        items.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
        time.sleep(0.1)
    return items


def rest_search_count(q: str) -> int:
    """Return total_count for a search query via REST search/issues."""
    vprint(f"search/count q={q}")
    resp = gh_get(f"{GITHUB_REST}/search/issues", params={"q": q, "per_page": 1})
    data = resp.json()
    return data.get("total_count", 0)


# NOTE: REST search for commenter: produced 422 in some environments; to keep the
# script reliable we omit that and rely on GraphQL contributionsCollection totals.


def fetch_users_contributions(users: List[str], org_id: str = None):
    # Build a single GraphQL query with aliases for each user to minimize roundtrips
    parts = []
    for i, u in enumerate(users):
        alias = f"u{i}"
        if org_id:
            coll_arg = f'contributionsCollection(organizationID: "{org_id}")'
        else:
            coll_arg = "contributionsCollection()"
        part = (
            f'{alias}: user(login: "{u}") {{ login {coll_arg} '
            "{ totalIssueContributions totalPullRequestContributions totalPullRequestReviewContributions } }"
        )
        parts.append(part)
    query = "query { " + " ".join(parts) + " }"
    data = graphql_query(query)
    results = {}
    for i, u in enumerate(users):
        key = f"u{i}"
        node = data.get(key)
        if not node:
            results[u] = {"error": "no data"}
            continue
        coll = node.get("contributionsCollection") or {}
        results[u] = {
            "user": node.get("login", u),
            "issues_created": coll.get("totalIssueContributions", 0),
            "prs_created": coll.get("totalPullRequestContributions", 0),
            "pr_review_contributions": coll.get("totalPullRequestReviewContributions", 0),
        }
    return results


def fetch_repos_list_rest():
    """Return list of repo full_names for the org via REST (public repos)."""
    # expect ORG to be passed via environment or args; fallback to env GITHUB_ORG
    org = os.environ.get("GITHUB_ORG")
    if not org:
        raise RuntimeError("Organization not set: provide --org or set GITHUB_ORG in environment")
    repos = paginate(f"{GITHUB_REST}/orgs/{org}/repos", params={"type": "public"})
    return [r.get("full_name") for r in repos if r.get("full_name")]


def detailed_count_comments_for_user(username: str, repo_full_names: List[str]):
    """Exact counts by enumerating issue comments and PR review comments per repo.

    This is the heavier, more accurate mode. It may consume many API requests.
    """
    issue_comments = 0
    review_comments = 0
    # If repo list is small, use search counts per repo which is much faster
    if len(repo_full_names) <= 5:
        for repo_full in repo_full_names:
            # issue comments count
            try:
                repo_parts = repo_full.split('/')
                if len(repo_parts) == 2:
                    owner, repo = repo_parts
                    q_ic = f"repo:{owner}/{repo} commenter:{username}"
                    ic = rest_search_count(q_ic)
                    issue_comments += ic
                else:
                    # fallback to pagination
                    comments = paginate(f"{GITHUB_REST}/repos/{repo_full}/issues/comments")
                    for c in comments:
                        if c.get("user", {}).get("login") == username:
                            issue_comments += 1
            except Exception as e:
                print(f"Warning: failed to fetch issue comments for {repo_full}: {e}", file=sys.stderr)
            # PR review comments count - search doesn't separate review comments, but search/issues includes PR review comments as "comments" on PRs for commenter searches.
            try:
                # use repo_full directly to avoid owner/repo scope issues
                q_rc = f"repo:{repo_full} commenter:{username} is:pr"
                rc = rest_search_count(q_rc)
                # rc counts PRs with a comment by the user, not review comment count; use as approximation
                review_comments += rc
            except Exception as e:
                print(f"Warning: failed to fetch PR review comments for {repo_full}: {e}", file=sys.stderr)
    else:
        for repo_full in repo_full_names:
            # issue comments
            try:
                comments = paginate(f"{GITHUB_REST}/repos/{repo_full}/issues/comments")
                for c in comments:
                    if c.get("user", {}).get("login") == username:
                        issue_comments += 1
            except Exception as e:
                print(f"Warning: failed to fetch issue comments for {repo_full}: {e}", file=sys.stderr)
            # PR review comments
            try:
                rev_comments = paginate(f"{GITHUB_REST}/repos/{repo_full}/pulls/comments")
                for c in rev_comments:
                    if c.get("user", {}).get("login") == username:
                        review_comments += 1
            except Exception as e:
                print(f"Warning: failed to fetch PR review comments for {repo_full}: {e}", file=sys.stderr)
    return issue_comments, review_comments


def detailed_aggregate_comments(repo_full_names: List[str], users: List[str], since: str = None, until: str = None):
    """Aggregate comment counts per user using search queries limited to a date range.

    Fast path: for each repo and each user, use the search API to count items the
    user commented on within the date range. This avoids paginating all comments.

    This returns a dict: { username: { 'issue_comments': int, 'review_comments': int } }
    Note: search-based counts count items (issues/PRs) where the user commented,
    not exact raw comment counts; it's much faster for time-bounded queries.
    """
    counts = {u: {'issue_comments': 0, 'review_comments': 0} for u in users}
    # Build date qualifier if provided
    date_qual = ""
    if since and until:
        # GitHub search supports range like 'updated:YYYY-MM-DD..YYYY-MM-DD'
        date_qual = f" updated:{since}..{until}"

    for repo_full in repo_full_names:
        for u in users:
            try:
                # count commented issue items in date range
                q_issue = f"repo:{repo_full} commenter:{u} is:issue{date_qual}"
                ic = rest_search_count(q_issue)
                # count commented PR items in date range (approx for review comments)
                q_pr = f"repo:{repo_full} commenter:{u} is:pr{date_qual}"
                prc = rest_search_count(q_pr)
                counts[u]['issue_comments'] += ic
                counts[u]['review_comments'] += prc
                # be polite to search rate limits
                time.sleep(0.05)
            except Exception as e:
                print(f"Warning: failed search count for {repo_full} user {u}: {e}", file=sys.stderr)
    return counts


def main():

    dotenv.load_dotenv()  # load .env if present

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="Output JSON file path")
    parser.add_argument("--detailed", action="store_true", help="Run detailed per-repo comment enumeration (slow)")
    parser.add_argument("--org", help="Organization login (e.g. kubernetes)")
    parser.add_argument("--repo", help="Repository full name (owner/repo) to limit created items search", default=REPO)
    parser.add_argument("--repos", help="Comma-separated list of repos to limit detailed mode (owner/repo,...)")
    parser.add_argument("-v", "--verbose", help="Enable verbose logging", action="store_true")
    parser.add_argument("--since", dest="since", help="Start date YYYY-MM-DD for comment aggregation", default="2025-08-31")
    parser.add_argument("--until", dest="until", help="End date YYYY-MM-DD for comment aggregation", default="2025-09-06")
    args = parser.parse_args()

    # set global verbose flag
    global VERBOSE
    VERBOSE = bool(args.verbose)

    # determine org and repo context
    ORG = args.org or os.environ.get("GITHUB_ORG")
    repo_arg = args.repo or REPO

    # fetch org node id for GraphQL contributionsCollection
    org_id = None
    if ORG:
        org_id = get_org_node_id(ORG)

    users_data = fetch_users_contributions(USERS, org_id=org_id)

    results = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "org": ORG, "users": []}
    repo_list = None
    if args.detailed:
        if args.repos:
            repo_list = [r.strip() for r in args.repos.split(",") if r.strip()]
            print(f"Detailed mode: limiting to {len(repo_list)} repos from --repos")
        else:
            print("Detailed mode: fetching repo list (this may take a while)...")
            repo_list = fetch_repos_list_rest()
            print(f"Found {len(repo_list)} repos")

    # If detailed, aggregate comments by scanning each repo once
    agg_counts = None
    if args.detailed and repo_list is not None:
        print(f"Aggregating comments across repos (one pass) for {args.since}..{args.until}")
        agg_counts = detailed_aggregate_comments(repo_list, USERS, since=args.since, until=args.until)

    for u in USERS:
        print("Collecting for", u)
        entry = users_data.get(u, {"user": u, "error": "missing"})
        # will be populated later from repo aggregation
        entry["commented_items"] = 0

        # fetch lists of issues and prs created by the user in the REPO (REST search)
        try:
            issues = rest_search_paginate(f"type:issue repo:{repo_arg} author:{u}")
            print("  found created issues:", len(issues))
            prs = rest_search_paginate(f"type:pr repo:{repo_arg} author:{u}")
            print("  found created prs:", len(prs))
        except Exception as e:
            print(f"Warning: search failed for created items for {u}: {e}", file=sys.stderr)
            issues = []
            prs = []

        def normalize_item(it):
            return {
                "title": it.get("title"),
                "html_url": it.get("html_url"),
                "repository_url": it.get("repository_url"),
            }

        entry["created_issues"] = [normalize_item(i) for i in issues]
        entry["created_prs"] = [normalize_item(p) for p in prs]

        # Build user -> repo aggregation (fast path)
        def api_url_to_fullname(api_url: str):
            # api_url like https://api.github.com/repos/owner/repo
            if not api_url:
                return None
            parts = api_url.rstrip('/').split('/')
            if len(parts) >= 2:
                owner = parts[-2]
                repo = parts[-1]
                return f"{owner}/{repo}"
            return None

        repos = {}
        for it in entry["created_issues"]:
            repo_full = api_url_to_fullname(it.get("repository_url"))
            if not repo_full:
                continue
            r = repos.setdefault(repo_full, {"issues_created": 0, "prs_created": 0, "commented_items": 0, "items": []})
            r["issues_created"] += 1
            r["items"].append({"type": "issue", "title": it.get("title"), "url": it.get("html_url")})
        for it in entry["created_prs"]:
            repo_full = api_url_to_fullname(it.get("repository_url"))
            if not repo_full:
                continue
            r = repos.setdefault(repo_full, {"issues_created": 0, "prs_created": 0, "commented_items": 0, "items": []})
            r["prs_created"] += 1
            r["items"].append({"type": "pr", "title": it.get("title"), "url": it.get("html_url")})

        # fast commenter aggregation: list items where user commented (not exact comment count)
        try:
            commented = rest_search_paginate(f"repo:{repo_arg} commenter:{u}")
            for it in commented:
                repo_full = api_url_to_fullname(it.get("repository_url"))
                if not repo_full:
                    continue
                r = repos.setdefault(repo_full, {"issues_created": 0, "prs_created": 0, "commented_items": 0, "items": []})
                r["commented_items"] += 1
                r["items"].append({"type": "commented_item", "title": it.get("title"), "url": it.get("html_url")})
        except Exception:
            # search commenter may fail in some environments; ignore for fast path
            pass

        entry["repos"] = repos

        # compute totals from repos aggregation
        try:
            entry["commented_items"] = sum(r.get("commented_items", 0) for r in repos.values())
            entry["total_created_issues"] = sum(r.get("issues_created", 0) for r in repos.values())
            entry["total_created_prs"] = sum(r.get("prs_created", 0) for r in repos.values())
        except Exception:
            entry["commented_items"] = entry.get("commented_items", 0)

        if agg_counts is not None:
            c = agg_counts.get(u, {"issue_comments": 0, "review_comments": 0})
            entry["issue_comments"] = c.get("issue_comments", 0)
            entry["review_comments"] = c.get("review_comments", 0)
            entry["total_comments"] = entry["issue_comments"] + entry["review_comments"]
        else:
            pr_reviews = entry.get("pr_review_contributions", 0) or 0
            entry["total_comments_approx"] = pr_reviews

        results["users"].append(entry)
        time.sleep(0.1)

    out_path = args.out
    dirpath = os.path.dirname(out_path) or '.'
    try:
        os.makedirs(dirpath, exist_ok=True)
    except Exception as e:
        print(f"Warning: could not create directory {dirpath}: {e}", file=sys.stderr)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Wrote", out_path)


if __name__ == "__main__":
    main()
