import os
import sys
import re
import json
import logging
from github import Github, GithubException

# Import the config generation functions
from repo_config_generator import generate_repository_config, save_repository_config


# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("repo_creation_debug.log")],
)

from github import Github, GithubException


def get_github_context():
    """
    Retrieve GitHub context from environment variables and event payload
    """
    # Get environment variables
    github_token = os.environ.get("GITHUB_TOKEN")
    github_event_path = os.environ.get("GITHUB_EVENT_PATH")

    logging.debug(f"GITHUB_TOKEN present: {bool(github_token)}")
    logging.debug(f"GITHUB_EVENT_PATH: {github_event_path}")

    # Parse GitHub event payload
    event_payload = {}
    if github_event_path and os.path.exists(github_event_path):
        try:
            with open(github_event_path, "r") as event_file:
                event_payload = json.load(event_file)
            logging.debug("Event payload successfully parsed")
        except Exception as e:
            logging.error(f"Error parsing event payload: {e}")

    # Extract context information
    context = {
        "token": github_token,
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "event_name": os.environ.get("GITHUB_EVENT_NAME", ""),
        "ref": os.environ.get("GITHUB_REF", ""),
        "actor": os.environ.get("GITHUB_ACTOR", ""),
        "issue_number": None,
        "organization": None,
    }

    # Extract issue number from payload or environment
    if "issue" in event_payload:
        context["issue_number"] = event_payload["issue"].get("number")

    # Extract organization from repository name
    if context["repository"]:
        context["organization"] = context["repository"].split("/")[0]

    # Logging all extracted context
    logging.debug("GitHub Context:")
    for key, value in context.items():
        logging.debug(f"{key}: {value}")

    return context, event_payload


