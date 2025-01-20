import os
import sys
from pathlib import Path
import logging
import traceback
from typing import List, Dict
import yaml
from github import Github, GithubException
import requests


def setup_logging():
    """Configure logging for script"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    return logging.getLogger(__name__)


def get_modified_team_files(repo, base_sha: str, head_sha: str) -> List[str]:
    """Get list of modified teams.yml files between two commits."""
    try:
        comparison = repo.compare(base_sha, head_sha)
        modified_files = [file.filename for file in comparison.files]

        all_team_files = get_all_team_files("teams")

        return [str(file) for file in all_team_files if str(file) in modified_files]
    except GithubException as e:
        logging.error(f"Failed to compare commits {base_sha} and {head_sha}: {e}")

        return get_all_team_files("teams")


def get_all_team_files(teams_dir: str) -> List[str]:
    """Find all teams.yml files in the teams directory structure"""
    teams_path = Path(teams_dir)
    return [str(yml_file) for yml_file in teams_path.glob("*/teams.yml") if yml_file.is_file()]


def load_team_config(file_path: str) -> Dict:
    """Load team configuration from Yaml file"""
    try:
        with open(file_path, mode="r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if not isinstance(config.get("teams"), dict):
            raise ValueError(f"Invalid team configuration in {file_path}")

        return config
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML in {file_path}: {e}") from e


def remove_team_repository(
    github_token: str, org_name: str, team_slug: str, repo_name: str, logger: logging.Logger
) -> bool:
    """Remove a repository from a team using GitHub Rest API directly"""
    BASE_URL = "https://api.github.com"
    url = f"{BASE_URL}/orgs/{org_name}/teams/{team_slug}/repos/{org_name}/{repo_name}"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-Github-Api-Version": "2022-11-28",
    }
    try:
        # Send DELETE request to remove repo from team
        response = requests.delete(url, headers=headers)

        # Check response status
        if response.status_code in [204, 200]:
            logger.info(f"Successfully removed repository {repo_name} from team {team_slug}")
            return True
        if response.status_code == 404:
            logger.warning(f"Response: {response.text} -for code: {response.status_code}")
            logger.warning(f"Repository {repo_name} not found or team dose not have access")
            return True

        logger.error(f"Failed to remove repository {repo_name} from {team_slug}. Status code: {response.status_code}")
        logger.error(f"Response: {response.text}")
        return False

    except requests.RequestException as e:
        logger.error(f"Error removing repository {repo_name} from team: {e}")
        return False


def sync_team_repos(
    org,
    team,
    desired_repos: List[str],
    desired_permissions: str,
    logger: logging.Logger,
    parent_repos: List[str] = None,
    is_parent_team: bool = False,
):
    """Sync team repository permissions based on config"""
    permission_mapping = {"read": "pull", "write": "push", "admin": "admin", "maintain": "maintain", "triage": "triage"}
    try:
        # Map the permission if needed
        if desired_permissions.lower() in permission_mapping:
            api_permission = permission_mapping[desired_permissions.lower()]
        else:
            api_permission = desired_permissions.lower()
            print(f"Using custom permission: {api_permission}")
    except GithubException as e:
        logger.error(f"Error mapping permissions for {team.name}: {str(e)}")

    remove_all_repos = (desired_repos is None) or (len(desired_repos) == 0)
    github_token = os.environ.get("GITHUB_TOKEN")
    try:

        current_team_repos = team.get_repos()
        current_repos_names = [repo.name for repo in current_team_repos]

        if remove_all_repos:
            for current_repo in current_team_repos:
                try:
                    # Check if repository is in the parent team's repository list
                    if not is_parent_team and parent_repos and current_repo.name in parent_repos:
                        logger.warning(
                            f"Repository {current_repo.name} is being removed from sub-team {team.name}, "
                            f"but it is still part of the parent team's repository list. "
                            f"Access to repositories is inherited from parent team. "
                        )
                    repo = team.organization.get_repo(current_repo.name)
                    remove_success = remove_team_repository(
                        github_token=github_token,
                        org_name=org.login,
                        team_slug=team.slug,
                        repo_name=current_repo.name,
                        logger=logger,
                    )
                    if not remove_success:
                        try:
                            team.remove_from_repos(repo)
                            logger.info(
                                f"Removed {current_repo.name} from {team.name} using PyGithub method - no repositories configured"
                            )
                        except Exception as pygh_error:
                            logger.error(
                                f"Failed to remove {current_repo.name} from {team.name} using PyGithub: {pygh_error}"
                            )
                except GithubException as e:
                    logger.error(f"Failed to remove {current_repo.name} from  {team.name}: {e}")
            return

        # Add/update
        for repo_name in desired_repos:
            try:
                repo = org.get_repo(repo_name)
                # Check if repository already in the team
                if repo_name not in current_repos_names:
                    # Add repository to team if not present
                    try:
                        team.update_team_repository(repo, api_permission)
                        logger.info(f"Added {repo_name} to {team.name} with {api_permission} permission")
                    except GithubException as e:
                        logger.error(f"Failed to add {repo_name} to {team.name}: {e}")
                # Check and update permissions if needed
                try:
                    # Get current permissions for this team on the repo
                    team_repo_permission = team.get_repo_permission(repo)
                    # Compare current permissions with desired permission
                    if team_repo_permission != api_permission:
                        # Update team repository permission
                        team.update_team_repository(repo, api_permission)
                        logger.info(f"Updated {repo_name} permissions for {team.name} to {api_permission}")
                except GithubException as perm_error:
                    logger.error(f"Error checking/updating permissions for {repo_name}: {perm_error}")
            except GithubException as repo_error:
                logger.error(f"Error accessing repository {repo_name}: {repo_error}")

        # Remove
        for current_repo in current_team_repos:
            if current_repo.name not in desired_repos:
                try:
                    # Check if repository is in the parent team's repository list
                    if not is_parent_team and parent_repos and current_repo.name in parent_repos:
                        logger.warning(
                            f"Repository {current_repo.name} is being removed from sub-team {team.name}, "
                            f"but it is still part of the parent team's repository list. "
                            f"Access to repositories is inherited from parent team. "
                        )
                    repo = team.organization.get_repo(current_repo.name)
                    remove_success = remove_team_repository(
                        github_token=github_token,
                        org_name=org.login,
                        team_slug=team.slug,
                        repo_name=current_repo.name,
                        logger=logger,
                    )
                    if not remove_success:
                        try:
                            team.remove_from_repos(current_repo)
                            logger.info(
                                f"Removed {current_repo.name} from {team.name} with permissions: {desired_permissions}"
                            )
                        except Exception as pygh_error:
                            logger.error(
                                f"Failed to remove {current_repo.name} from {team.name} using PyGithub: {pygh_error}"
                            )
                except GithubException as e:
                    logger.error(f"Failed to remove {current_repo.name} from {team.name}: {e}")

    except GithubException as e:
        logger.error(f"Unexpected error syncing repositories for {team.name}: {e}")
        logger.error(traceback.format_exc())


def sync_team_repositories(org, team_config: Dict, logger: logging.Logger):
    """Sync team repositories based on configuration"""
    team_data = team_config["teams"]
    parent_team_name = team_data["team_name"]

    try:
        try:
            parent_team = org.get_team_by_slug(parent_team_name)
            logger.info(f"Found parent team: {parent_team_name}")

            parent_repos = team_data.get("repositories", [])
            parent_permissions = team_data.get("repository_permissions", "read")
            sync_team_repos(org, parent_team, parent_repos, parent_permissions, logger, is_parent_team=True)

        except GithubException:
            logger.error(f"Parent team {parent_team_name} does not exist in the organization - skipping")
            return

        for sub_team_config in team_data.get("default_sub_teams", []):
            sub_team_name = sub_team_config["name"]
            try:
                sub_team = org.get_team_by_slug(sub_team_name)
                logger.info(f"Found sub-team: {sub_team_name}")

                sub_team_repos = sub_team_config.get("repositories", [])
                sub_team_permissions = sub_team_config.get("repository_permissions", "read")
                sync_team_repos(
                    org,
                    sub_team,
                    sub_team_repos,
                    sub_team_permissions,
                    logger,
                    parent_repos=parent_repos,
                    is_parent_team=False,
                )

            except GithubException:
                logger.error(f"Sub-team{sub_team_name} does not exist in the organization - skipping")
                continue

    except GithubException as e:
        logger.error(f"Failed to sync teams: {e}")


def main():
    logger = setup_logging()

    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable is not set")
        return 1

    org_name = os.environ.get("GITHUB_ORGANIZATION")
    if not org_name:
        logger.error("GITHUB_ORGANIZATION environment variable is not set")
        return 1

    team_directory = "teams"

    try:
        gh = Github(github_token)
        org = gh.get_organization(org_name)

        if os.getenv("GITHUB_EVENT_NAME") == "push" and not os.environ.get("GITHUB_API_EVENT") == "api-push":
            base_sha = os.getenv("GITHUB_EVENT_BEFORE")
            head_sha = os.getenv("GITHUB_SHA")
            repo_full_name = os.environ.get("GITHUB_REPOSITORY")
            if not all([base_sha, head_sha, repo_full_name]):
                logger.error(f"Missing required environment variables for push event")
                logger.debug(f"base_sha: {base_sha}, head_sha: {head_sha}, repo: {repo_full_name} ")
                return 1

            try:
                repo = gh.get_repo(repo_full_name)
                logger.debug(f"Successfully accessed repository: {repo_full_name}")
                team_files = get_modified_team_files(repo, base_sha, head_sha)
                if team_files is not None:
                    logger.info(f"Processing all {len(team_files)} team files")
                else:
                    logger.info("No team files were modified in this push")
                    return 0
            except GithubException as e:
                logger.error(f"Error accessing repository or getting modified files: {str(e)}")
                logger.info("Falling back to processing all team files")
                team_files = get_all_team_files(team_directory)
        else:
            team_files = get_all_team_files(team_directory)

        if not team_files:
            logger.info("No team files to process")
            return 0

        for team_file in team_files:
            try:
                logger.info(f"Processing team file: {team_file}")
                team_config = load_team_config(team_file)
                sync_team_repositories(org, team_config, logger)
            except Exception as e:
                logger.error(f"Failed to process {team_file}: {str(e)}\n{traceback.format_exc()}")

        return 0

    except Exception as e:
        logger.error(f"Unexpected error in main: {str(e)}\n{traceback.format_exc()}")
        return 1
    finally:
        gh.close()


if __name__ == "__main__":
    sys.exit(main())
