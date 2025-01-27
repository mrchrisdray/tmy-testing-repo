import os
import sys
import yaml
from github import Github, GithubException


def get_pr_number():
    """Retrieve PR number from various sources."""
    pr_number_env = os.environ.get("PR_NUMBER")
    if pr_number_env:
        return int(pr_number_env)

    github_event_path = os.environ.get("GITHUB_EVENT_PATH")
    if github_event_path and os.path.exists(github_event_path):
        import json

        with open(github_event_path, "r") as event_file:
            event_data = json.load(event_file)
            if "pull_request" in event_data:
                return event_data["pull_request"]["number"]
            elif "number" in event_data:
                return event_data["number"]

    raise ValueError("Could not determine PR number")


def validate_pr_requirements(config_path, pr_number, target_branch, team_name, github_token):
    """Validate pull request review requirements."""
    # Load configuration
    with open(config_path, mode="r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    # Initialize GitHub client
    github_obj = Github(github_token)
    repo = github_obj.get_repo(os.environ.get("GITHUB_REPOSITORY"))
    pull_request = repo.get_pull(pr_number)

    # Find branch-specific configuration
    branch_configs = config["pull_requests"]["branches"]
    branch_config = None
    for pattern, config in branch_configs.items():
        pattern_regex = pattern.replace("*", ".*")
        if target_branch and (pattern_regex in target_branch or target_branch.startswith(pattern.rstrip("*"))):
            if not (config.get("exclude") and target_branch in config["exclude"]):
                branch_config = config
                break

    if not branch_config:
        print(f"No configuration found for branch {target_branch}")
        return False

    # Validate required reviews
    required_teams = [
        config.replace("{{ team_name }}", team_name) for config in branch_config.get("required_teams", [])
    ]
    required_team_members = []
    for team_name in required_teams:
        try:
            team = github_obj.get_organization(repo.organization.login).get_team_by_slug(team_name)
            required_team_members.extend([member.login for member in team.get_members()])
        except GithubException as e:
            print(f"Could not fetch members for team {team_name}: {e}")

    # Get PR reviews
    reviews = pull_request.get_reviews()

    # Count approvals from required team members
    required_review_status = [
        any(review.user.login == reviewer and review.state == "APPROVED" for review in reviews)
        for reviewer in required_team_members
    ]

    required_approvals_count = sum(required_review_status)
    is_valid = required_approvals_count >= len(required_team_members)

    print(f"Required team members: {required_team_members}")
    print(f"Approvals count: {required_approvals_count}")
    print(f"Total required members: {len(required_team_members)}")
    print(f"Validation result: {is_valid}")

    return is_valid


def main():
    config_path = os.environ.get("REVIEWERS_CONFIG_PATH", "REVIEWERS.yml")
    team_name = os.environ.get("TEAM_NAME", "team-test-creation-a")
    github_token = os.environ.get("GITHUB_TOKEN")
    target_branch = os.environ.get("TARGET_BRANCH", os.environ.get("GITHUB_BASE_REF", ""))

    try:
        pr_number = get_pr_number()
        result = validate_pr_requirements(config_path, pr_number, target_branch, team_name, github_token)
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
