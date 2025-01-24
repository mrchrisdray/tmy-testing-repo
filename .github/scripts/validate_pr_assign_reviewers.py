import os
import yaml
from github import Github, GithubException

def replace_placeholders(text, team_name):
    """Replace team name placeholders in the configuration."""
    return text.replace('{{ team_name }}', team_name)

def expand_team_members(github_obj, org, teams):
    """Expand team members from GitHub teams."""
    team_members = []
    for team_name in teams:
        try:
            team = github_obj.get_organization(org).get_team_by_slug(team_name)
            team_members.extend([member.login for member in team.get_members()])
        except GithubException as e:
            print(f"Could not fetch members for team {team_name}: {e}")
    return team_members

def assign_reviewers_and_assignees(config_path, pr_number, target_branch, team_name, github_token):
    """Assign reviewers and assignees for a pull request."""
    # Load configuration
    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)

    # Initialize GitHub client
    github_obj = Github(github_token)
    repo = github_obj.get_repo(os.environ.get('GITHUB_REPOSITORY'))

    # Find branch-specific configuration
    branch_configs = config['pull_requests']['branches']
    branch_config = None
    for pattern, config in branch_configs.items():
        if pattern.replace('*', '.*') in target_branch:
            if not (config.get('exclude') and target_branch in config['exclude']):
                branch_config = config
                break

    if not branch_config:
        print(f"No configuration found for branch {target_branch}")
        return False

    # Process reviewers and assignees
    review_teams = [replace_placeholders(team, team_name) for team in branch_config.get('review_teams', [])]
    assignee_teams = [replace_placeholders(team, team_name) for team in branch_config.get('assignees', [])]

    reviewers = expand_team_members(github_obj, repo.organization.login, review_teams)
    assignees = expand_team_members(github_obj, repo.organization.login, assignee_teams)

    # Assign reviewers
    if reviewers:
        pull_request = repo.get_pull(pr_number)
        pull_request.create_review_request(reviewers=reviewers)
        print(f"Assigned reviewers: {', '.join(reviewers)}")

    # Assign assignees
    if assignees:
        issue = repo.get_issue(pr_number)
        issue.edit(assignees=assignees)
        print(f"Assigned assignees: {', '.join(assignees)}")

    return True

def main():
    # Get environment variables
    config_path = os.environ.get('REVIEWERS_CONFIG_PATH', 'REVIEWERS.yml')
    pr_number = int(os.environ.get('PR_NUMBER', 0))
    target_branch = os.environ.get('TARGET_BRANCH', '')
    team_name = os.environ.get('TEAM_NAME', 'team-test-creation-a')
    github_token = os.environ.get('GITHUB_TOKEN')

    # Assign reviewers and assignees
    assign_reviewers_and_assignees(config_path, pr_number, target_branch, team_name, github_token)

if __name__ == '__main__':
    main()