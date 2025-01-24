import os
from github import Github, GithubException


def block_pr_merge(pr_number, github_token):
    """Block merge for a specific pull request."""
    # Initialize GitHub client
    github_obj = Github(github_token)
    repo = github_obj.get_repo(os.environ.get("GITHUB_REPOSITORY"))

    try:
        # Update PR to block merge
        pull_request = repo.get_pull(pr_number)
        pull_request.edit(state="closed")  # Alternative method to block merge
        print(f"Blocked merge for PR #{pr_number}")
    except GithubException as e:
        print(f"Error blocking PR merge: {e}")
        return False

    return True


def main():
    # Get environment variables
    pr_number = int(os.environ.get("PR_NUMBER", 0))
    github_token = os.environ.get("GITHUB_TOKEN")

    # Block PR merge
    block_pr_merge(pr_number, github_token)


if __name__ == "__main__":
    main()
