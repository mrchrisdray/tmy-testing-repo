"""Test module for team_manage_parent_teams.py."""

import os
import sys
from pathlib import Path
from typing import Dict, List, Any
from unittest.mock import Mock, patch, mock_open

import git
import pytest
from github import Github, Organization, Team
from git.exc import InvalidGitRepositoryError

# Add script directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.team_manage_parent_teams import (  # pylint: disable=wrong-import-position
    load_yaml_config,
    find_git_root,
    get_existing_team_directories,
    get_configured_teams,
    delete_team_directory,
    delete_github_team,
    commit_changes,
    main,
)

# Test Constants
SAMPLE_CONFIG = """
teams:
    - team_name: team1
    - team_name: team2
"""

# Fixtures
@pytest.fixture
def mock_repo() -> Mock:
    """Create a mock Git repository."""
    mock = Mock(spec=git.Repo)
    mock.working_dir = "/fake/repo/path"
    mock.is_dirty.return_value = True
    
    # Setup index
    mock_index = Mock()
    mock_index.add = Mock()
    mock_index.commit = Mock()
    mock.index = mock_index
    
    # Setup remote
    mock_remote = Mock()
    mock_remote.push = Mock()
    mock.remote = Mock(return_value=mock_remote)
    
    # Make iterable for git operations
    mock.__iter__ = Mock(return_value=iter([]))
    mock.untracked_files = []
    
    return mock

@pytest.fixture
def mock_github() -> Mock:
    """Create a mock GitHub instance.

    Returns:
        Mock: Mocked GitHub object
    """
    return Mock(spec=Github)

@pytest.fixture
def test_config_file(tmp_path: Path) -> Path:
    """Create a temporary test configuration file.

    Args:
        tmp_path: Pytest fixture providing temporary directory

    Returns:
        Path: Path to test configuration file
    """
    config_file = tmp_path / "test_config.yml"
    config_file.write_text(SAMPLE_CONFIG)
    return config_file

@pytest.fixture
def mock_organization() -> Mock:
    """Create a mock GitHub organization.

    Returns:
        Mock: Mocked GitHub organization object
    """
    mock = Mock(spec=Organization)
    mock.get_team.return_value = Mock(spec=Team)
    return mock

# Test Classes
class TestGitOperations:
    """Tests for Git-related operations."""

    def test_find_git_root(self, mock_repo: Mock) -> None:
        """Test finding Git repository root."""
        with patch("git.Repo", return_value=mock_repo):
            result = find_git_root()
            assert result == Path("/fake/repo/path")

    def test_commit_changes(self, mock_repo: Mock) -> None:
        """Test committing changes to repository."""
        with patch("git.Repo", return_value=mock_repo):
            commit_changes(Path("/fake/path"), "Test commit", ["team1"])
            
            # Verify git operations
            mock_repo.index.add.assert_called_once()
            mock_repo.index.commit.assert_called_once_with("Test commit")
            mock_repo.remote.return_value.push.assert_called_once()

class TestTeamOperations:
    """Tests for team-related operations."""

    @pytest.mark.parametrize(
        "team_name,exists,expected",
        [
            ("team1", True, True),
            ("nonexistent", False, False),
        ],
    )
    def test_delete_team_directory(
        self, tmp_path: Path, team_name: str, exists: bool, expected: bool
    ) -> None:
        """Test team directory deletion scenarios."""
        if exists:
            team_dir = tmp_path / "teams" / team_name
            team_dir.mkdir(parents=True)

        result = delete_team_directory(tmp_path, team_name)
        assert result == expected

    def test_get_configured_teams(self, test_config_file: Path) -> None:
        """Test getting configured teams from config file."""
        teams = get_configured_teams(test_config_file)
        assert teams == ["team1", "team2"]

if __name__ == "__main__":
    pytest.main([__file__])