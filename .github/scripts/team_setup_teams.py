import os
from pathlib import Path
import yaml
from github import Github
import git
from git.exc import InvalidGitRepositoryError


def load_yaml_config(file_path):
    """Load YAML configuration file."""
    with open(file_path, mode="r", encoding="utf-8") as file:
        return yaml.safe_load(file)


class IndentDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def create_team_directory(team_name, team_config, default_sub_teams, repo_root):
    """Create directory and team configurationfile for a team."""
    team_dir = repo_root / "teams" / team_name

    # Check if the team directory already exists
    if team_dir.exists():
        print(f"Team directory '{team_name}' already exists, skipping creation.")
    else:
        team_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created team directory: {team_dir}")

    # Check if the team's configuration file already exists
    team_config_file = team_dir / "teams.yml"
    if team_config_file.exists():
        print(f"Team configuration file for '{team_name}' already exists, skipping creation.")
    else:
        # Create team-specific configuration
        default_repos = team_config.get("default_repositories", [])
        team_yaml = {
            "teams": {
                "team_name": team_name,
                "description": team_config["description"],
                "project": team_config["project"],
                "repository_permission": team_config["repository_permissions"],
                "members": team_config.get("members", []),
                "repositories": default_repos,
                "default_sub_teams": [],
            }
        }

        # Add inherited sub-teams
        for sub_team in default_sub_teams:
            sub_team_config = {
                "name": sub_team["name"].replace("[team_name]", team_name),
                "description": sub_team["description"].replace("[project]", team_yaml["teams"]["project"]),
                "members": [],
                "repositories": default_repos.copy(),
                "repository_permissions": sub_team["repository_permissions"],
            }

            team_yaml["teams"]["default_sub_teams"].append(sub_team_config)

        # Write configuration to file
        with open(team_config_file, mode="w", encoding="utf-8") as f:
            yaml.dump(team_yaml, f, sort_keys=False, Dumper=IndentDumper, default_flow_style=False, indent=2)

        print(f"Create team configuration file: {team_config_file}")

    return team_config_file


def find_git_root():
    """Find the Git repository root directory."""
    try:
        repo = git.Repo(os.getcwd(), search_parent_directories=True)
        return Path(repo.working_dir)
    except InvalidGitRepositoryError as exc:
        raise InvalidGitRepositoryError("No Git repository found in current directory or its parents") from exc


def commit_changes(repo_root, files_to_commit, commit_message):
    """Commit changes to the repository."""
    try:
        # Try to get the Git repo from the current path
        repo = git.Repo(repo_root)
        # Convert all paths to be relative to repo root
        relative_files = []
        for file_path in files_to_commit:
            file_path = Path(file_path)
            if not file_path.is_absolute():
                file_path = repo_root / file_path
            try:
                relative_path = file_path.relative_to(repo_root)
                relative_files.append(str(relative_path))
            except ValueError as e:
                print(f"Warning Skipping file {file_path} - {str(e)}")
                continue

        if not relative_files:
            print("No valid files to commit")
            return

        # Add files and commit
        repo.index.add(relative_files)
        repo.index.commit(commit_message)

        # Check if remote exists before pushing
        if "origin" in [remote.name for remote in repo.remotes]:
            repo.remote("origin").push()
            print("Changes committed and pushed to the repository.")
        else:
            print("Changes committed locally. No remote repository found for pushing")
    except Exception as e:
        print(f"Error during commit: {str(e)}")
        raise


def create_github_team(gh_org, team_name, description, visibility="closed", parent_team=None):
    """Create or Update Github team."""
    try:
        team = gh_org.get_team_by_slug(team_name)
        parent_id = parent_team.id if parent_team else None
        team.edit(
            name=team_name,
            description=description,
            privacy=visibility,
            parent_team_id=int(parent_id) if parent_id is not None else None,
        )
        print(f"Team {team_name} already exists and was updated")
    except Exception:
        try:
            parent_id = parent_team.id if parent_team else None
            team = gh_org.create_team(
                name=team_name,
                description=description,
                privacy=visibility,
                parent_team_id=int(parent_id) if parent_id is not None else None,
            )
            print(f"Created team {team_name}")
        except Exception as create_error:
            print(f"Error creating team {team_name}: {str(create_error)}")
            # Attempt to create without parent if that was the issue
            team = gh_org.create_team(name=team_name, description=description, privacy=visibility)
            print(f"Create team {team_name} without parent")
    return team


def create_github_team_hierarchy(gh_org, team_name, description, parent_team_name=None, visibility="closed"):
    """Create or update GitHub team and its parent if necessary."""
    if parent_team_name:
        try:
            parent_team = gh_org.get_team_by_slug(parent_team_name)
            # Create team or update with parent
            team = create_github_team(gh_org, team_name, description, visibility, parent_team)
            print(f"Set {team_name} as child of {parent_team_name}")
        except Exception as e:
            print(f"Error setting parent team: {str(e)}")
            # If there's an error with the parent, create team without parent
            team = create_github_team(gh_org, team_name, description, visibility)
    else:
        team = create_github_team(gh_org, team_name, description, visibility)

    return team


def main():
    try:
        # Find Git repository root
        repo_root = find_git_root()
        print(f"Git repository root: {repo_root}")

        # Initialise Github client
        github_token = os.environ["GITHUB_TOKEN"]
        org_name = os.environ["GITHUB_ORGANIZATION"]

        gh = Github(github_token)
        org = gh.get_organization(org_name)

        # Load configuration
        config_path = repo_root / "teams.yml"
        config = load_yaml_config(config_path)
        default_sub_teams = config["default_sub_teams"]
        teams = config["teams"]

        # Process each team
        files_to_commit = []
        for team_config in teams:
            team_name = team_config["team_name"]
            print(f"\nProcessing Team: {team_name}")
            team_yml_path = create_team_directory(team_name, team_config, default_sub_teams, repo_root)
            files_to_commit.append(str(team_yml_path))

            # Create parent team in Github
            parent_team = create_github_team_hierarchy(org, team_name, team_config["description"], visibility="closed")

            # Create sub-teams and sync their members
            for sub_team in default_sub_teams:
                sub_team_name = sub_team["name"].replace("[team_name]", team_name)
                sub_team_description = sub_team["description"].replace("[project]", team_config["project"])
                create_github_team_hierarchy(
                    org, sub_team_name, sub_team_description, parent_team.name, visibility="closed"
                )

            print(f"Completed Processing team: {team_name}\n")

        # Commt changes to the repository
        commit_changes(repo_root, files_to_commit, "Setup and Update Team configurations")

    except Exception as e:
        print(f"Error in main execution: {str(e)}")
        raise


if __name__ == "__main__":
    main()
