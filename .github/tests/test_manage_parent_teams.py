"""Test module for team_manage_parent_teams.py."""

import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, call
import pytest
import yaml
from github import Github, Organization, Team
import git
from git.exc import InvalidGitRepositoryError

# Add script directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.team_manage_parent_teams import (
    load_yaml_config,
    find_git_root,
    get_existing_team_directories,
    get_configured_teams,
    delete_team_directory,
    delete_github_team,
    commit_changes,
    main,
)


@pytest.fixture
def mock_repo():
    with patch("git.Repo") as MockRepo:
        mock_instance = Mock(spec=git.Repo)
        mock_instance.working_dir = "/fake/repo/path"
        mock_instance.is_dirty.return_value = True
        mock_instance.untracked_files = []
        # Setup remote
        mock_remote = Mock()
        mock_remote.name = "origin"
        mock_instance.remotes = [mock_remote]
        MockRepo.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_github():
    with patch('github.Github'):
        mock_gh = Mock(spec=Github)
        mock_org = Mock(spec=Organization)
        mock_team = Mock(spec=Team)

        # Setup chain of mock returns
        mock_gh.get_organization.return_value = mock_org
        mock_org.get_team_by_slug.return_value = mock_team
        mock_team.get_teams.return_value = []

        yield {"github": mock_gh, "org": mock_org, "team": mock_team}


@pytest.fixture
def sample_config():
    return {"teams": [{"team_name": "team1"}, {"team_name": "team2"}]}


def test_load_yaml_config(tmp_path):
    """Test loading YAML configuration"""
    config_file = tmp_path / "teams.yml"
    test_config = {'teams': [{'team_name': 'test_team'}]}
    with open(config_file, mode='w', encoding="utf-8") as f:
        yaml.dump(test_config, f)

    result = load_yaml_config(config_file)
    assert result == test_config


def test_find_git_root(mock_repo):
    """Test finding Git repository root"""
    result = find_git_root()
    assert result == Path("/fake/repo/path")


def test_find_git_root_error():
    """Test error handling when Git repository is not found"""
    with patch("git.Repo", side_effect=InvalidGitRepositoryError):
        with pytest.raises(InvalidGitRepositoryError):
            find_git_root()


def test_get_existing_team_directories(tmp_path):
    """Test getting existing team directories"""
    # Create test directory structure
    teams_dir = tmp_path / "teams"
    teams_dir.mkdir()
    (teams_dir / "team1").mkdir()
    (teams_dir / "team2").mkdir()

    result = get_existing_team_directories(tmp_path)
    assert set(result) == {"team1", "team2"}


def test_get_configured_teams(tmp_path):
    """Test getting configured teams from YAML"""
    config_file = tmp_path / "teams.yml"
    test_config = {'teams': [{'team_name': 'team1'}, {'team_name': 'team2'}]}
    with open(config_file,mode='w', encoding="utf-8") as f:
        yaml.dump(test_config, f)

    result = get_configured_teams(config_file)
    assert result == ["team1", "team2"]


def test_delete_team_directory(tmp_path):
    """Test deleting team directory"""
    # Setup
    team_dir = tmp_path / "teams" / "test_team"
    team_dir.mkdir(parents=True)

    # Execute
    result = delete_team_directory(tmp_path, "test_team")

    # Assert
    assert result is True
    assert not team_dir.exists()


def test_delete_github_team(mock_github):
    """Test deleting GitHub team"""
    mock_team = mock_github["team"]
    mock_org = mock_github["org"]

    # Setup sub-teams
    sub_team = Mock(spec=Team)
    sub_team.name = "sub_team"
    mock_team.get_teams.return_value = [sub_team]

    result = delete_github_team(mock_org, "test_team")

    assert result is True
    mock_org.get_team_by_slug.assert_called_once_with("test_team")
    sub_team.delete.assert_called_once()
    mock_team.delete.assert_called_once()


def test_commit_changes(mock_repo):
    """Test committing changes"""
    repo_root = Path("/fake/repo/path")
    deleted_teams = ["team1", "team2"]

    commit_changes(repo_root, "Test commit", deleted_teams)

    # Verify git operations
    mock_repo.git.add.assert_has_calls([call(update=True), call(".")])
    mock_repo.index.commit.assert_called_once_with("Test commit")
    mock_repo.remote().push.assert_called_once()


@patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token", "GITHUB_ORGANIZATION": "fake-org"})
@patch("pathlib.Path.exists")
def test_main_workflow(mock_exists, mock_repo, mock_github, tmp_path):
    """Test the main workflow"""
    # Setup mocks
    mock_exists.return_value = True

    # Mock configuration
    config = {"teams": [{"team_name": "team1"}]}
    with patch("builtins.open", create=True) as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = yaml.dump(config)

        # Mock existing teams
        with patch("team_manage_parent_teams.get_existing_team_directories", return_value=["team1", "team2"]):
            # Execute main
            main()

            # Verify GitHub team deletion was attempted
            mock_github["org"].get_team_by_slug.assert_called_with("team2")


def test_main_no_teams_to_remove(mock_repo, mock_github):
    """Test main when no teams need to be removed"""
    with patch("team_manage_parent_teams.get_existing_team_directories", return_value=["team1"]):
        with patch("team_manage_parent_teams.get_configured_teams", return_value=["team1"]):
            main()

            # Verify no GitHub operations were performed
            mock_github["org"].get_team_by_slug.assert_not_called()


def test_error_handling_in_main():
    """Test error handling in main function"""
    with patch("team_manage_parent_teams.find_git_root", side_effect=InvalidGitRepositoryError):
        with pytest.raises(InvalidGitRepositoryError):
            main()
