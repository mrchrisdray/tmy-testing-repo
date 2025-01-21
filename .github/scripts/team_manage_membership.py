import os
import sys
from pathlib import Path
import logging
import traceback
from typing import List, Dict, Set
import yaml
from github import Github, GithubException


def setup_logging():
    """Configure logging for script"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    return logging.getLogger(__name__)


def normalize_username(username: str) -> str:
    """Remove @ prefix and quotes from username id present"""
    if username is None:
        return ""
    return username.lstrip("@").strip("'")


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


def get_team_members(team, logger: logging.Logger) -> Set[str]:
    """Safely get team members handling empty teams"""
    try:
        return {member.login for member in team.get_members()}
    except GithubException as e:
        logger.error(f"Failed to get members for team {team.name}: {e}")
        return set()


def remove_all_members(team, team_name: str, logger: logging.Logger):
    """Remove all members for a team with empty members list in config YAML file."""
    current_members = get_team_members(team, logger)
    for member in current_members:
        try:
            team.remove_membership(member)
            logger.info(f"Removed {member} from {team_name}")
        except GithubException as e:
            logger.error(f"Failed to remove {member} from {team_name}: {e}")


def sync_team_members(gh, team, team_name: str, members_list: List[str], logger: logging.Logger):
    """Sync team members based on the provided list"""
    if members_list is None or not members_list:
        logger.info(f"Empty members list for {team_name} - removing all members")
        remove_all_members(team, team_name, logger)
        return

    desired_members = {normalize_username(member) for member in members_list}
    current_members = get_team_members(team, logger)

    # Add
    for member in desired_members - current_members:
        try:
            user = gh.get_user(member)
            team.add_membership(user, role="member")
            logger.info(f"Added {member} to {team_name}")
        except GithubException as e:
            logger.error(f"Failed to add {member} to {team_name}: {e}")

    # Remove
    for member in current_members - desired_members:
        try:
            user = gh.get_user(member)
            team.remove_membership(user)
            logger.info(f"Removed {member} from {team_name}")
        except GithubException as e:
            logger.error(f"Failed to remove {member} from {team_name}: {e}")


def sync_team_memberships(gh, org, team_config: Dict, logger: logging.Logger):
    """Sync team memberships based on configuration"""
    team_data = team_config["teams"]
    parent_team_name = team_data["team_name"]

    try:
        try:
            parent_team = org.get_team_by_slug(parent_team_name)
            logger.info(f"Found parent team: {parent_team_name}")

            parent_members = team_data.get("members", [])
            sync_team_members(gh, parent_team, parent_team_name, parent_members, logger)

        except GithubException:
            logger.error(f"Parent team {parent_team_name} does not exist in the organization - skipping")
            return

        for sub_team_config in team_data.get("default_sub_teams", []):
            sub_team_name = sub_team_config["name"]
            try:
                sub_team = org.get_team_by_slug(sub_team_name)
                logger.info(f"Found sub-team: {sub_team_name}")

                sub_team_members = sub_team_config.get("members", [])
                sync_team_members(gh, sub_team, sub_team_name, sub_team_members, logger)

            except GithubException:
                logger.error(f"Sub-team{sub_team_name} does not exist in the organization - skipping")
                continue

    except GithubException as e:
        logger.error(f"Failed to sync teams: {e}")


def main():
    logger = setup_logging()

    github_token = os.environ.get("GITHUB_TOKEN")
    org_name = os.environ.get("GITHUB_ORGANIZATION")
    if not all([org_name, github_token]):
        logger.error("GITHUB_TOKEN/GITHUB_ORGANIZATION environment variable is not set")
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
                sync_team_memberships(gh, org, team_config, logger)
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