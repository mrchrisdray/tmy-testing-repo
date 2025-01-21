import os
import sys
from pathlib import Path
from unittest.mock import call, patch, MagicMock
import shutil
import tempfile
import pytest

# Add script directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.team_manage_membership import (
    normalize_username,
    get_all_team_files,
    get_modified_team_files,
    sync_team_members,
    sync_team_memberships,
    setup_logging,
)


@pytest.fixture
def logger():
    return setup_logging()


@pytest.fixture
def temp_dir():
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_github():
    with patch("github.Github") as mock:
        yield mock


@pytest.fixture
def mock_repo():
    """Create mock repository with diff functionality"""
    mock = MagicMock()

    # Setup diff objects
    mock_diff = MagicMock()
    mock_diff.a_path = "teams/team1/teams.yml"

    # Setup commit and diff chain
    mock_commit = MagicMock()
    mock_commit.diff.return_value = [mock_diff]
    mock.commit.return_value = mock_commit

    return mock


@pytest.mark.parametrize(
    "input_username,expected",
    [
        ("@user", "user"),
        ("'user'", "user"),
        ("user", "user"),
        (None, ""),
    ],
)
def test_normalize_username(input_username, expected):
    assert normalize_username(input_username) == expected


def test_get_all_team_files(temp_dir):
    teams_dir = Path(temp_dir) / "teams"
    teams_dir.mkdir()
    (teams_dir / "team1").mkdir()
    (teams_dir / "team2").mkdir()

    team1_file = teams_dir / "team1" / "teams.yml"
    team2_file = teams_dir / "team2" / "teams.yml"
    team1_file.touch()
    team2_file.touch()

    result = get_all_team_files(teams_dir)
    assert len(result) == 2
    assert str(team1_file) in result
    assert str(team2_file) in result


def test_get_modified_team_files(mock_repo):
    """Test getting modified team files."""
    # Setup mock commit to return diff with team file changes
    mock_diff = MagicMock()
    mock_diff.a_path = "teams/team1/teams.yml"
    mock_diff.b_path = "teams/team1/teams.yml"  # Add b_path for modified file
    mock_diff.deleted_file = False  # Indicate file wasn't deleted
    mock_diff.renamed_file = False  # Indicate file wasn't renamed

    mock_commit = MagicMock()
    mock_commit.diff.return_value = [mock_diff]
    mock_repo.get_commit.return_value = mock_commit  # Use get_commit instead of commit

    modified_files = get_modified_team_files(mock_repo, "base_sha", "head_sha")
    assert len(modified_files) == 1
    assert modified_files[0] == "teams/team1/teams.yml"


def test_sync_team_members(logger):
    """Test syncing team members"""
    team = MagicMock()
    team.name = "test-team"  # Add name attribute to mock team

    # Mock the Github user objects properly
    user1 = MagicMock()
    user1.login = "user1"
    user2 = MagicMock()
    user2.login = "user2"

    gh = MagicMock()
    gh.get_user.side_effect = lambda x: {"user1": user1, "user2": user2}[x]

    members_list = ["user1", "user2"]

    # Mock existing members to be empty
    team.get_members.return_value = []

    sync_team_members(gh, team, "test-team", members_list, logger)

    # Verify correct calls
    assert team.add_membership.call_count == 2
    team.add_membership.assert_has_calls([call(user1), call(user2)], any_order=True)


def test_get_modified_team_files_multiple(mock_repo):
    """Test getting multiple modified team files"""
    # Setup multiple diff objects with proper attributes
    mock_diff1 = MagicMock()
    mock_diff1.a_path = "teams/team1/teams.yml"
    mock_diff1.b_path = "teams/team1/teams.yml"
    mock_diff1.deleted_file = False
    mock_diff1.renamed_file = False

    mock_diff2 = MagicMock()
    mock_diff2.a_path = "teams/team2/teams.yml"
    mock_diff2.b_path = "teams/team2/teams.yml"
    mock_diff2.deleted_file = False
    mock_diff2.renamed_file = False

    mock_diff3 = MagicMock()
    mock_diff3.a_path = "other/file.txt"
    mock_diff3.b_path = "other/file.txt"
    mock_diff3.deleted_file = False
    mock_diff3.renamed_file = False

    mock_commit = MagicMock()
    mock_commit.diff.return_value = [mock_diff1, mock_diff2, mock_diff3]
    mock_repo.get_commit.return_value = mock_commit

    modified_files = get_modified_team_files(mock_repo, "base_sha", "head_sha")
    assert len(modified_files) == 2
    assert "teams/team1/teams.yml" in modified_files
    assert "teams/team2/teams.yml" in modified_files


def test_sync_team_memberships(logger):
    """Test syncing team memberships"""

    team_config = {"teams": {"team_name": "test-team", "members": ["user1", "user2"]}}
    gh = MagicMock()
    org = MagicMock()

    sync_team_memberships(gh, org, team_config, logger)

    org.get_team_by_slug.assert_called_once_with("test-team")
