"""Module to process GitHub issue body to create a team configuration setup"""

import os
import json
import logging
import re
import yaml

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Define the root teams file path
ROOT_TEAMS_FILE = "teams.yml"


class IndentDumper(yaml.Dumper):
    """Format YAML output indents"""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def parse_issue_body(issue_body):
    """Parse the issue body to extract team configuration details"""

    # Expected format:
    # Team Name: Team-X
    # Project: ProjectName
    # Description: Team description
    # Members: @user1 @user2
    # Repositories: repo-a, repo-b
    # Repository Permissions: read

    team_config = {}

    # Extract details
    team_name_match = re.search(r"Team Name:\s*(.+)", issue_body)
    team_config["team_name"] = team_name_match.group(1).strip() if team_name_match else None

    project_match = re.search(r"Project:\s*(.+)", issue_body)
    team_config["project"] = project_match.group(1).strip() if project_match else None

    desc_match = re.search(r"Description:\s*(.+)", issue_body)
    team_config["description"] = desc_match.group(1).strip() if desc_match else None

    members_match = re.search(r"Members:\s*(.+)", issue_body)
    team_config["members"] = [m.strip() for m in members_match.group(1).split(",")] if members_match else []

    repos_match = re.search(r"Repositories:\s*(.+)", issue_body)
    team_config["default_repositories"] = [r.strip() for r in repos_match.group(1).split(",")] if repos_match else []

    perms_match = re.search(r"Repository Permissions:\s*(.+)", issue_body)
    team_config["repository_permissions"] = perms_match.group(1).strip() if perms_match else "read"

    return team_config


def update_teams_config(new_team_config, config_file=ROOT_TEAMS_FILE):
    """Update the teams.yml configuration file"""

    # Read existing configuration
    with open(config_file, mode="r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    # Ensure teams list exists
    if "teams" not in config:
        config["teams"] = []

    # Check if team already exists
    existing_team = next((team for team in config["teams"] if team["team_name"] == new_team_config["team_name"]), None)
    if existing_team:
        logger.info(f"Team Already exists and can not be updated {new_team_config['team_name']}")
        logger.info(f"This is for setup only. No changes made")
        return False

    config["teams"].append(new_team_config)

    with open(config_file, mode="w", encoding="utf-8") as f:
        yaml.dump(config, f, sort_keys=False, Dumper=IndentDumper, default_flow_style=False, indent=2)

    logger.info(f"Created team configuration for {new_team_config['team_name']}")
    return True


def main():
    """Setup team configuration setup"""
    # Get the issue payload from envrionment variable
    issue_payload = os.environ.get("ISSUE_PAYLOAD")

    if not issue_payload:
        print("No issue payload found")
        return

    # Parse the payload
    payload = json.loads(issue_payload)

    # Parse issue body
    team_config = parse_issue_body(payload["body"])

    # Update teams configuration
    update_teams_config(team_config)

    print(f"Process team configuration for {team_config.get('team_name', 'Unkonwn Team')}")


if __name__ == "__main__":
    main()
