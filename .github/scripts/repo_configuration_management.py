import os
import yaml
import json
import sys
from github import Github 

class RepositoryConfigManager:
    def __init__(self, github_token, org_name):
        """
        Initialize the Repository Configuration Manager
        
        :param github_token: GitHub Personal Access Token
        :param org_name: GitHub Organization Name
        """
        self.g = Github(github_token)
        self.org = self.g.get_organization(org_name)
        self.config_filename = '.github/repo_settings.yml'
    
    def validate_repository_config(self, repo):
        """
        Validate repository configuration against predefined settings
        
        :param repo: GitHub Repository object
        :return: Dictionary of configuration changes
        """
        try:
            # Try to get the config file
            try:
                config_content = repo.get_contents(self.config_filename)
                config = yaml.safe_load(config_content.decoded_content)
            except Exception:
                # No config file found
                return None
            
            changes = {}
            
            # Validate and update repository metadata
            if 'metadata' in config:
                metadata = config['metadata']
                
                # Check repository name
                if metadata.get('name') and metadata['name'] != repo.name:
                    changes['name'] = metadata['name']
                
                # Check description
                if metadata.get('description') and metadata['description'] != repo.description:
                    changes['description'] = metadata['description']
                
                # Check visibility
                if metadata.get('private') is not None and metadata['private'] != repo.private:
                    changes['private'] = metadata['private']
            
            # Validate branch protection
            if 'branch_protection' in config:
                branch_config = config['branch_protection']
                default_branch = repo.default_branch
                
                try:
                    branch = repo.get_branch(default_branch)
                    current_protection = branch.get_protection()
                    
                    # Compare current protection with desired protection
                    protection_changes = self._compare_branch_protection(
                        current_protection, 
                        branch_config
                    )
                    
                    if protection_changes:
                        changes['branch_protection'] = protection_changes
                
                except Exception as e:
                    # If branch protection can't be retrieved or set
                    print(f"Error checking branch protection: {e}")
            
            # Validate repository collaborators and teams
            if 'collaborators' in config:
                current_collaborators = [member.login for member in repo.get_collaborators()]
                desired_collaborators = config['collaborators']
                
                add_collaborators = set(desired_collaborators) - set(current_collaborators)
                remove_collaborators = set(current_collaborators) - set(desired_collaborators)
                
                if add_collaborators or remove_collaborators:
                    changes['collaborators'] = {
                        'add': list(add_collaborators),
                        'remove': list(remove_collaborators)
                    }
            
            return changes if changes else None
        
        except Exception as e:
            print(f"Error validating repository configuration: {e}")
            return None
    
    def _compare_branch_protection(self, current_protection, desired_protection):
        """
        Compare current branch protection with desired configuration
        
        :param current_protection: Current branch protection settings
        :param desired_protection: Desired branch protection configuration
        :return: Dictionary of protection changes
        """
        changes = {}
        
        # Check required status checks
        if 'required_status_checks' in desired_protection:
            current_contexts = set(current_protection.required_status_checks.contexts)
            desired_contexts = set(desired_protection.get('required_status_checks', []))
            
            if current_contexts != desired_contexts:
                changes['required_status_checks'] = {
                    'add': list(desired_contexts - current_contexts),
                    'remove': list(current_contexts - desired_contexts)
                }
        
        # Check enforce admins
        if 'enforce_admins' in desired_protection:
            if current_protection.enforce_admins.enabled != desired_protection['enforce_admins']:
                changes['enforce_admins'] = desired_protection['enforce_admins']
        
        # Check required pull request reviews
        if 'required_pull_request_reviews' in desired_protection:
            review_config = desired_protection['required_pull_request_reviews']
            current_reviews = current_protection.required_pull_request_reviews
            
            # Compare review requirements
            review_changes = {}
            if 'required_approving_review_count' in review_config:
                if current_reviews.required_approving_review_count != review_config['required_approving_review_count']:
                    review_changes['required_approving_review_count'] = review_config['required_approving_review_count']
            
            if review_changes:
                changes['required_pull_request_reviews'] = review_changes
        
        return changes
    
    def apply_repository_changes(self, repo, changes):
        """
        Apply detected configuration changes to the repository
        
        :param repo: GitHub Repository object
        :param changes: Dictionary of changes to apply
        """
        try:
            # Apply metadata changes
            if 'name' in changes or 'description' in changes or 'private' in changes:
                repo.edit(
                    name=changes.get('name', repo.name),
                    description=changes.get('description', repo.description),
                    private=changes.get('private', repo.private)
                )
            
            # Apply branch protection changes
            if 'branch_protection' in changes:
                branch = repo.get_branch(repo.default_branch)
                protection_changes = changes['branch_protection']
                
                # Update required status checks
                if 'required_status_checks' in protection_changes:
                    current_contexts = branch.get_protection().required_status_checks.contexts
                    new_contexts = list(set(current_contexts) | 
                                        set(protection_changes['required_status_checks'].get('add', [])) - 
                                        set(protection_changes['required_status_checks'].get('remove', [])))
                    branch.edit_protection(required_status_checks={'contexts': new_contexts})
                
                # Update enforce admins
                if 'enforce_admins' in protection_changes:
                    if protection_changes['enforce_admins']:
                        branch.edit_protection(enforce_admins=True)
                    else:
                        branch.edit_protection(enforce_admins=False)
                
                # Update pull request reviews
                if 'required_pull_request_reviews' in protection_changes:
                    review_changes = protection_changes['required_pull_request_reviews']
                    branch.edit_protection(
                        required_pull_request_reviews={
                            'required_approving_review_count': review_changes.get('required_approving_review_count', 1)
                        }
                    )
            
            # Manage collaborators
            if 'collaborators' in changes:
                collab_changes = changes['collaborators']
                
                # Add new collaborators
                for username in collab_changes.get('add', []):
                    repo.add_to_collaborators(username)
                
                # Remove collaborators
                for username in collab_changes.get('remove', []):
                    repo.remove_collaborator(username)
        
        except Exception as e:
            print(f"Error applying repository changes: {e}")

def main():
    # This would typically be passed as environment variables or arguments
    github_token = os.environ.get('GITHUB_TOKEN')
    org_name = os.environ.get('GITHUB_ORGANIZATION')
    
    if not github_token or not org_name:
        print("Missing GitHub Token or Organization Name")
        sys.exit(1)
    
    config_manager = RepositoryConfigManager(github_token, org_name)
    
    # Iterate through repositories in the organization
    for repo in config_manager.org.get_repos():
        changes = config_manager.validate_repository_config(repo)
        
        if changes:
            print(f"Applying changes to repository: {repo.full_name}")
            config_manager.apply_repository_changes(repo, changes)

if __name__ == '__main__':
    main()