class RepositoryCreationHandler:
    def __init__(self, github_token, org_name):
        self.g = Github(github_token)
        self.org = self.g.get_organization(org_name)
        self.org_name = org_name

    def validate_repository_name(self, name):
        """
        Validate repository name according to GitHub naming conventions
        
        :param name: Repository name to validate
        :return: tuple(bool, str) - (is_valid, message)
        """
        if not name:
            return False, "Repository name cannot be empty"
        
        # GitHub repository naming rules
        if len(name) > 100:
            return False, "Repository name must be 100 characters or less"
            
        # Check for valid characters (letters, numbers, hyphens, underscores)
        if not re.match(r'^[a-zA-Z0-9._-]+$', name):
            return False, "Repository name can only contain letters, numbers, hyphens, and underscores"
            
        # Check if repository already exists
        try:
            self.org.get_repo(name)
            return False, f"Repository '{name}' already exists in the organization"
        except GithubException:
            pass
            
        return True, "Repository name is valid"

    def validate_description(self, description):
        """
        Validate repository description
        
        :param description: Repository description to validate
        :return: tuple(bool, str) - (is_valid, message)
        """
        if not description:
            return False, "Description cannot be empty"
            
        if len(description) > 350:  # GitHub's description length limit
            return False, "Description must be 350 characters or less"
            
        return True, "Description is valid"

    def validate_visibility(self, visibility):
        """
        Validate repository visibility setting
        
        :param visibility: Desired visibility setting
        :return: tuple(bool, str) - (is_valid, message)
        """
        valid_values = ['private', 'internal']
        if not visibility.lower() in valid_values:
            return False, "Visibility must be either 'private' or 'internal'"
        return True, "Visibility setting is valid"


    def parse_issue_body(self, body):
        """
        Parse issue body into input dictionary with required and optional fields
        """
        input_data = {"required": {}, "optional": {}, "branch_protection": []}

        lines = body.split("\n")
        current_section = None
        current_data = []

        for line in lines:
            line = line.strip()

            # Skip empty lines and markdown section
            if not line or line.startswith("##"):
                continue

            # Handle section headers (identified by form field labels)
            if line.endswith(":") or line.endswith(" (Optional):"):
                if current_section and current_data:
                    self._process_section(current_section, current_data, input_data)
                current_section = line.replace(":", "").replace(" (Optional)", "").lower()
                current_data = []
                continue

            # Collect checkbox selections for branch protection
            if line.startswith("- [x]"):
                if current_section == "branch protection settings":
                    input_data["branch_protection"].append(line[5:].strip())
            # Collect regular input data
            elif line and not line.startswith("-"):
                current_data.append(line)

        # Process the last section
        if current_section and current_data:
            self._process_section(current_section, current_data, input_data)

        return input_data

    def _process_section(self, section, data, input_data):
        """Helper method to process each section of the issue form"""
        clean_data = [line for line in data if line and not line.startswith(">")]
        if not clean_data:
            return

        value = "\n".join(clean_data) if len(clean_data) > 1 else clean_data[0]

        # Map sections to required or optional fields
        required_fields = {
            "repository name": "repo_name",
            "repository description": "description",
            "repository visibility": "visibility",
        }

        optional_fields = {"teams": "teams", "additional notes": "notes"}

        section = section.lower()
        if section in required_fields:
            input_data["required"][required_fields[section]] = value
        elif section in optional_fields:
            input_data["optional"][optional_fields[section]] = value

    def validate_input(self, input_data):
        """
        Validate all required inputs and return validation results
        """
        validation_results = {}

        # Validate required fields
        required_fields = {
            "repo_name": self.validate_repository_name,
            "description": self.validate_description,
            "visibility": self.validate_visibility,
        }

        for field, validator in required_fields.items():
            if field not in input_data["required"]:
                validation_results[field] = (False, f"{field.replace('_', ' ').title()} is required")
            else:
                validation_results[field] = validator(input_data["required"][field])

        # Validate branch protection settings
        if not input_data["branch_protection"]:
            validation_results["branch_protection"] = (False, "At least one branch protection option must be selected")
        else:
            validation_results["branch_protection"] = (True, "Branch protection settings are valid")

        return validation_results

    def process_issue(self, issue):
        """
        Process repository creation issue with improved validation and feedback
        """
        logging.info(f"Processing issue #{issue.number}")

    def validate_repository_name(self, name):
        """
        Validate repository name according to GitHub naming conventions
        
        :param name: Repository name to validate
        :return: tuple(bool, str) - (is_valid, message)
        """
        if not name:
            return False, "Repository name cannot be empty"
        
        # GitHub repository naming rules
        if len(name) > 100:
            return False, "Repository name must be 100 characters or less"
            
        # Check for valid characters (letters, numbers, hyphens, underscores)
        if not re.match(r'^[a-zA-Z0-9._-]+$', name):
            return False, "Repository name can only contain letters, numbers, hyphens, and underscores"
            
        # Check if repository already exists
        try:
            self.org.get_repo(name)
            return False, f"Repository '{name}' already exists in the organization"
        except GithubException:
            pass
            
        return True, "Repository name is valid"

    def validate_description(self, description):
        """
        Validate repository description
        
        :param description: Repository description to validate
        :return: tuple(bool, str) - (is_valid, message)
        """
        if not description:
            return False, "Description cannot be empty"
            
        if len(description) > 350:  # GitHub's description length limit
            return False, "Description must be 350 characters or less"
            
        return True, "Description is valid"

    def validate_visibility(self, visibility):
        """
        Validate repository visibility setting
        
        :param visibility: Desired visibility setting
        :return: tuple(bool, str) - (is_valid, message)
        """
        valid_values = ['private', 'public']
        if not visibility.lower() in valid_values:
            return False, "Visibility must be either 'private' or 'public'"
        return True, "Visibility setting is valid"        # Parse issue body
        input_data = self.parse_issue_body(issue.body)


        # Validate inputs
        validation_results = self.validate_input(input_data)

        # Check if all validations passed
        if all(result[0] for result in validation_results.values()):
            # Generate repository configuration
            config = self.generate_repository_config(input_data)
            repo = self.create_repository(config)

            if repo:
                self._post_success_comment(issue, repo, input_data)
                issue.edit(state="closed")
                logging.info(f"Repository {repo.name} created successfully")
            else:
                self._post_error_comment(issue)
                logging.error("Repository creation failed")
        else:
            feedback_comment = self.generate_validation_comment(validation_results)
            issue.create_comment(feedback_comment)
            logging.warning("Repository creation validation failed")
    def generate_validation_comment(self, validation_results):
        """
        Generate a comment with validation feedback
        
        :param validation_results: Dictionary of validation results
        :return: str - Formatted comment
        """
        comment = "## ❌ Validation Failed\n\nPlease fix the following issues:\n\n"
        
        for field, (is_valid, message) in validation_results.items():
            if not is_valid:
                comment += f"- **{field.title()}**: {message}\n"
                
        comment += "\nPlease update the issue with corrected information."
        return comment

    def generate_repository_config(self, input_data):
        """
        Generate repository configuration from input data
        
        :param input_data: Dictionary of repository inputs
        :return: Dictionary of repository configuration
        """
        return {
            "name": input_data.get("repo-name", ""),
            "description": input_data.get("description", ""),
            "visibility": input_data.get("visibility", "private"),
            "collaborators": input_data.get("collaborators", "").split("\n") if input_data.get("collaborators") else [],
            "teams": input_data.get("teams", "").split("\n") if input_data.get("teams") else []
        }
    
    
    def _post_success_comment(self, issue, repo, input_data):
        """Post a detailed success comment"""
        success_comment = f"""
## 🎉 Repository Created Successfully!

**Repository Details:**
- Name: [{repo.name}]({repo.html_url})
- Description: {repo.description}
- Visibility: {'Private' if repo.private else 'Public'}
- Branch Protection: Enabled
- Teams Added: {', '.join(input_data['optional'].get('teams', '').split()) or 'None'}

Configuration files have been created at:
- `.github/repo_settings.yml`

You can now clone your repository and start working:
```bash
git clone {repo.clone_url}
```
"""
        issue.create_comment(success_comment)

    def _post_error_comment(self, issue):
        """Post an error comment"""
        error_comment = """
## ❌ Repository Creation Failed

There was an error while creating the repository. Please contact an administrator for assistance.

Please provide the following details when seeking help:
- Issue number: #{issue.number}
- Timestamp: {datetime.now().isoformat()}
"""
        issue.create_comment(error_comment)


