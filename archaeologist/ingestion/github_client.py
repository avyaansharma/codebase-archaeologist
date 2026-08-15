import os
import re
from typing import List, Dict, Any, Optional
from github import Github, RateLimitExceededException
from dotenv import load_dotenv

load_dotenv()

class GitHubIngestionClient:
    def __init__(self, repo_url: str, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.gh = Github(self.token) if self.token else Github()
        
        # Parse owner and repo name from URL (e.g. https://github.com/owner/repo)
        match = re.search(r'github\.com/([^/]+)/([^/.]+)', repo_url)
        if not match:
            raise ValueError(f"Invalid GitHub URL: '{repo_url}'")
            
        self.owner = match.group(1)
        self.repo_name = match.group(2)
        try:
            self.repo = self.gh.get_repo(f"{self.owner}/{self.repo_name}")
        except Exception as e:
            print(f"Notice: Could not access GitHub repository metadata for '{self.owner}/{self.repo_name}': {e}")
            self.repo = None

    def fetch_pull_requests(self, state: str = "all", limit: int = 50) -> List[Dict[str, Any]]:
        """Fetches PRs with main metadata, comments, and linked issue numbers."""
        if not self.repo:
            return []

        prs_data = []
        try:
            prs = self.repo.get_pulls(state=state, sort="created", direction="desc")
            count = 0
            for pr in prs:
                if count >= limit:
                    break
                
                # Parse linked issue numbers from body
                body_text = pr.body or ""
                linked_issues = [int(n) for n in re.findall(r'(?:fixes|resolves|closes|refs)\s+#(\d+)', body_text, re.IGNORECASE)]
                
                comments = []
                try:
                    for c in pr.get_issue_comments():
                        comments.append({
                            "user": c.user.login if c.user else "unknown",
                            "body": c.body,
                            "created_at": c.created_at.isoformat()
                        })
                except Exception as e:
                    if "rate limit" in str(e).lower() or "403" in str(e):
                        print(f"Warning: GitHub API rate limit hit while fetching PR comments. Skipping further comment fetch.")
                        break

                prs_data.append({
                    "number": pr.number,
                    "title": pr.title,
                    "body": body_text,
                    "state": pr.state,
                    "author": pr.user.login if pr.user else "unknown",
                    "created_at": pr.created_at,
                    "merged_at": pr.merged_at,
                    "merged_commit_sha": pr.merge_commit_sha,
                    "comments": comments,
                    "linked_issue_numbers": linked_issues,
                })
                count += 1
        except Exception as e:
            print(f"Notice: Skipping remaining PR fetch due to GitHub API limit/error: {e}")

        return prs_data

    def fetch_issues(self, state: str = "all", limit: int = 50) -> List[Dict[str, Any]]:
        """Fetches issues with main metadata, comments, labels, and linked PR numbers."""
        if not self.repo:
            return []

        issues_data = []
        try:
            issues = self.repo.get_issues(state=state, sort="created", direction="desc")
            count = 0
            for issue in issues:
                if count >= limit:
                    break
                if issue.pull_request:  # Skip PRs returned by issue endpoint
                    continue

                body_text = issue.body or ""
                linked_prs = [int(n) for n in re.findall(r'(?:pr|pull request|see)\s+#(\d+)', body_text, re.IGNORECASE)]

                comments = []
                try:
                    for c in issue.get_comments():
                        comments.append({
                            "user": c.user.login if c.user else "unknown",
                            "body": c.body,
                            "created_at": c.created_at.isoformat()
                        })
                except Exception as e:
                    if "rate limit" in str(e).lower() or "403" in str(e):
                        print("Warning: GitHub API rate limit hit while fetching issue comments.")
                        break

                issues_data.append({
                    "number": issue.number,
                    "title": issue.title,
                    "body": body_text,
                    "state": issue.state,
                    "author": issue.user.login if issue.user else "unknown",
                    "created_at": issue.created_at,
                    "closed_at": issue.closed_at,
                    "labels": [l.name for l in issue.labels],
                    "comments": comments,
                    "linked_pr_numbers": linked_prs,
                })
                count += 1
        except Exception as e:
            print(f"Notice: Skipping remaining Issue fetch due to GitHub API limit/error: {e}")

        return issues_data
