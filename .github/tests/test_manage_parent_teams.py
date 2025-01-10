import pytest
from unittest.mock import Mock, patch, mock_open
from pathlib import Path
import git
from github import Github, Organization, Team
from git.exc import InvalidGitRepositoryError

# Import the functions to test
from your_script import (
    load_yaml_config,
    find_git_root,
    get_existing_team_directories,
    get_configured_teams,
    delete_team_directory,
    delete_github_team,
    commit_changes,
    main
)

# Sample test data
SAMPLE_CONFIG = """
teams:
  - team_name: team1
  - team_name: team2
"""

@pytest.fixture
def mock_repo():
    """Fixture for mocking Git repository"""
    mock = Mock(spec=git.Repo)
    mock.working_dir = "/fake/repo/path"
    mock.is_dirty.return_value = True
    mock.untracked_files = []
    mock.remotes = [Mock(name="origin")]
    return mock

@pytest.fixture
def mock_github():
    """Fixture for mocking GitHub API"""
    mock = Mock(spec=Github)
    mock_org = Mock(spec=Organization.Organization)
    mock_team = Mock(spec=Team.Team)
    mock_sub_team = Mock(spec=Team.Team)
    
    # Setup the mock chain
    mock.get_organization.return_value = mock_org
    mock_org.get_team_by_slug.return_value = mock_team
    mock_team.get_teams.return_value = [mock_sub_team]
    
    return mock, mock_org, mock_team, mock_sub_team

def test_load_yaml_config():
    """Test loading YAML configuration"""
    with patch('builtins.open', mock_open(read_data=SAMPLE_CONFIG)):
        config = load_yaml_config('dummy_path')
        assert 'teams' in config
        assert len(config['teams']) == 2
        assert config['teams'][0]['team_name'] == 'team1'

def test_find_git_root_success(mock_repo):
    """Test finding Git root directory - success case"""
    with patch('git.Repo', return_value=mock_repo):
        root = find_git_root()
        assert str(root) == "/fake/repo/path"

def test_find_git_root_failure():
    """Test finding Git root directory - failure case"""
    with patch('git.Repo', side_effect=InvalidGitRepositoryError):
        with pytest.raises(InvalidGitRepositoryError):
            find_git_root()

def test_get_existing_team_directories(tmp_path):
    """Test getting existing team directories"""
    # Create test directory structure
    teams_dir = tmp_path / "teams"
    teams_dir.mkdir()
    (teams_dir / "team1").mkdir()
    (teams_dir / "team2").mkdir()
    
    with patch('pathlib.Path.exists', return_value=True):
        result = get_existing_team_directories(tmp_path)
        assert sorted(result) == ["team1", "team2"]

def test_get_configured_teams():
    """Test getting configured teams from config file"""
    with patch('builtins.open', mock_open(read_data=SAMPLE_CONFIG)):
        teams = get_configured_teams('dummy_path')
        assert teams == ["team1", "team2"]

def test_delete_team_directory(tmp_path):
    """Test deleting team directory"""
    # Setup test directory
    team_dir = tmp_path / "teams" / "team1"
    team_dir.mkdir(parents=True)
    
    result = delete_team_directory(tmp_path, "team1")
    assert result is True
    assert not team_dir.exists()

def test_delete_github_team(mock_github):
    """Test deleting GitHub team"""
    mock_gh, mock_org, mock_team, mock_sub_team = mock_github
    
    result = delete_github_team(mock_org, "team1")
    assert result is True
    mock_sub_team.delete.assert_called_once()
    mock_team.delete.assert_called_once()

@patch('os.environ', {'GITHUB_TOKEN': 'fake-token', 'GITHUB_ORGANIZATION': 'fake-org'})
@patch('git.Repo')
@patch('github.Github')
def test_main_success(mock_github_class, mock_repo_class, mock_repo, tmp_path):
    """Test main function - successful execution"""
    # Setup mocks
    mock_github_class.return_value = Mock()
    mock_repo_class.return_value = mock_repo
    
    # Create test directory structure
    teams_dir = tmp_path / "teams"
    teams_dir.mkdir()
    (teams_dir / "team3").mkdir()  # Team to be removed
    
    # Create test config
    config = """
    teams:
      - team_name: team1
      - team_name: team2
    """
    
    with patch('builtins.open', mock_open(read_data=config)):
        with patch('pathlib.Path.exists', return_value=True):
            main()
            
            # Verify commit was made
            mock_repo.index.commit.assert_called_once()
            mock_repo.remote().push.assert_called_once()

def test_commit_changes(mock_repo):
    """Test committing changes"""
    deleted_teams = ["team1"]
    commit_message = "Remove teams: team1"
    
    commit_changes(Path("/fake/repo/path"), commit_message, deleted_teams)
    
    # Verify Git operations were called
    mock_repo.git.add.assert_called()
    mock_repo.index.commit.assert_called_with(commit_message)
    mock_repo.remote().push.assert_called_once()

if __name__ == "__main__":
    pytest.main(["-v"])