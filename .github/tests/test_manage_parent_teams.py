"""Test module for team_manage_parent_teams.py."""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import git
import pytest

# Add script directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.team_manage_parent_teams import (  # pylint: disable=wrong-import-position
    find_git_root,
    get_configured_teams,
    delete_team_directory,
    commit_changes,
)

# Test Constants
SAMPLE_CONFIG = """
teams:
    - team_name: team1
    - team_name: team2
"""


# Fixtures
@pytest.fixture
def mock_repo():
    """Create a mock Git repository configuration."""
    mock = MagicMock(spec=git.Repo)

    # Setup basic attributes
    mock.working_dir = "/fake/repo/path"
    mock.is_dirty.return_value = True
    mock.untracked_files = []

    # Setup git command interface
    mock.git = MagicMock()
    mock.git.add = MagicMock()
    mock.git.rm = MagicMock()

    # Setup index
    mock.index = MagicMock()
    mock.index.add = MagicMock()
    mock.index.commit = MagicMock()

    # Setup remotes
    mock_origin = MagicMock()
    mock_origin.push = MagicMock()
    mock.remotes = MagicMock()
    mock.remotes.origin = mock_origin

    return mock


class TestGitOperations:
    @patch("git.Repo")
    def test_find_git_root(self, mock_git_repo, mock_repo):
        """Test finding Git repository root."""
        mock_git_repo.return_value = mock_repo
        result = find_git_root()
        assert isinstance(result, Path)
        assert str(result) == "/fake/repo/path"

    def test_get_configured_teams(self, tmp_path):
        """Test getting configured teams from YAML."""
        config_file = tmp_path / "teams.yml"
        config_file.write_text(SAMPLE_CONFIG)
        teams = get_configured_teams(config_file)
        assert teams == ["team1", "team2"]

    def test_delete_team_directory(self, tmp_path):
        """Test team directory deletion."""
        team_dir = tmp_path / "teams" / "test_team"
        team_dir.mkdir(parents=True)
        assert delete_team_directory(tmp_path, "test_team")
        assert not team_dir.exists()

    @patch("git.Repo")
    def test_commit_changes(self, mock_git_repo, mock_repo):
        """Test committing changes."""
        mock_git_repo.return_value = mock_repo
        repo_root = Path("/fake/repo/path")
        deleted_teams = ["team1"]
        commit_message = "Test commit"

        commit_changes(repo_root, commit_message, deleted_teams)

        # Verify interactions
        mock_repo.git.add.assert_called_with(update=True)
        mock_repo.git.add.assert_any_call(".")
        mock_repo.index.commit.assert_called_once_with(commit_message)
        mock_repo.remote("origin").push.assert_called_once()
