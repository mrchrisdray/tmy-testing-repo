import os
import sys
import yaml
import pytest

# Add script directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.team_setup_teams import load_yaml_config, create_team_directory, IndentDumper


@pytest.fixture
def temp_repo_root(tmp_path):
    teams_dir = tmp_path / "teams"
    teams_dir.mkdir()
    return tmp_path


@pytest.fixture
def sample_team_config():
    return {
        "description": "Test Team",
        "project": "Test Project",
        "default_repositories": ["repo1", "repo2"],
        "repository_permissions": {"repo1": "admin", "repo2": "maintain"},
    }


@pytest.fixture
def default_sub_teams():
    return ["subteam1", "subteam2"]


def test_load_yaml_config(temp_repo_root):
    config_path = temp_repo_root / "test_config.yml"
    test_data = {"test": "data"}
    with open(config_path, mode="w", encoding="utf-8") as f:
        yaml.dump(test_data, f)

    result = load_yaml_config(config_path)
    assert result == test_data


def test_create_team_directory(temp_repo_root, sample_team_config):
    team_name = "test-team"
    result = create_team_directory(repo_root=temp_repo_root, team_name=team_name, team_config=sample_team_config)
    assert result is True
    team_dir = temp_repo_root / "teams" / team_name
    assert team_dir.exists()


def test_create_existing_team_directory(temp_repo_root, sample_team_config):
    """Test handling existing team directory"""
    team_name = "existing-team"
    team_dir = temp_repo_root / "teams" / team_name
    team_dir.mkdir(parents=True)
    result = create_team_directory(repo_root=temp_repo_root, team_name=team_name, team_config=sample_team_config)
    assert result is False


def test_indent_dumper():
    dumper = IndentDumper(None)
    assert dumper.increase_indent(flow=True) == dumper.increase_indent(flow=True, indentless=False)
