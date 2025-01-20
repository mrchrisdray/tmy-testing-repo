from unittest.mock import MagicMock
from pathlib import Path
import logging
from github import GithubException
import tempfile
import pytest

from team_manage_resource import setup_logging, get_modified_team_files, get_all_team_files


@pytest.fixture
def logger():
    return setup_logging()


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield Path(tmpdirname)


@pytest.fixture
def mock_repo():
    return MagicMock()


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
    assert isinstance(logger, logging.Logger)
    assert logger.level == logging.INFO


def test_get_modified_team_files_success(mock_repo, sample_teams_dir):
    mock_comparison = MagicMock()
    mock_file = MagicMock()
    mock_file.filename = str(sample_teams_dir / "team1" / "teams.yml")
    mock_comparison.files = [mock_file]
    mock_repo.compare.return_value = mock_comparison

    result = get_modified_team_files(mock_repo, "base_sha", "head_sha")
    assert len(result) == 1
    assert str(sample_teams_dir / "team1" / "teams.yml") in result


def test_get_modified_team_files_github_exception(mock_repo):
    mock_repo.compare.side_effect = GithubException(500, "Error")
    result = get_modified_team_files(mock_repo, "base_sha", "head_sha")
    assert isinstance(result, list)
    assert len(result) == 0


def test_get_all_team_files(sample_teams_dir):
    result = get_all_team_files(str(sample_teams_dir))
    assert len(result) == 2
    assert any("team1/teams.yml" in str(f) for f in result)
    assert any("team2/teams.yml" in str(f) for f in result)
