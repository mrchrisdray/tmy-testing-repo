import os
import yaml
from datetime import datetime

def generate_repository_config(repo_details):
    """
    Generate a comprehensive repository configuration file
    
    :param repo_details: Dictionary of repository details
    :return: Dictionary representing the repository configuration
    """
    # Get current timestamp
    timestamp = datetime.now().isoformat()
    
    # Base configuration template
    config = {
        # Metadata
        'metadata': {
            'name': repo_details.get('name', ''),
            'description': repo_details.get('description', ''),
            'created_at': timestamp,
            'visibility': 'private' if repo_details.get('private', True) else 'public',
        },
        
        # Version Control
        'version_control': {
            'default_branch': 'main',
            'protected_branches': ['main'],
        },
        
        # Access Control
        'access_control': {
            'collaborators': repo_details.get('collaborators', []),
            'teams': repo_details.get('teams', []),
        },
        
        # CI/CD Configuration
        'ci_cd': {
            'enabled': True,
            'workflows': [
                {
                    'name': 'Continuous Integration',
                    'trigger': ['push', 'pull_request'],
                    'branches': ['main', 'develop']
                }
            ]
        },
        
        # Security Settings
        'security': {
            'branch_protection': {
                'enforce_admins': True,
                'required_reviews': {
                    'count': 1,
                    'dismiss_stale_reviews': True
                },
                'required_status_checks': [
                    'continuous-integration/github-actions'
                ]
            },
            'dependabot': {
                'version_updates': True,
                'security_updates': True
            }
        },
        
        # Development Workflow
        'development': {
            'default_branch_protection': True,
            'issue_templates': [],
            'pull_request_templates': []
        }
    }
    
    return config

def save_repository_config(repo_name, config):
    """
    Save repository configuration to a YAML file
    
    :param repo_name: Name of the repository
    :param config: Configuration dictionary
    :return: Path to the saved configuration file
    """
    # Ensure repositories directory exists
    repositories_dir = os.path.join(os.getcwd(), 'repositories')
    os.makedirs(repositories_dir, exist_ok=True)
    
    # Generate filename
    config_filename = f"{repo_name}.yml"
    config_path = os.path.join(repositories_dir, config_filename)
    
    # Write configuration file
    with open(config_path, 'w') as config_file:
        yaml.dump(config, config_file, default_flow_style=False)
    
    return config_path

def main():
    # Example usage (for testing)
    repo_details = {
        'name': 'example-project',
        'description': 'A sample repository configuration',
        'private': True,
        'collaborators': ['user1', 'user2'],
        'teams': ['developers']
    }
    
    # Generate configuration
    config = generate_repository_config(repo_details)
    
    # Save configuration
    config_path = save_repository_config(repo_details['name'], config)
    
    print(f"Configuration saved to: {config_path}")

if __name__ == '__main__':
    main()