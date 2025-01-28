import os
import re
from typing import Dict, List, Optional
import yaml
from github import Github


class PRReviewManager:
    def __init__(self, github_token: str, repository: str):
        """Initialize the PR Review Manager."""
        self.gh = Github(github_token)
        self.repo = self.gh.get_repo(repository)
        self.config = self._load_config()
        self.org = self.repo.organization

    def _load_config(self) -> Dict:
        """Load the REVIEWERS.yml configuration file from root directory."""
        try:
            # Get repository contents at root level
            contents = self.repo.get_contents("")
            config_file = None
            
            # Look specifically for REVIEWERS.yml in root contents
            for content_file in contents:
                if content_file.name == "REVIEWERS.yml":
                    config_file = content_file
                    break
            
            if not config_file:
                print("Debug: Files found in root:", [f.name for f in contents])
                raise FileNotFoundError("REVIEWERS.yml not found in repository root")
            
            content = config_file.decoded_content
            if not content:
                raise ValueError("REVIEWERS.yml is empty")
            
            print(f"Debug: Successfully loaded REVIEWERS.yml, size: {len(content)} bytes")
            
            config = yaml.safe_load(content.decode("utf-8"))
            if not config:
                raise ValueError("REVIEWERS.yml contains no valid configuration")
            
            print("Debug: Successfully parsed YAML configuration")
            return config
            
        except yaml.YAMLError as e:
            print(f"Debug: YAML parsing error - {str(e)}")
            raise ValueError(f"Failed to parse REVIEWERS.yml: {str(e)}") from e
        except Exception as e:
            print(f"Debug: Unexpected error while loading config - {str(e)}")
            raise FileNotFoundError(f"Failed to load REVIEWERS.yml: {str(e)}") from e

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

    def _get_team_members(self, team_slug: str) -> List[str]:
        """Get list of usernames for members of a team."""
        try:
            team = self.org.get_team_by_slug(team_slug)
            return [member.login for member in team.get_members()]
        except Exception as e:
            print(f"Error getting team members for {team_slug}: {str(e)}")
            return []

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
        assignee_teams = branch_config.get("assignees", [])

        try:
            # Add review teams using team slugs
            for team in review_teams:
                team_slug = team.replace("{{ team_name }}", os.environ.get("TEAM_NAME", ""))
                # Create review request using team slug
                pr.create_review_request(team_reviewers=[team_slug])

            # Add assignees from teams
            assignees = set()
            for team in assignee_teams:
                team_slug = team.replace("{{ team_name }}", os.environ.get("TEAM_NAME", ""))
                # Convert team slug to lowercase and replace spaces with hyphens
                team_slug = team_slug.lower().replace(" ", "-")
                # Get all members of the team and add them to assignees set
                team_members = self._get_team_members(team_slug)
                assignees.update(team_members)

            # Filter out the PR creator from assignees if present
            if pr.user.login in assignees:
                assignees.remove(pr.user.login)

            # Only proceed if there are assignees to add
            if assignees:
                try:
                    # Add assignees in batches to handle GitHub's limitation
                    # GitHub allows up to 10 assignees per request
                    assignees_list = list(assignees)
                    for i in range(0, len(assignees_list), 10):
                        batch = assignees_list[i : i + 10]
                        pr.add_to_assignees(*batch)
                except Exception as e:
                    if "404" in str(e):
                        print(f"Warning: Unable to assign users to PR #{pr.number}. No more users found.")
                    else:
                        raise

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

    # Debug: Check repository access
    gh = Github(github_token)
    try:
        repo = gh.get_repo(repository)
        print(f"Debug: Successfully accessed repository {repository}")
        print(f"Debug: Current user has access to: {[p for p in repo.permissions]}")
    except Exception as e:
        print(f"Debug: Error accessing repository - {str(e)}")

    # Initialize and run the PR Review Manager
    manager = PRReviewManager(github_token, repository)
    manager.process_pull_request(pr_number)

if __name__ == "__main__":
    main()
