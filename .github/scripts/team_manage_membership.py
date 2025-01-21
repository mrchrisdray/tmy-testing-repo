import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import yaml
import logging
from github import GithubException

# Import the functions to test
from paste import (
    normalize_username,
    get_modified_team_files,
    get_all_team_files,
    load_team_config,
    get_team_members,
    sync_team_members,
    sync_team_memberships,
)


@pytest.fixture
def mock_logger():
    return logging.getLogger("test_logger")


@pytest.fixture
def sample_team_config():
    return {
        "teams": {
            "team_name": "engineering",
            "members": ["@user1", "user2", "'user3'"],
            "default_sub_teams": [
                {"name": "backend", "members": ["user1", "user2"]},
                {"name": "frontend", "members": ["user2", "user3"]},
            ],
        }
    }


@pytest.fixture
def mock_github():
    mock = MagicMock()
    mock.get_user.return_value = MagicMock()
    return mock


@pytest.fixture
def mock_team():
    mock = MagicMock()
    mock.name = "test-team"
    return mock


def test_normalize_username():
    assert normalize_username("@username") == "username"
    assert normalize_username("'username'") == "username"
    assert normalize_username("username") == "username"
    assert normalize_username(None) == ""
    assert normalize_username("@'username'") == "username"


def test_get_all_team_files(tmp_path):
    # Create temporary directory structure
    team1_dir = tmp_path / "team1"
    team2_dir = tmp_path / "team2"
    team1_dir.mkdir()
    team2_dir.mkdir()

    # Create teams.yml files
    (team1_dir / "teams.yml").touch()
    (team2_dir / "teams.yml").touch()
    (tmp_path / "random.yml").touch()

    files = get_all_team_files(str(tmp_path))
    assert len(files) == 2
    assert all("teams.yml" in f for f in files)


@patch("builtins.open")
def test_load_team_config_valid(mock_open, sample_team_config):
    mock_open.return_value.__enter__.return_value.read.return_value = yaml.dump(sample_team_config)
    config = load_team_config("dummy_path")
    assert config == sample_team_config
    assert "teams" in config
    assert config["teams"]["team_name"] == "engineering"


@patch("builtins.open")
def test_load_team_config_invalid_yaml(mock_open):
    mock_open.return_value.__enter__.return_value.read.return_value = "invalid: yaml: content: - ["
    with pytest.raises(ValueError) as exc_info:
        load_team_config("dummy_path")
    assert "Failed to parse YAML" in str(exc_info.value)


def test_get_modified_team_files():
    mock_repo = MagicMock()
    mock_comparison = MagicMock()
    mock_file1 = MagicMock()
    mock_file1.filename = "team1/teams.yml"
    mock_file2 = MagicMock()
    mock_file2.filename = "team2/teams.yml"

    mock_comparison.files = [mock_file1, mock_file2]
    mock_repo.compare.return_value = mock_comparison

    files = get_modified_team_files(mock_repo, "base-sha", "head-sha")
    assert len(files) == 2
    assert "team1/teams.yml" in files
    assert "team2/teams.yml" in files


def test_get_team_members(mock_team, mock_logger):
    member1 = MagicMock()
    member1.login = "user1"
    member2 = MagicMock()
    member2.login = "user2"
    mock_team.get_members.return_value = [member1, member2]

    members = get_team_members(mock_team, mock_logger)
    assert members == {"user1", "user2"}


def test_get_team_members_error(mock_team, mock_logger):
    mock_team.get_members.side_effect = GithubException(404, "Not found")
    members = get_team_members(mock_team, mock_logger)
    assert members == set()


def test_sync_team_members_add_remove(mock_github, mock_team, mock_logger):
    # Setup current team members
    current_member = MagicMock()
    current_member.login = "existing_user"
    mock_team.get_members.return_value = [current_member]

    # Test syncing with new desired members
    desired_members = ["new_user"]
    sync_team_members(mock_github, mock_team, "test-team", desired_members, mock_logger)

    # Verify that new member was added and existing member was removed
    mock_team.add_membership.assert_called_once()
    mock_team.remove_membership.assert_called_once()


def test_sync_team_members_empty_list(mock_github, mock_team, mock_logger):
    current_member = MagicMock()
    current_member.login = "existing_user"
    mock_team.get_members.return_value = [current_member]

    sync_team_members(mock_github, mock_team, "test-team", [], mock_logger)
    mock_team.remove_membership.assert_called_once()
    mock_team.add_membership.assert_not_called()


def test_sync_team_memberships(mock_github, mock_logger, sample_team_config):
    mock_org = MagicMock()
    mock_parent_team = MagicMock()
    mock_sub_team = MagicMock()

    mock_org.get_team_by_slug.side_effect = [mock_parent_team, mock_sub_team, mock_sub_team]

    sync_team_memberships(mock_github, mock_org, sample_team_config, mock_logger)

    # Verify parent team was synced
    assert mock_org.get_team_by_slug.call_count >= 1
    mock_parent_team.get_members.assert_called_once()


def test_sync_team_memberships_parent_team_not_found(mock_github, mock_logger, sample_team_config):
    mock_org = MagicMock()
    mock_org.get_team_by_slug.side_effect = GithubException(404, "Not found")

    sync_team_memberships(mock_github, mock_org, sample_team_config, mock_logger)
    mock_org.get_team_by_slug.assert_called_once()
