import os
import sys
from unittest.mock import MagicMock, patch
from github import GithubException
import pytest
import yaml

# Add script directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.team_manage_resource import (
    sync_team_repos,
    sync_team_repositories,
    load_team_config,
    remove_team_repository,
)


@pytest.fixture
def mock_org():
    mock = MagicMock()
    mock.login = "test-org"
    return mock


@pytest.fixture
def mock_team():
    mock = MagicMock()
    mock.name = "test-team"
    mock.slug = "test-team"
    return mock


@pytest.fixture
def mock_repo():
    mock = MagicMock()
    mock.name = "test-repo"
    return mock


@pytest.fixture(scope="session")
def mock_logger():
    """Create a logger instance that's reused across tests"""
    logger = MagicMock()
    logger.info = MagicMock()
    return logger


@pytest.fixture
def sample_team_config():
    return {
        "teams": {
            "team_name": "parent-team",
            "repositories": ["repo1", "repo2"],
            "repository_permissions": "write",
            "default_sub_teams": [{"name": "sub-team-1", "repositories": ["repo3"], "repository_permissions": "read"}],
        }
    }


@pytest.fixture
def temp_config_file(tmp_path, sample_team_config):
    config_file = tmp_path / "teams.yml"
    with open(config_file, mode="w", encoding="utf-8") as f:
        yaml.dump(sample_team_config, f)
    return str(config_file)


def test_sync_team_repos_add_new_repo(mock_org, mock_team, mock_logger):
    # Setup
    desired_repos = ["new-repo"]
    mock_team.get_repos.return_value = []
    mock_repo = MagicMock()
    mock_org.get_repo.return_value = mock_repo

    # Test
    sync_team_repos(mock_org, mock_team, desired_repos, "write", mock_logger)

    # Verify
    mock_team.update_team_repository.assert_called_with(mock_repo, "push")
    mock_logger.info.assert_called_with(f"Updated new-repo permissions for {mock_team.name} to push")


def test_sync_team_repos_update_permissions(mock_org, mock_team, mock_logger):
    # Setup
    desired_repos = ["existing-repo"]
    mock_repo = MagicMock(name="existing-repo")
    mock_team.get_repos.return_value = [mock_repo]
    mock_team.get_repo_permission.return_value = "pull"
    mock_org.get_repo.return_value = mock_repo

    # Test
    sync_team_repos(mock_org, mock_team, desired_repos, "write", mock_logger)

    # Verify
    mock_team.update_team_repository.assert_called_with(mock_repo, "push")


def test_sync_team_repos_github_exception(mock_org, mock_team, mock_logger):
    # Setup
    desired_repos = ["repo"]
    mock_team.get_repos.side_effect = GithubException(404, "Not found")

    # Test
    sync_team_repos(mock_org, mock_team, desired_repos, "read", mock_logger)

    # Verify
    mock_logger.error.assert_called()


def test_load_team_config_valid(temp_config_file):
    # Test
    config = load_team_config(temp_config_file)

    # Verify
    assert "teams" in config
    assert config["teams"]["team_name"] == "parent-team"
    assert len(config["teams"]["repositories"]) == 2


def test_load_team_config_invalid_format(tmp_path):
    # Setup
    invalid_config = tmp_path / "invalid.yml"
    with open(invalid_config, mode="w", encoding="utf-8") as f:
        f.write("invalid: :")

    # Test & Verify
    with pytest.raises(ValueError):
        load_team_config(str(invalid_config))


def test_remove_team_repository_success():
    # Setup
    mock_logger = MagicMock()
    with patch("requests.delete") as mock_delete:
        mock_delete.return_value.status_code = 204

        # Test
        result = remove_team_repository("fake-token", "test-org", "test-team", "test-repo", mock_logger)

        # Verify
        assert result is True
        mock_logger.info.assert_called_once()


def test_remove_team_repository_failure():
    # Setup
    mock_logger = MagicMock()
    with patch("requests.delete") as mock_delete:
        mock_delete.return_value.status_code = 500
        mock_delete.return_value.text = "Internal Server Error"

        # Test
        result = remove_team_repository("fake-token", "test-org", "test-team", "test-repo", mock_logger)

        # Verify
        assert result is False
        mock_logger.error.assert_called()


@pytest.mark.integration
def test_sync_team_repositories_integration(mock_org, mock_logger, sample_team_config):
    # Setup
    parent_team = MagicMock()
    sub_team = MagicMock()
    mock_org.get_team_by_slug.side_effect = {"parent-team": parent_team, "sub-team-1": sub_team}.get

    # Test
    sync_team_repositories(mock_org, sample_team_config, mock_logger)

    # Verify
    parent_team.get_repos.assert_called_once()
    sub_team.get_repos.assert_called_once()
    mock_logger.info.assert_called()
