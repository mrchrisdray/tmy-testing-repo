import os
import sys
import tempfile
import logging
import yaml
import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.process_team_configuration import parse_issue_body, update_teams_config, IndentDumper


def test_parse_issue_body():
    """Test parsing of issue body for team configuration"""
    sample_issue_body = """
    Team Name: Team-Test
    Project: TestProject
    Description: A Test team for validation
    Members: @user1, @user2
    Repositories: repo-test1, repo-test2
    Repository Permissions: write
    """

    team_config = parse_issue_body(sample_issue_body)
    assert team_config["team_name"] == "Team-Test"
    assert team_config["project"] == "TestProject"
    assert team_config["description"] == "A Test team for validation"
    assert team_config["members"] == ["@user1", "@user2"]
    assert team_config["default_repositories"] == ["repo-test1", "repo-test2"]
    assert team_config["repository_permissions"] == "write"


def test_create_teams_config():
    """Test updating teams configuration"""
    # Create a temporary teams.yml file
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as temp_file:
        initial_config = {"default_sub_teams": [], "teams": []}
        yaml.dump(initial_config, temp_file, sort_keys=False, Dumper=IndentDumper, default_flow_style=False, indent=2)
        temp_filename = temp_file.name

    try:
        # Create a new team
        new_team_config = {"team_name": "Team-A", "project": "NewProject", "members": ["@user1"]}

        result = update_teams_config(new_team_config, temp_filename)
        assert result is True

        # Read the updated file
        with open(temp_filename, mode="r", encoding="utf-8") as f:
            updated_config = yaml.safe_load(f)

        # Verify new team addition
        assert updated_config is not None, "Updated conifg should not be None"
        assert "teams" in updated_config, "Update config should have 'teams' key"
        assert isinstance(updated_config["teams"], list), "Teams should still be a list"
        assert len(updated_config["teams"]) == 1, "Should have exactly one team"
        assert updated_config["teams"][0]["team_name"] == "Team-A", "Team name should match"

    finally:
        # Cleanup and restore original file path
        os.unlink(temp_filename)


def test_create_duplicate_team(caplog):
    """Test creating a team with an existing name logs a message"""
    # Create a temporary teams.yaml file
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yml") as temp_file:
        initial_config = {
            "default_sub_teams": [],
            "teams": [{"team_name": "Team-A", "project": "ExistingProject", "members": ["@existing-user"]}],
        }
        yaml.dump(initial_config, temp_file)
        temp_filename = temp_file.name

    try:
        # Attept to create a team with the same name
        duplicate_team_config = {"team_name": "Team-A", "project": "NewProject", "members": ["@newuser"]}

        # Should return False and log message
        caplog.set_level(logging.INFO)
        update_teams_config(duplicate_team_config, temp_filename)

        # Verify no additionl teams were added
        with open(temp_filename, mode="r", encoding="utf-8") as f:
            updated_config = yaml.safe_load(f)
        assert len(updated_config["teams"]) == 1, "Should still only have the one team"

    finally:
        # Cleanuo
        os.unlink(temp_filename)


def test_create_multiple_teams():
    """Test creating multiple unique teams"""
    # Create a temporary teams.yml file
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yml") as temp_file:
        initial_config = {"default_sub_teams": [], "teams": []}
        yaml.dump(initial_config, temp_file, sort_keys=False, Dumper=IndentDumper, default_flow_style=False, indent=2)
        temp_filename = temp_file.name

    try:
        # Create muliple teams
        teams = [
            {"team_name": "Team-A", "project": "ProjectA", "members": ["@user1"]},
            {"team_name": "Team-B", "project": "ProjectB", "members": ["@user2"]},
        ]

        # Create each team and track results
        results = [update_teams_config(team_config, temp_filename) for team_config in teams]

        # Verify all teams were created
        assert results == [True, True]

        # Read the updated file
        with open(temp_filename, mode="r", encoding="utf-8") as f:
            updated_config = yaml.safe_load(f)

        # Verify both teams are added
        assert len(updated_config["teams"]) == 2, "Should have exactly two teams"
        team_names = [team["team_name"] for team in updated_config["teams"]]
        assert set(team_names) == {"Team-A", "Team-B"}, "Team name should match"

    finally:
        # Cleanup
        os.unlink(temp_filename)


if __name__ == "_-main__":
    pytest.main()
