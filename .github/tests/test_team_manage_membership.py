import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import shutil
import tempfile
import yaml
import pytest

# Add script directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.team_manage_membership import (
    normalize_username,
    get_all_team_files,
    load_team_config,
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


@patch("github.Github")
def test_get_modified_team_files(mock_github, temp_dir):
    mock_repo = MagicMock()
    mock_comparison = MagicMock()
    mock_file = MagicMock()
    mock_file.filename = "teams/team1/teams.yml"
    mock_comparison.files = [mock_file]
    mock_repo.compare.return_value = mock_comparison

    result = get_modified_team_files(mock_repo, "base_sha", "head_sha")
    assert len(result) == 1
    assert "teams/team1/teams.yml" in result


def test_get_modified_team_files(mock_repo):
    """Test getting modified team files."""
    base_sha = "base_sha"
    head_sha = "head_sha"
    
    modified_files = get_modified_team_files(mock_repo, base_sha, head_sha)
    assert len(modified_files) == 1
    assert modified_files[0] == "teams/team1/teams.yml"


def test_sync_team_members(logger):
    """Test syncing team members."""
    team = MagicMock()
    members_list = ["user1", "user2"]
    
    sync_team_members(team, members_list, logger)
    
    team.add_membership.assert_any_call("user1")
    team.add_membership.assert_any_call("user2")

def test_sync_team_memberships(logger):
    """Test syncing team memberships."""
    gh_team = MagicMock()
    team_config = {
        "members": ["user1", "user2"]
    }
    
    sync_team_memberships(gh_team, team_config, logger)
    
    gh_team.add_membership.assert_any_call("user1")
    gh_team.add_membership.assert_any_call("user2")
