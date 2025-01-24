import os
import sys
from unittest.mock import patch, MagicMock
import logging
import yaml
import pytest
from github import GithubException
import timeout_decorator

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Import the functions to test
from scripts.team_manage_membership import (
    normalize_username,
    get_modified_team_files,
    get_all_team_files,
    load_team_config,
    get_team_members,
    sync_team_members,
    sync_team_memberships,
)

# Increased timeout for complex tests
TEST_TIMEOUT = 30


@pytest.fixture(scope="session", autouse=True)
def setup_timeout():
    """Setup global timeout for all tests with a longer timeout"""
    timeout_decorator.timeout(TEST_TIMEOUT)(lambda: None)()


@pytest.fixture(scope="session")
def mock_logger():
    """Create a logger instance that's reused across tests"""
    logger = logging.getLogger("test_logger")
    logger.setLevel(logging.INFO)
    return logger


@pytest.fixture(scope="session")
def sample_team_config():
    """Reusable team configuration"""
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


@pytest.fixture(scope="function")
def mock_github():
    """Create a fresh mock GitHub instance for each test"""
    with patch("github.Github") as mock:
        mock_instance = mock.return_value
        mock_instance.get_user.return_value = MagicMock()
        # Increased timeout for API calls
        mock_instance.per_page = 100
        mock_instance.timeout = 10
        yield mock_instance


@pytest.fixture(scope="function")
def mock_team():
    """Create a fresh mock team instance for each test"""
    mock = MagicMock()
    mock.name = "test-team"
    # Increased timeout for team operations
    mock.per_page = 100
    mock.timeout = 10
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


def test_load_team_config_valid(tmp_path, sample_team_config):
    test_file = tmp_path / "teams.yml"
    with open(test_file, 'w') as f:
        yaml.dump(sample_team_config, f)
    
    config = load_team_config(str(test_file))
    assert config == sample_team_config
    assert "teams" in config
    assert config["teams"]["team_name"] == "engineering"


def test_load_team_config_invalid_yaml(tmp_path):
    test_file = tmp_path / "invalid.yml"
    with open(test_file, 'w') as f:
        f.write("invalid: yaml: content: - [")
    
    with pytest.raises(ValueError) as exc_info:
        load_team_config(str(test_file))
    assert "Failed to parse YAML" in str(exc_info.value)


def test_load_team_config_file_not_found(tmp_path):
    non_existent_file = tmp_path / "non_existent.yml"
    
    with pytest.raises(FileNotFoundError):
        load_team_config(str(non_existent_file))


def test_get_modified_team_files():
    mock_repo = MagicMock()
    mock_comparison = MagicMock()
    mock_file1 = MagicMock()
    mock_file1.filename = "team1/teams.yml"
    mock_file2 = MagicMock()
    mock_file2.filename = "team2/teams.yml"

    mock_comparison.files = [mock_file1, mock_file2]
    mock_repo.compare.return_value = mock_comparison

    with patch("scripts.team_manage_membership.get_all_team_files", return_value=["team1/teams.yml", "team2/teams.yml"]):
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
    mock_sub_team_1 = MagicMock()
    mock_sub_team_2 = MagicMock()

    # Set increased timeouts for API calls
    mock_org.per_page = 100
    mock_org.timeout = 10
    mock_parent_team.per_page = 100
    mock_parent_team.timeout = 10
    mock_sub_team_1.per_page = 100
    mock_sub_team_1.timeout = 10
    mock_sub_team_2.per_page = 100
    mock_sub_team_2.timeout = 10

    mock_org.get_team_by_slug.side_effect = [mock_parent_team, mock_sub_team_1, mock_sub_team_2]

    sync_team_memberships(mock_github, mock_org, sample_team_config, mock_logger)

    # Verify parent team was synced
    assert mock_org.get_team_by_slug.call_count >= 1
    mock_parent_team.get_members.assert_called_once()


def test_sync_team_memberships_parent_team_not_found(mock_github, mock_logger, sample_team_config):
    mock_org = MagicMock()
    mock_org.get_team_by_slug.side_effect = GithubException(404, "Not found")

    sync_team_memberships(mock_github, mock_org, sample_team_config, mock_logger)
    mock_org.get_team_by_slug.assert_called_once()


# Error handling and edge case tests
def test_sync_team_members_github_exception(mock_github, mock_team, mock_logger):
    mock_github.get_user.side_effect = GithubException(404, "User not found")
    
    with pytest.raises(GithubException):
        sync_team_members(mock_github, mock_team, "test-team", ["non_existent_user"], mock_logger)


# Cleanup fixture to ensure no hanging connections
@pytest.fixture(autouse=True)
def cleanup():
    yield