def get_current_repository(g, full_repo_name):
    """
    Get the current repository where the action is running.

    Args:
        g: Github instance
        full_repo_name: Full repository name (org/repo format)

    Returns:
        github.Repository.Repository: Repository object
    """
    try:
        repo = g.get_repo(full_repo_name)
        logging.info(f"Using current repository: {full_repo_name}")
        return repo
    except GithubException as e:
        logging.error(f"Error accessing current repository: {e}")
        sys.exit(1)


def main():
    # Get GitHub context and event payload
    context, event_payload = get_github_context()

    # Validate required context
    if not context["token"]:
        logging.error("GitHub token not found")
        sys.exit(1)

    if not context["repository"]:
        logging.error("Repository could not be determined")
        sys.exit(1)

    # Initialize GitHub instance
    g = Github(context["token"])

    try:
        # Get the current repository where the action is running
        current_repo = get_current_repository(g, context["repository"])

        # Retrieve issue
        if context["issue_number"]:
            issue = current_repo.get_issue(context["issue_number"])

            # Process the issue
            handler = RepositoryCreationHandler(context["token"], context["organization"])
            handler.process_issue(issue)
        else:
            logging.error("No issue number found in the event payload")
            sys.exit(1)

    except Exception as e:
        logging.error(f"Error processing repository creation: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
