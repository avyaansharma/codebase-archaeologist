import re
from typing import List, Set, Tuple

ISSUE_REF = re.compile(r'#(\d+)')
CLOSES_REF = re.compile(
    r'\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)', re.IGNORECASE
)
# Match github.com/owner/repo/issues/123 or pull/123
FULL_URL_REF = re.compile(r'github\.com/[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+/(?:issues|pull)/(\d+)')

# Require at least one non-decimal hex character (a-fA-F) (§7 Fix)
SHA_REF = re.compile(r'\b(?=[a-fA-F0-9]{7,40}\b)(?=\w*[a-fA-F])[a-fA-F0-9]{7,40}\b')

def extract_refs(text: str) -> dict:
    """Returns {'closes': [ids], 'mentions': [ids], 'shas': [shas]}."""
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
    """Updates linked_issue_numbers on PRs and linked_pr_numbers on issues in-place, plus linked_commit_shas."""
    issue_map = {i["number"]: i for i in issue_list}
    pr_map = {p["number"]: p for p in pr_list}

    for p in pr_list:
        if "linked_issue_numbers" not in p:
            p["linked_issue_numbers"] = []
        if "linked_commit_shas" not in p:
            p["linked_commit_shas"] = []

        all_text = f"{p.get('title', '')} {p.get('body', '')} "
        comments_list = p.get("review_comments", []) + p.get("comments", [])
        for c in comments_list:
            all_text += f"{c.get('body', '')} "

        refs = extract_refs(all_text)
        all_issues = set(p["linked_issue_numbers"]) | set(refs["closes"]) | set(refs["mentions"])
        p["linked_issue_numbers"] = sorted(list(all_issues))
        p["linked_commit_shas"] = sorted(list(set(p["linked_commit_shas"]) | set(refs["shas"])))

        # Update back-references on issues
        for issue_num in p["linked_issue_numbers"]:
            if issue_num in issue_map:
                target_issue = issue_map[issue_num]
                if "linked_pr_numbers" not in target_issue:
                    target_issue["linked_pr_numbers"] = []
                if p["number"] not in target_issue["linked_pr_numbers"]:
                    target_issue["linked_pr_numbers"].append(p["number"])
                    target_issue["linked_pr_numbers"].sort()

    for i in issue_list:
        if "linked_pr_numbers" not in i:
            i["linked_pr_numbers"] = []
        if "linked_commit_shas" not in i:
            i["linked_commit_shas"] = []

        all_text = f"{i.get('title', '')} {i.get('body', '')} "
        for c in i.get("comments", []):
            all_text += f"{c.get('body', '')} "

        refs = extract_refs(all_text)
        i["linked_commit_shas"] = sorted(list(set(i["linked_commit_shas"]) | set(refs["shas"])))

        for pr_num in refs["closes"] + refs["mentions"]:
            if pr_num not in i["linked_pr_numbers"]:
                i["linked_pr_numbers"].append(pr_num)
                i["linked_pr_numbers"].sort()

            if pr_num in pr_map:
                target_pr = pr_map[pr_num]
                if "linked_issue_numbers" not in target_pr:
                    target_pr["linked_issue_numbers"] = []
                if i["number"] not in target_pr["linked_issue_numbers"]:
                    target_pr["linked_issue_numbers"].append(i["number"])
                    target_pr["linked_issue_numbers"].sort()

    return pr_list, issue_list
