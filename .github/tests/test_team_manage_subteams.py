import os
import sys
from unittest.mock import MagicMock, patch, mock_open
import yaml
from github import GithubException
import pytest

# Add script directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.team_manage_subteams import (
    get_modified_team_files, 
    load_team_config, 
    get_existing_subteams,
    create_subteam,
    delete_subteam,
    sync_subteams,
    main
)

@pytest.fixture
def mock_github():
    """Create a mock GitHub instance"""
    with patch('scripts.team_manage_subteams.Github') as mock_gh:
        mock_org = MagicMock()
        mock_gh.return_value.get_organization.return_value = mock_org
        yield mock_gh, mock_org

@pytest.fixture
def mock_logger():
    """Create a mock logger"""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    return logger

@pytest.fixture
def sample_team_config():
    """Create a sample team configuration"""
    return {
        "teams": {
            "team_name": "parent-team",
            "default_sub_teams": [
                {
                    "name": "sub-team-1",
                    "description": "First sub team"
                },
                {
                    "name": "sub-team-2", 
                    "description": "Second sub team"
                }
            ]
        }
    }

def test_get_modified_team_files_success(mock_github):
    """Test getting modified team files with a successful scenario"""
    mock_gh, _ = mock_github
    mock_repo = MagicMock()
    
    # Create mock comparison with modified files
    mock_comparison = MagicMock()
    mock_file = MagicMock()
    mock_file.filename = "teams/test-team/teams.yml"
    mock_comparison.files = [mock_file]
    mock_repo.compare.return_value = mock_comparison

    # Mock get_all_team_files to return a list that includes the modified file
    with patch('scripts.team_manage_subteams.get_all_team_files', 
               return_value=["teams/test-team/teams.yml"]):
        modified_files = get_modified_team_files(mock_repo, "base_sha", "head_sha")

    # Verify
    assert len(modified_files) == 1
    assert modified_files[0] == "teams/test-team/teams.yml"
    mock_repo.compare.assert_called_once_with("base_sha", "head_sha")

def test_get_modified_team_files_github_error(mock_github):
    """Test handling of GitHub API errors when getting modified files"""
    mock_gh, _ = mock_github
    mock_repo = MagicMock()
    mock_repo.compare.side_effect = GithubException(500, "API Error")

    # Mock get_all_team_files to return a list of team files
    with patch('scripts.team_manage_subteams.get_all_team_files', 
               return_value=["teams/test-team/teams.yml"]):
        result = get_modified_team_files(mock_repo, "base_sha", "head_sha")

    # Verify fallback to all team files
    assert len(result) == 1
    assert result[0] == "teams/test-team/teams.yml"

def test_load_team_config():
    """Test loading team configuration from a YAML file"""
    sample_config = {
        "teams": {
            "team_name": "test-team",
            "default_sub_teams": [{"name": "sub-team", "description": "Test sub-team"}]
        }
    }

    # Mock file open and yaml load
    with patch('builtins.open', mock_open(read_data=yaml.safe_dump(sample_config))) as mock_file:
        config = load_team_config("path/to/teams.yml")
        
        # Verify config is loaded correctly
        assert config == sample_config
        mock_file.assert_called_once_with("path/to/teams.yml", mode="r", encoding="utf-8")

def test_load_team_config_invalid_yaml():
    """Test handling of invalid YAML configuration"""
    with patch('builtins.open', mock_open(read_data="invalid: yaml: config")):
        with pytest.raises(ValueError, match="Failed to parse YAML"):
            load_team_config("path/to/teams.yml")

def test_get_existing_subteams(mock_github):
    """Test retrieving existing sub-teams"""
    mock_gh, mock_org = mock_github
    
    # Create mock parent team and sub-teams
    mock_parent_team = MagicMock()
    mock_org.get_team_by_slug.return_value = mock_parent_team
    
    mock_sub_team1 = MagicMock()
    mock_sub_team1.name = "existing-sub-team-1"
    mock_sub_team2 = MagicMock()
    mock_sub_team2.name = "existing-sub-team-2"
    mock_parent_team.get_teams.return_value = [mock_sub_team1, mock_sub_team2]

    # Test get_existing_subteams
    existing_subteams = get_existing_subteams(mock_org, "parent-team")
    
    # Verify
    assert existing_subteams == {"existing-sub-team-1", "existing-sub-team-2"}
    mock_org.get_team_by_slug.assert_called_once_with("parent-team")

def test_create_subteam(mock_github, mock_logger, sample_team_config):
    """Test creating a new sub-team"""
    mock_gh, mock_org = mock_github
    
    # Create mock parent team
    mock_parent_team = MagicMock()
    mock_parent_team.id = 123
    mock_org.get_team_by_slug.return_value = mock_parent_team

    # Test create_subteam
    sub_team_config = sample_team_config["teams"]["default_sub_teams"][0]
    create_subteam(mock_org, "parent-team", sub_team_config, mock_logger)

    # Verify
    mock_org.create_team.assert_called_once_with(
        name="sub-team-1", 
        description="First sub team", 
        privacy="closed", 
        parent_team_id=123
    )
    mock_logger.info.assert_called_once_with("Created new sub-team: sub-team-1 under parent-team")

def test_delete_subteam(mock_github, mock_logger):
    """Test deleting a sub-team"""
    mock_gh, mock_org = mock_github
    
    # Create mock team to delete
    mock_team = MagicMock()
    mock_org.get_team_by_slug.return_value = mock_team

    # Test delete_subteam
    delete_subteam(mock_org, "team-to-delete", mock_logger)

    # Verify
    mock_team.delete.assert_called_once()
    mock_logger.info.assert_called_once_with("Delete sub_team: team-to-delete")

def test_sync_subteams(mock_github, mock_logger, sample_team_config):
    """Test synchronizing sub-teams"""
    mock_gh, mock_org = mock_github
    
    # Mock existing and desired sub-teams
    mock_parent_team = MagicMock()
    mock_parent_team.id = 123
    mock_org.get_team_by_slug.return_value = mock_parent_team

    # Existing sub-teams
    mock_existing_team1 = MagicMock()
    mock_existing_team1.name = "existing-team"
    mock_parent_team.get_teams.return_value = [mock_existing_team1]

    # Test sync_subteams
    with patch('scripts.team_manage_subteams.create_subteam') as mock_create, \
         patch('scripts.team_manage_subteams.delete_subteam') as mock_delete:
        sync_subteams(mock_org, sample_team_config, mock_logger)

        # Verify create and delete calls
        assert mock_create.call_count == 2
        assert mock_delete.call_count == 1
        mock_delete.assert_called_with(mock_org, "existing-team", mock_logger)

def test_main_push_event(monkeypatch, mock_github, mock_logger):
    """Test main function for push event"""
    # Set up environment variables
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_ORGANIZATION", "test-org")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_EVENT_BEFORE", "base_sha")
    monkeypatch.setenv("GITHUB_SHA", "head_sha")
    monkeypatch.setenv("GITHUB_REPOSITORY", "test/repo")

    # Mock dependencies
    mock_gh, mock_org = mock_github
    mock_repo = MagicMock()
    mock_gh.return_value.get_repo.return_value = mock_repo

    # Mock team files and config
    with patch('scripts.team_manage_subteams.get_modified_team_files', 
               return_value=["teams/test-team/teams.yml"]), \
         patch('scripts.team_manage_subteams.load_team_config', 
               return_value={"teams": {"team_name": "test-team"}}), \
         patch('scripts.team_manage_subteams.sync_subteams'):
        
        result = main()
        assert result == 0