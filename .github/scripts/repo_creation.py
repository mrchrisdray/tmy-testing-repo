import os
import re
import yaml
import sys
from github import Github


class RepositoryCreationHandler:
    def __init__(self, github_token, org_name):
        """
        Initialize the Repository Creation Handler

        :param github_token: GitHub Personal Access Token
        :param org_name: GitHub Organization Name
        """
        self.g = Github(github_token)
        self.org = self.g.get_organization(org_name)

    def validate_repository_name(self, name):
        """
        Validate repository name according to GitHub guidelines

        :param name: Proposed repository name
        :return: Tuple (is_valid, error_message)
        """
        # GitHub repository name rules
        if not name:
            return False, "Repository name cannot be empty"

        # Check length
        if len(name) < 1 or len(name) > 100:
            return False, "Repository name must be between 1 and 100 characters"

        # Check for valid characters
        if not re.match(r"^[a-z0-9_.-]+$", name, re.IGNORECASE):
            return False, "Repository name can only contain alphanumeric characters, periods, hyphens, and underscores"

        return True, None

    def validate_description(self, description):
        """
        Validate repository description

        :param description: Proposed repository description
        :return: Tuple (is_valid, error_message)
        """
        if description and len(description) > 280:
            return False, "Description must be 280 characters or less"

        return True, None

    def generate_repository_config(self, input_data):
        """
        Generate a standardized repository configuration

        :param input_data: Dictionary of repository creation inputs
        :return: Validated YAML configuration
        """
        # Basic repository configuration
        config = {
            "metadata": {
                "name": input_data["name"],
                "description": input_data.get("description", ""),
                "private": input_data.get("visibility", True),
            },
            "branch_protection": {
                "enforce_admins": True,
                "required_status_checks": ["continuous-integration/github-actions"],
                "required_pull_request_reviews": {"required_approving_review_count": 1},
            },
        }

        # Add optional collaborators
        if input_data.get("collaborators"):
            config["collaborators"] = input_data["collaborators"]

        # Add optional teams
        if input_data.get("teams"):
            config["teams"] = input_data["teams"]

        return config

    def create_repository(self, config):
        """
        Create repository based on configuration

        :param config: Repository configuration dictionary
        :return: Created repository object or None
        """
        try:
            # Extract metadata
            metadata = config.get("metadata", {})

            # Create repository
            repo = self.org.create_repo(
                name=metadata.get("name"),
                description=metadata.get("description", ""),
                private=metadata.get("private", True),
                auto_init=True,
            )

            # Create configuration file
            config_content = yaml.dump(config, default_flow_style=False)
            repo.create_file(
                path=f'repositories/{metadata.get("name")}.yml',
                message="Initial repository configuration",
                content=config_content.encode("utf-8"),
            )

            return repo

        except Exception as e:
            print(f"Error creating repository: {e}")
            return None

    def generate_issue_comment(self, validation_results):
        """
        Generate a detailed comment for issue feedback

        :param validation_results: Dictionary of validation results
        :return: Formatted markdown comment
        """
        comment = "## 📋 Repository Creation Validation Report\n\n"

        # Validation Status
        if all(validation_results.values()):
            comment += "✅ **All inputs passed validation!**\n\n"
        else:
            comment += "⚠️ **Some inputs require attention**\n\n"

        # Detailed validation results
        comment += "### Validation Details:\n"

        for key, (is_valid, message) in validation_results.items():
            if is_valid:
                comment += f"- ✅ **{key.capitalize()}**: Passed validation\n"
            else:
                comment += f"- ❌ **{key.capitalize()}**: {message}\n"

        # Suggestions section
        comment += "\n### Suggested Next Steps:\n"
        comment += "- Review and correct any flagged items\n"
        comment += "- Reopen the issue with corrected information\n"
        comment += "- Contact organization administrators if you need assistance\n"

        return comment


def handle_repository_creation_issue(issue, github_token, org_name):
    """
    Main handler for repository creation issues

    :param issue: GitHub Issue object
    :param github_token: GitHub Personal Access Token
    :param org_name: GitHub Organization Name
    """
    handler = RepositoryCreationHandler(github_token, org_name)

    # Extract issue body and parse input (this would be more robust with a structured issue template)
    issue_body = issue.body

    # Example: Simple parsing (real implementation would use a more robust parser)
    input_data = {}
    for line in issue_body.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            input_data[key.strip().lower()] = value.strip()

    # Validate inputs
    validation_results = {
        "name": handler.validate_repository_name(input_data.get("name", "")),
        "description": handler.validate_description(input_data.get("description", "")),
    }

    # Check if all validations passed
    if all(result[0] for result in validation_results.values()):
        # Generate configuration
        config = handler.generate_repository_config(input_data)

        # Create repository
        repo = handler.create_repository(config)

        if repo:
            # Comment with success message
            success_comment = f"""
## 🎉 Repository Created Successfully!

Repository **{repo.full_name}** has been created with the following configuration:

- **Name**: {repo.name}
- **Description**: {repo.description}
- **Visibility**: {'Private' if repo.private else 'Public'}

Configuration file has been generated at `.github/repo_settings.yml`

[View Repository](${repo.html_url})
"""
            issue.create_comment(success_comment)
            issue.edit(state="closed")
        else:
            # Repository creation failed
            issue.create_comment("❌ **Repository Creation Failed**\nPlease contact an administrator.")
    else:
        # Generate detailed validation feedback
        feedback_comment = handler.generate_issue_comment(validation_results)
        issue.create_comment(feedback_comment)


def main():
    # Typically set via environment variables or GitHub Actions context
    github_token = os.environ.get("GITHUB_TOKEN")
    org_name = os.environ.get("GITHUB_ORGANIZATION")
    issue_number = os.environ.get("ISSUE_NUMBER")

    if not all([github_token, org_name, issue_number]):
        print("Missing required environment variables")
        sys.exit(1)

    # Initialize GitHub instance
    g = Github(github_token)
    org = g.get_organization(org_name)

    # Get the specific issue
    issue = org.get_repo(org_name + "/" + org_name + ".github").get_issue(int(issue_number))

    # Handle repository creation
    handle_repository_creation_issue(issue, github_token, org_name)


if __name__ == "__main__":
    main()
