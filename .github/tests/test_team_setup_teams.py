import os
import sys
from unittest.mock import Mock, patch
from pathlib import Path
import pytest
import yaml
from git.exc import InvalidGitRepositoryError

# Add script directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.team_setup_teams import (
    load_yaml_config,
    create_team_directory,
    IndentDumper,
    find_git_root,
    commit_changes,
    create_github_team,
    create_github_team_hierarchy,
    main,
)


@pytest.fixture
def temp_repo_root(tmp_path):
    """Create a temporary repository root with teams directory"""
    teams_dir = tmp_path / "teams"
    teams_dir.mkdir()
    return tmp_path


@pytest.fixture
def sample_team_config():
    """Create sample team configuration"""
    return {
        "team_name": "test-team",
        "description": "Test Team",
        "project": "Test Project",
        "repository_permissions": {"repo1": "admin", "repo2": "maintain"},
        "default_repositories": ["repo1", "repo2"],
        "members": ["user1", "user2"],
    }


@pytest.fixture
def default_sub_teams():
    """Create sample sub-teams configuration"""
    return [
        {"name": "[team_name]-admins", "description": "[project] Administrators", "repository_permissions": "admin"},
        {
            "name": "[team_name]-maintainers",
            "description": "[project] Maintainers",
            "repository_permissions": "maintain",
        },
    ]


@pytest.fixture
def mock_github_org():
    """Create a mock GitHub organization"""
    mock_org = Mock()
    mock_org.get_team_by_slug = Mock()
    mock_org.create_team = Mock()
    return mock_org


def test_load_yaml_config(temp_repo_root):
    """Test YAML configuration loading"""
    config_path = temp_repo_root / "test_config.yml"
    test_data = {"test": "data"}

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(test_data, f)

    result = load_yaml_config(config_path)
    assert result == test_data


def test_load_yaml_config_file_not_found():
    """Test handling of missing YAML file"""
    with pytest.raises(FileNotFoundError):
        load_yaml_config("nonexistent.yml")


def test_create_team_directory(temp_repo_root, sample_team_config, default_sub_teams):
    """Test team directory and configuration creation"""
    team_name = "test-team"

    config_file = create_team_directory(team_name, sample_team_config, default_sub_teams, temp_repo_root)

    # Verify directory creation
    team_dir = temp_repo_root / "teams" / team_name
    assert team_dir.exists()
    assert config_file.exists()

    # Verify configuration content
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert config["teams"]["team_name"] == team_name
    assert config["teams"]["description"] == sample_team_config["description"]
    assert len(config["teams"]["default_sub_teams"]) == len(default_sub_teams)


def test_create_existing_team_directory(temp_repo_root, sample_team_config, default_sub_teams):
    """Test handling of existing team directory"""
    team_name = "existing-team"
    team_dir = temp_repo_root / "teams" / team_name
    team_dir.mkdir(parents=True)

    config_file = create_team_directory(team_name, sample_team_config, default_sub_teams, temp_repo_root)
    assert config_file.parent == team_dir


@patch("git.Repo")
def test_find_git_root_success(mock_repo):
    """Test successful Git root directory finding"""
    mock_repo.return_value.working_dir = "/fake/repo/path"
    result = find_git_root()
    assert isinstance(result, Path)
    assert str(result) == "/fake/repo/path"


@patch("git.Repo")
def test_find_git_root_failure(mock_repo):
    """Test handling of missing Git repository"""
    mock_repo.side_effect = InvalidGitRepositoryError("No repository found")
    with pytest.raises(InvalidGitRepositoryError):
        find_git_root()


@patch("git.Repo")
def test_commit_changes(mock_repo, temp_repo_root):
    """Test Git commit functionality"""
    mock_index = Mock()
    mock_repo.return_value.index = mock_index
    mock_repo.return_value.remotes = [Mock(name="origin")]

    files = ["file1.yml", "file2.yml"]
    commit_changes(temp_repo_root, files, "Test commit")

    mock_index.add.assert_called_once()
    mock_index.commit.assert_called_once_with("Test commit")


