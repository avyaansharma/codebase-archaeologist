import re
from typing import List, Set, Tuple

ISSUE_REF = re.compile(r'#(\d+)')
CLOSES_REF = re.compile(
    r'\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)', re.IGNORECASE
)
# Match github.com/owner/repo/issues/123 or pull/123
FULL_URL_REF = re.compile(r'github\.com/[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+/(?:issues|pull)/(\d+)')
SHA_REF = re.compile(r'\b([a-fA-F0-9]{7,40})\b')

def extract_refs(text: str) -> dict:
    """Returns {'closes': [ids], 'mentions': [ids]} — distinguish strong (closes) vs weak (mentions) links."""
    if not text:
        return {"closes": [], "mentions": [], "shas": []}
    closes = {int(n) for n in CLOSES_REF.findall(text)}
    all_refs = {int(n) for n in ISSUE_REF.findall(text)} | {int(n) for n in FULL_URL_REF.findall(text)}
    mentions = all_refs - closes
    shas = {s.lower() for s in SHA_REF.findall(text) if len(s) >= 7}
    
    return {
        "closes": sorted(list(closes)),
        "mentions": sorted(list(mentions)),
        "shas": sorted(list(shas))
    }

def update_cross_links(pr_list: List[dict], issue_list: List[dict]) -> Tuple[List[dict], List[dict]]:
    """Resolves cross-links bidirectionally between fetched PRs and Issues."""
    pr_map = {pr["number"]: pr for pr in pr_list}
    issue_map = {issue["number"]: issue for issue in issue_list}

    # Initialize links
    for pr in pr_list:
        if "linked_issue_numbers" not in pr:
            pr["linked_issue_numbers"] = []
    for issue in issue_list:
        if "linked_pr_numbers" not in issue:
            issue["linked_pr_numbers"] = []

    # Resolve links from PRs to Issues
    for pr in pr_list:
        # Check title and body
        refs = extract_refs(pr.get("title", "") + " " + (pr.get("body", "") or ""))
        all_issue_refs = set(refs["closes"] + refs["mentions"])
        
        # Check review comments
        for comment in pr.get("review_comments", []):
            comment_refs = extract_refs(comment.get("body", ""))
            all_issue_refs.update(comment_refs["closes"] + comment_refs["mentions"])

        for issue_num in all_issue_refs:
            if issue_num in issue_map:
                if issue_num not in pr["linked_issue_numbers"]:
                    pr["linked_issue_numbers"].append(issue_num)
                if pr["number"] not in issue_map[issue_num]["linked_pr_numbers"]:
                    issue_map[issue_num]["linked_pr_numbers"].append(pr["number"])

    # Resolve links from Issues to PRs
    for issue in issue_list:
        refs = extract_refs(issue.get("title", "") + " " + (issue.get("body", "") or ""))
        
        # Check comments
        for comment in issue.get("comments", []):
            comment_refs = extract_refs(comment.get("body", ""))
            refs["mentions"].extend(comment_refs["closes"] + comment_refs["mentions"])
            
        all_pr_refs = set(refs["closes"] + refs["mentions"])
        for pr_num in all_pr_refs:
            if pr_num in pr_map:
                if pr_num not in issue["linked_pr_numbers"]:
                    issue["linked_pr_numbers"].append(pr_num)
                if issue["number"] not in pr_map[pr_num]["linked_issue_numbers"]:
                    pr_map[pr_num]["linked_issue_numbers"].append(issue["number"])

    return pr_list, issue_list
