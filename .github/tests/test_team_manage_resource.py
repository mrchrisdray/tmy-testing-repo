import os
import sys
from unittest.mock import MagicMock
from pathlib import Path
import logging
import tempfile
from github import GithubException
import pytest

# Add script directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.team_manage_resource import setup_logging, get_modified_team_files, get_all_team_files


@pytest.fixture
def logger():
    return setup_logging()


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield Path(tmpdirname)


@pytest.fixture
def mock_repo():
    mock = MagicMock()
    mock_diff = MagicMock()
    mock_diff.a_path = "teams/team1/teams.yml"
    mock_commit = MagicMock()
    mock_commit.diff.return_value = [mock_diff]
    mock.commit.return_value = mock_commit
    return mock


@pytest.fixture
def sample_teams_dir(temp_dir):
    teams_dir = temp_dir / "teams"
    teams_dir.mkdir(parents=True)

    # Create sample team directories and files
    (teams_dir / "team1").mkdir()
    (teams_dir / "team2").mkdir()
    (teams_dir / "team1" / "teams.yml").touch()
    (teams_dir / "team2" / "teams.yml").touch()

    return teams_dir


def test_setup_logging():
    logger = setup_logging()
    assert logger.level == logging.INFO
    assert len(logger.handlers) == 1


def test_get_modified_team_files_success(mock_repo):
    base_sha = "base_sha"
    head_sha = "head_sha"

    modified_files = get_modified_team_files(mock_repo, base_sha, head_sha)
    assert len(modified_files) == 1
    assert modified_files[0] == "teams/team1/teams.yml"


def test_get_modified_team_files_github_exception(mock_repo):
    mock_repo.commit.side_effect = GithubException(404, "Not found")
    modified_files = get_modified_team_files(mock_repo, "base_sha", "head_sha")
    assert len(modified_files) == 0


def test_get_all_team_files(sample_teams_dir):
    result = get_all_team_files(str(sample_teams_dir))
    assert len(result) == 2
    assert any("team1/teams.yml" in str(f) for f in result)
    assert any("team2/teams.yml" in str(f) for f in result)
