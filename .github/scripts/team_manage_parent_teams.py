import os
from pathlib import Path
import shutil
import yaml
from github import Github
import git
from git.exc import InvalidGitRepositoryError


def load_yaml_config(file_path):
    """Load YAML configuration file."""
    with open(file_path, mode="r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def find_git_root():
    """Find the Git repository root directory."""
    try:
        repo = git.Repo(os.getcwd(), search_parent_directories=True)
        return Path(repo.working_dir)
    except InvalidGitRepositoryError as exc:
        raise InvalidGitRepositoryError("No Git repository found in current directory or it parents") from exc


def get_existing_team_directories(repo_root):
    """Get list of existing team directories."""
    teams_dir = repo_root / "teams"
    if not teams_dir.exists():
        return []
    return [d.name for d in teams_dir.iterdir() if d.is_dir()]


def get_configured_teams(config_file):
    """Get list of teams from configuration file."""
    config = load_yaml_config(config_file)
    return [team["team_name"] for team in config.get("teams", [])]


def delete_team_directory(repo_root, team_name):
    """Delete team directory and it configuration file."""
    team_dir = repo_root / "teams" / team_name
    if team_dir.exists():
        try:
            shutil.rmtree(team_dir)
            print(f"Deleted team directory {team_dir}")
            return True
        except Exception as e:
            print(f"Error deleting team directory {team_dir}: {str(e)}")
            return False
    return False


def delete_github_team(gh_org, team_name):
    """Delete GitHub team and its sub-teams."""
    try:
        team = gh_org.get_team_by_slug(team_name)

        # First, delete all sub-teams
        sub_teams = team.get_teams()
        for sub_team in sub_teams:
            try:
                sub_team.delete()
                print(f"Deleted sub-team: {sub_team.name}")
            except Exception as e:
                print(f"Error deleting sub-team {sub_team.name}: {str(e)}")

        # Delete the parent team
        team.delete()
        print(f"Deleted parent team: {team_name}")
        return True
    except Exception as e:
        print(f"Error deleting GitHub team {team_name}: {str(e)}")
        return False


def commit_changes(repo_root, commit_message, deleted_teams):
    """Commit changes to the repository."""
    try:
        repo = git.Repo(repo_root)

        # Added all changes including deletions
        repo.git.add(update=True)
        repo.git.add(".")

        # Explicitly remove deleted team directories
        for team in deleted_teams:
            team_path = repo_root / "teams" / team
            if team_path.exists():
                repo.git.rm("-r", str(team_path))

        # Only commit if there are changes
        if repo.is_dirty() or len(repo.untracked_files) > 0:
            repo.index.commit(commit_message)

            # Push if remote exists
            if "origin" in [remote.name for remote in repo.remotes]:
                repo.remote("origin").push()
                print("Changes committed and pushed to the repository.")
            else:
                print("Changes committed locally. No remote repository found for pushing.")
        else:
            print("No changes to commit.")

    except Exception as e:
        print(f"Error during commit: {str(e)}")
        raise


def main():
    try:
        # Find Git repository root
        repo_root = find_git_root()
        print(f"Git repository root: {repo_root}")

        # Initialize GitHub client
        github_token = os.environ["GITHUB_TOKEN"]
        org_name = os.environ["GITHUB_ORGANIZATION"]

        gh = Github(github_token)
        org = gh.get_organization(org_name)

        # Load root configuration
        config_path = repo_root / "teams.yml"

        # Get existing teams from directories and configuration
        existing_teams = get_existing_team_directories(repo_root)
        configured_teams = get_configured_teams(config_path)

        # Find teams that exist but are not in configuration
        teams_to_remove = set(existing_teams) - set(configured_teams)

        if not teams_to_remove:
            print("No teams to remove.")
            return
        print(f"Teams to remove: {teams_to_remove}")

        # Process each team to remove
        deleted_teams = []
        for team_name in teams_to_remove:
            print(f"\nProcessing removal of teams: {team_name}")

            # Delete GitHub team and its sub-teams
            if delete_github_team(org, team_name):
                # If GitHub deletion successfully, delete local directory
                if delete_team_directory(repo_root, team_name):
                    deleted_teams.append(team_name)

        if deleted_teams:
            # Commit changes to the repository
            commit_message = f"Remove teams: {','.join(deleted_teams)}"
            commit_changes(repo_root, commit_message, deleted_teams)
            print(f"\nSuccessfully removed teams: {deleted_teams}")
        else:
            print("\nNo teams were successfully removed.")

    except Exception as e:
        print(f"Error in main execution: {str(e)}")
        raise


if __name__ == "__main__":
    main()
