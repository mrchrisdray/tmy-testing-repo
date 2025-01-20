import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import shutil
from pathlib import Path
import tempfile
import yaml
import pytest

# Add script directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from script.team_manage_membership import (
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


def test_load_team_config(temp_dir):
    config_path = Path(temp_dir) / "teams.yml"
    test_config = {"teams": {"name": "test-team", "members": ["user1", "user2"]}}

    with open(config_path, mode="w", encoding="utf-8") as f:
        yaml.dump(test_config, f)

    result = load_team_config(config_path)
    assert result == test_config


def test_sync_team_members(mock_github, logger):
    mock_team = MagicMock()
    mock_team.get_members.return_value = []

    members = ["user1", "user2"]
    sync_team_members(mock_team, members, logger)

    assert mock_team.add_membership.call_count == len(members)


def test_sync_team_memberships(mock_github, logger):
    mock_org = MagicMock()
    mock_team = MagicMock()
    mock_org.get_team.return_value = mock_team

    team_config = {"teams": {"name": "test-team", "members": ["user1", "user2"]}}

    sync_team_memberships(mock_org, team_config, logger)
    assert mock_org.get_team.called
