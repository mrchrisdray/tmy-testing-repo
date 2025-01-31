import os
import re
import yaml
import sys
import json
import logging
from github import Github, GithubException

# Import the config generation functions
from repo_config_generator import generate_repository_config, save_repository_config

class RepositoryCreationHandler:
    def __init__(self, github_token, org_name):
        """
        Initialize the Repository Creation Handler
        
        :param github_token: GitHub Personal Access Token
        :param org_name: GitHub Organization Name
        """
        self.g = Github(github_token)
        self.org = self.g.get_organization(org_name)
        self.org_name = org_name
    
    def create_repository(self, input_data):
        """
        Create repository and generate configuration file
        
        :param input_data: Dictionary of repository creation inputs
        :return: Created repository object
        """
        try:
            # Prepare repository creation parameters
            repo_params = {
                'name': input_data.get('name', ''),
                'description': input_data.get('description', ''),
                'private': input_data.get('visibility', 'Private').lower() == 'private',
                'auto_init': True
            }
            
            # Create repository in GitHub
            repo = self.org.create_repo(**repo_params)
            
            # Generate repository configuration
            config = generate_repository_config({
                'name': repo.name,
                'description': repo.description,
                'private': repo.private,
                'collaborators': input_data.get('collaborators', '').split('\n') if input_data.get('collaborators') else [],
                'teams': input_data.get('teams', '').split('\n') if input_data.get('teams') else []
            })
            
            # Save configuration file
            config_path = save_repository_config(repo.name, config)
            
            # Optional: Commit configuration file to the repository
            with open(config_path, 'r') as config_file:
                config_content = config_file.read()
                repo.create_file(
                    path='.github/repo_config.yml',
                    message='Add initial repository configuration',
                    content=config_content
                )
            
            return repo
        
        except Exception as e:
            logging.error(f"Repository creation error: {e}")
            return None
    
    # ... [rest of the class remains the same]

# The rest of the script remains largely unchanged
def main():
    # ... [previous main function implementation]
    # When creating the handler, pass the context and event payload
    handler = RepositoryCreationHandler(context['token'], context['organization'])
    
    # In the process_issue method, use the new create_repository approach
    repo = handler.create_repository({
        'name': input_data.get('repo-name', ''),
        'description': input_data.get('description', ''),
        'visibility': input_data.get('visibility', 'Private'),
        'collaborators': input_data.get('collaborators', ''),
        'teams': input_data.get('teams', '')
    })

if __name__ == '__main__':
    main()