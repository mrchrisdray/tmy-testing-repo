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


def get_all_team_files(teams_dir: str):
    """Find all teams.yml files in the teams directory structure"""
    teams_path = Path(teams_dir)
    return [str(yml_file) for yml_file in teams_path.glob("*/teams.yml") if yml_file.is_file()]


def load_team_config(file_path: str) -> Dict:
    """Load and parse team configuration from AML file"""
    try:
        with open(file_path, mode="r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if not isinstance(config.get("teams"), dict):
            raise ValueError(f"Invalid team configuration in {file_path}")
        return config
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML in {file_path}: {e}") from e


def get_existing_subteams(org, parent_team_name: str) -> Set[str]:
    """Get set of existing sub-team names for parent team"""
    try:
        parent_team = org.get_team_by_slug(parent_team_name)
        return {team.name for team in parent_team.get_teams()}
    except GithubException as e:
        logging.error(f"Failed to get existing sub-teams for {parent_team_name}: {e}")
        return set()


def create_subteam(org, parent_team_name: str, sub_team_config: Dict, logger: logging.Logger, visibility="closed"):
    """Create a new sub-team under the parent team"""
    try:
        parent_team = org.get_team_by_slug(parent_team_name)
        sub_team_name = sub_team_config["name"]
        description = sub_team_config["description"]

        # Create the team
        org.create_team(name=sub_team_name, description=description, privacy=visibility, parent_team_id=parent_team.id)

        logger.info(f"Created new sub-team: {sub_team_name} under {parent_team_name}")

    except GithubException as e:
        logger.error(f"Failed to create sub_team {sub_team_config['name']}: {e}")


def delete_subteam(org, team_name: str, logger: logging.Logger):
    """Delete a sub_team from the organization"""
    try:
        team = org.get_team_by_slug(team_name)
        team.delete()
        logger.info(f"Delete sub_team: {team_name}")
    except GithubException as e:
        logger.error(f"Failed to delete sub-team {team_name}: {e}")


def sync_subteams(org, team_config: Dict, logger: logging.Logger):
    """Sync Sub-teams base on configuration"""
    team_data = team_config["teams"]
    parent_team_name = team_data["team_name"]

    try:
        # Get current sub_teams from Github
        existing_subteams = get_existing_subteams(org, parent_team_name)

        # Get desired sub_teams from config
        desired_sub_teams = {team_config["name"] for team_config in team_data.get("default_sub_teams", [])}

        # Create new sub-teams
        for sub_team_config in team_data.get("default_sub_teams", []):
            if sub_team_config["name"] not in existing_subteams:
                create_subteam(org, parent_team_name, sub_team_config, logger)

        # Delete removed sub-teams
        team_to_delete = existing_subteams - desired_sub_teams
        for team_name in team_to_delete:
            delete_subteam(org, team_name, logger)

    except GithubException as e:
        logger.error(f"Failed to sync sub-teams: {e}")


def main():
    logger = setup_logging()

    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set")
        return 1

    org_name = os.environ.get("GITHUB_ORGANIZATION")
    if not org_name:
        logger.error("GITHUB_ORGANIZATION environment variable not set")
        return 1

    team_directory = "teams"

    try:
        gh = Github(github_token)
        org = gh.get_organization(org_name)

        if os.getenv("GITHUB_EVENT_NAME") == "push":
            base_sha = os.getenv("GITHUB_EVENT_BEFORE")
            head_sha = os.getenv("GITHUB_SHA")
            repo_full_name = os.environ.get("GITHUB_REPOSITORY")
            if not all([base_sha, head_sha, repo_full_name]):
                logger.error("Missing required environment variables for push event")
                return 1

            try:
                repo = gh.get_repo(repo_full_name)
                team_files = get_modified_team_files(repo, base_sha, head_sha)
                if team_files:
                    logger.info(f"Processing {len(team_files)} modified team files")
                else:
                    logger.info("No team files were modified in this push")
                    return 0
            except GithubException as e:
                logger.error(f"Error accessing repository or getting modified files: {e}")
                logger.info("Falling back to processing all team files")
                team_files = get_all_team_files(team_directory)
        else:
            team_files = get_all_team_files(team_directory)

        if not team_files:
            logger.info("No team files to process")
            return 0

        for team_file in team_files:
            try:
                logger.info(f"processing team file: {team_file}")
                team_config = load_team_config(team_file)
                sync_subteams(org, team_config, logger)
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
