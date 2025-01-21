import os
from subprocess import call
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
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
    """Create mock repository with diff functionality."""
    mock = MagicMock()
    mock_diff = MagicMock()
    mock_diff.a_path = "teams/team1/teams.yml"
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
    base_sha = "base_sha"
    head_sha = "head_sha"

    modified_files = get_modified_team_files(mock_repo, base_sha, head_sha)
    assert len(modified_files) == 1
    assert modified_files[0] == "teams/team1/teams.yml"


def test_sync_team_members(logger):
    """Test syncing team members"""
    team = MagicMock()
    members_list = ["user1", "user2"]
    gh = MagicMock()
    gh.get_user.side_effect = lambda x: MagicMock(login=x)

    sync_team_members(gh, team, "test-team", members_list, logger)

    assert team.add_membership.call_count == 2
    team.add_membership.assert_has_calls(
        [call(gh.get_user("user1"), role="member"), call(gh.get_user("user2"), role="member")]
    )


def test_sync_team_memberships(logger):
    """Test syncing team memberships"""

    team_config = {"teams": {"team_name": "test-team", "members": ["user1", "user2"]}}
    gh = MagicMock()
    org = MagicMock()

    sync_team_memberships(gh, org, team_config, logger)

    org.get_team_by_slug.assert_called_once_with("test-team")