def test_create_github_team(mock_github_org):
    """Test GitHub team creation"""
    mock_github_org.get_team_by_slug.side_effect = Exception("Team not found")

    team_name = "test-team"
    description = "Test Team"

    create_github_team(mock_github_org, team_name, description)

    mock_github_org.create_team.assert_called_once_with(
        name=team_name, description=description, privacy="closed", parent_team_id=None
    )


def test_create_github_team_existing(mock_github_org):
    """Test updating existing GitHub team"""
    mock_team = Mock()
    mock_github_org.get_team_by_slug.return_value = mock_team

    team_name = "test-team"
    description = "Test Team"

    result = create_github_team(mock_github_org, team_name, description)

    mock_team.edit.assert_called_once_with(
        name=team_name, description=description, privacy="closed", parent_team_id=None
    )
    assert result == mock_team


def test_create_github_team_hierarchy_no_parent(mock_github_org):
    """Test creating GitHub team without parent"""
    team_name = "standalone-team"
    description = "Standalone Team"
    
    # Setup mock behavior for team lookup (simulate team doesn't exist)
    mock_github_org.get_team_by_slug.side_effect = Exception("Team not found")
    
    # Setup mock for team creation
    mock_team = Mock(name="created_team")
    mock_github_org.create_team.return_value = mock_team
    
    result = create_github_team_hierarchy(
        mock_github_org,
        team_name,
        description,
        parent_team_name=None,
        visibility="closed"
    )
    
    # Verify direct team creation
    mock_github_org.create_team.assert_called_once_with(
        name=team_name,
        description=description,
        privacy="closed",
        parent_team_id=None
    )
    assert result == mock_team


def test_create_github_team_with_parent_creation_error(mock_github_org):
    """Test handling team creation errors with parent"""
    team_name = "test-team"
    description = "Test Team"
    parent_team = Mock(id=123)
    
    # Setup mock for team lookup failure
    mock_github_org.get_team_by_slug.side_effect = Exception("Team not found")
    
    # Setup mock for team creation to fail first with parent, then succeed without
    mock_github_org.create_team.side_effect = [
        Exception("Error creating team with parent"),  # First call fails
        Mock(name="created_team")  # Second call succeeds
    ]
    
    # Create the team
    create_github_team(mock_github_org, team_name, description, parent_team=parent_team)
    
    # Get the actual calls made to create_team
    actual_calls = mock_github_org.create_team.call_args_list
    
    # Verify both attempts were made
    assert len(actual_calls) == 2
    
    # Verify first call (with parent)
    assert actual_calls[0].kwargs == {
        "name": team_name,
        "description": description,
        "privacy": "closed",
        "parent_team_id": parent_team.id
    }
    
    # Verify second call (without parent)
    assert actual_calls[1].kwargs == {
        "name": team_name,
        "description": description,
        "privacy": "closed"
    }


@patch("scripts.team_setup_teams.find_git_root")
@patch("scripts.team_setup_teams.Github")
def test_main_execution(mock_github, mock_find_git_root, temp_repo_root):
    """Test main function execution"""
    # Setup mocks
    mock_find_git_root.return_value = temp_repo_root
    mock_gh = Mock()
    mock_github.return_value = mock_gh
    mock_org = Mock()
    mock_gh.get_organization.return_value = mock_org

    # Create test config file
    config = {
        "teams": [
            {
                "team_name": "test-team",
                "description": "Test Team",
                "project": "Test Project",
                "repository_permissions": {"repo1": "admin"},
            }
        ],
        "default_sub_teams": [],
    }

    config_path = temp_repo_root / "teams.yml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f)

    # Set environment variables
    os.environ["GITHUB_TOKEN"] = "fake-token"
    os.environ["GITHUB_ORGANIZATION"] = "test-org"

    # Execute main function
    with patch("scripts.team_setup_teams.commit_changes"):
        main()

    # Verify organization was accessed
    mock_gh.get_organization.assert_called_once_with("test-org")


def test_indent_dumper():
    """Test YAML IndentDumper functionality"""
    dumper = IndentDumper(None)
    assert dumper.increase_indent(flow=True) == dumper.increase_indent(flow=True, indentless=False)
