import pytest
from unittest.mock import patch, MagicMock
import os
from pathlib import Path
import shutil
import yaml
import git
from git.exc import InvalidGitRepositoryError
from team_manage_parent_teams import (
    load_yaml_config,
    find_git_root,
    get_existing_team_directories,
    get_configured_teams,
    delete_team_directory
)

@pytest.fixture
def test_dir():
    test_dir = Path("test_workspace")
    test_dir.mkdir(exist_ok=True)
    yield test_dir
    if test_dir.exists():
        shutil.rmtree(test_dir)

def test_load_yaml_config(test_dir):
    test_config = {
        "teams": [
            {"team_name": "team1", "description": "Test Team 1"},
            {"team_name": "team2", "description": "Test Team 2"}
        ]
    }
    config_path = test_dir / "test_config.yml"
    with open(config_path, "w") as f:
        yaml.dump(test_config, f)
        
    result = load_yaml_config(config_path)
    assert result == test_config

@patch('git.Repo')
def test_find_git_root(mock_repo, test_dir):
    mock_repo.return_value.working_dir = str(test_dir)
    result = find_git_root()
    assert result == test_dir

@patch('git.Repo')
def test_find_git_root_error(mock_repo):
    mock_repo.side_effect = InvalidGitRepositoryError()
    with pytest.raises(InvalidGitRepositoryError):
        find_git_root()

def test_get_existing_team_directories(test_dir):
    teams_dir = test_dir / "teams"
    teams_dir.mkdir(parents=True)
    (teams_dir / "team1").mkdir()
    (teams_dir / "team2").mkdir()
    
    result = get_existing_team_directories(test_dir)
    assert sorted(result) == ["team1", "team2"]

def test_get_configured_teams(test_dir):
    config = {
        "teams": [
            {"team_name": "team1"},
            {"team_name": "team2"}
        ]
    }
    config_path = test_dir / "teams.yml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)
        
    result = get_configured_teams(config_path)
    assert result == ["team1", "team2"]

def test_delete_team_directory(test_dir):
    team_dir = test_dir / "teams" / "test_team"
    team_dir.mkdir(parents=True)
    (team_dir / "teams.yml").touch()
    
    delete_team_directory(test_dir, "test_team")
    assert not team_dir.exists()