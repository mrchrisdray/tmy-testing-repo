import os
import yaml
from github import Github
import re
from typing import Dict, List, Optional


class PRReviewManager:
    def __init__(self, github_token: str, repository: str):
        """Initialize the PR Review Manager."""
        self.gh = Github(github_token)
        self.repo = self.gh.get_repo(repository)
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load the REVIEWERS.yml configuration file."""
        try:
            config_file = self.repo.get_contents("REVIEWERS.yml")
            return yaml.safe_load(config_file.decoded_content.decode("utf-8"))
        except Exception as e:
            raise Exception(f"Failed to load REVIEWERS.yml: {str(e)}")

    def _get_branch_config(self, branch_name: str) -> Optional[Dict]:
        """Get the configuration for a specific branch."""
        branch_configs = self.config["pull_requests"]["branches"]

        # First check for exact match
        if branch_name in branch_configs:
            return branch_configs[branch_name]

        # Then check pattern matches
        for pattern, config in branch_configs.items():
            if "*" in pattern:
                regex_pattern = pattern.replace("*", ".*")
                if re.match(regex_pattern, branch_name):
                    # Check if branch is excluded
                    if "exclude" in config and branch_name in config["exclude"]:
                        continue
                    return config

        return None

    def _check_required_reviews(self, pr, branch_config: Dict) -> bool:
        """Check if the PR has met the required review conditions."""
        required_approvals = branch_config.get("required_approvals", 0)
        required_teams = branch_config.get("required_teams", [])

        # Get all reviews
        reviews = pr.get_reviews()
        approved_reviews = {}

        for review in reviews:
            if review.state == "APPROVED":
                reviewer = review.user
                # Get user's teams in this repository
                user_teams = [team.name for team in reviewer.get_teams()]

                # Store the approval with the teams the reviewer belongs to
                approved_reviews[reviewer.login] = user_teams

        # Check number of approvals
        if len(approved_reviews) < required_approvals:
            return False

        # Check required teams
        if required_teams:
            approved_teams = set()
            for user_teams in approved_reviews.values():
                approved_teams.update(user_teams)

            if not all(team in approved_teams for team in required_teams):
                return False

        return True

    def process_pull_request(self, pr_number: int):
        """Process a pull request according to the configuration."""
        pr = self.repo.get_pull(pr_number)
        branch_name = pr.base.ref
        branch_config = self._get_branch_config(branch_name)

        if not branch_config:
            print(f"No configuration found for branch: {branch_name}")
            return

        # Assign reviewers and assignees
        review_teams = branch_config.get("review_teams", [])
        assignees = branch_config.get("assignees", [])

        try:
            # Add review teams using team slugs
            for team in review_teams:
                team_slug = team.replace("{{ team_name }}", os.environ.get("TEAM_NAME", ""))
                # Create review request using team slug
                pr.create_review_request(team_reviewers=[team_slug])

            # Add assignees
            for assignee in assignees:
                assignee_name = assignee.replace("{{ team_name }}", os.environ.get("TEAM_NAME", ""))
                pr.add_to_assignees(assignee_name)

            # Check review requirements
            meets_requirements = self._check_required_reviews(pr, branch_config)

            if not meets_requirements:
                # Create or update status check
                self.repo.get_commit(pr.head.sha).create_status(
                    state="pending",
                    target_url="",
                    description="Required reviews not yet met",
                    context="pr-review-requirements",
                )
            else:
                # Update status check to success
                self.repo.get_commit(pr.head.sha).create_status(
                    state="success",
                    target_url="",
                    description="All review requirements met",
                    context="pr-review-requirements",
                )

        except Exception as e:
            print(f"Error processing PR #{pr_number}: {str(e)}")
            raise


def main():
    # Get inputs from GitHub Actions environment
    github_token = os.environ["GITHUB_TOKEN"]
    repository = os.environ["GITHUB_REPOSITORY"]
    pr_number = int(os.environ["PR_NUMBER"])

    # Initialize and run the PR Review Manager
    manager = PRReviewManager(github_token, repository)
    manager.process_pull_request(pr_number)


if __name__ == "__main__":
    main()
