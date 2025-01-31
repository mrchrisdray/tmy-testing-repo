# config.yaml
import os
import sys
import argparse
import pandas as pd
from datetime import datetime
import concurrent.futures
from tqdm import tqdm
from typing import Dict
import yaml
from github import Github


def parse_args():
    parser = argparse.ArgumentParser(description='GitHub Repository Health Checker')
    parser.add_argument('--init-config', action='store_true',
                       help='Create default configuration file')
    parser.add_argument('--token', help='GitHub token',
                       default=os.environ.get('GITHUB_TOKEN'))
    parser.add_argument('--org', help='GitHub organization name',
                       default=os.environ.get('ORG_NAME'))
    return parser.parse_args()

class ConfigManager:
    def __init__(self, config_path: str = "repo_health_config.yaml"):
        """
        Initialize configuration manager.
        
        Args:
            config_path (str): Path to YAML configuration file
        """
        self.config_path = config_path
        self.config = self.load_config()
    
    def load_config(self) -> Dict:
        """Load configuration from YAML file."""
        if not os.path.exists(self.config_path):
            self.create_default_config()
        
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def create_default_config(self):
        """Create default configuration file if none exists."""
        default_config = {
            'required_files': {
                'README.md': {
                    'required': True,
                    'weight': 1.0,
                    'description': 'Project documentation and overview'
                },
                'CODEOWNERS': {
                    'required': True,
                    'weight': 1.0,
                    'description': 'Define individuals responsible for code'
                },
                'SECURITY.md': {
                    'required': True,
                    'weight': 1.0,
                    'description': 'Security policy and reporting instructions'
                },
                'CODE_OF_CONDUCT.md': {
                    'required': True,
                    'weight': 0.8,
                    'description': 'Community behavior guidelines'
                },
                'GOVERNANCE.md': {
                    'required': False,
                    'weight': 0.5,
                    'description': 'Project governance model'
                },
                'SUPPORT.md': {
                    'required': False,
                    'weight': 0.5,
                    'description': 'Support guidelines and resources'
                },
                '.gitignore': {
                    'required': True,
                    'weight': 0.8,
                    'description': 'Git ignore patterns'
                },
                'pull_request_template.md': {
                    'required': True,
                    'weight': 0.8,
                    'description': 'PR template for contributors'
                }
            },
            'security_requirements': {
                'security_scanning': {
                    'required': True,
                    'weight': 1.0,
                    'description': 'Advanced security scanning'
                },
                'dependabot': {
                    'required': True,
                    'weight': 1.0,
                    'description': 'Dependabot alerts'
                }
            },
            'alert_severity_weights': {
                'critical': 1.0,
                'high': 0.75,
                'medium': 0.5,
                'low': 0.25
            },
            'scoring': {
                'component_weights': {
                    'required_files': 0.4,
                    'security_scanning': 0.3,
                    'dependabot': 0.3
                },
                'thresholds': {
                    'green': 80,
                    'amber': 60
                }
            },
            'scanning': {
                'max_workers': 5,
                'include_archived': False,
                'include_private': True
            },
            'reporting': {
                'output_directory': 'reports',
                'include_top_bottom': 5,
                'export_formats': ['csv', 'markdown']
            }
        }
        
        with open(self.config_path, 'w') as f:
            yaml.safe_dump(default_config, f, sort_keys=False)

class GitHubOrgHealthCheck:
    def __init__(self, token: str, org_name: str, config_path: str = "repo_health_config.yaml"):
        """
        Initialize the health checker with GitHub token, organization name, and config.
        
        Args:
            token (str): GitHub personal access token
            org_name (str): GitHub organization name
            config_path (str): Path to configuration file
        """
        self.g = Github(token)
        self.org = self.g.get_organization(org_name)
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.config
    
    def check_single_repo(self, repo):
        """Check health metrics for a single repository."""
        try:
            metrics = {
                'repository': repo.full_name,
                'last_updated': repo.updated_at.isoformat(),
                'required_files': {file: False for file in self.config['required_files'].keys()},
                'security_scanning': False,
                'dependabot_enabled': False,
                'dependabot_alerts': {k: 0 for k in self.config['alert_severity_weights'].keys()},
                'is_archived': repo.archived,
                'is_private': repo.private
            }
            
            # Skip archived repositories if configured
            if repo.archived and not self.config['scanning']['include_archived']:
                return metrics
            
            # Skip private repositories if configured
            if repo.private and not self.config['scanning']['include_private']:
                return metrics
            
            # Check required files
            try:
                contents = repo.get_contents("")
                for content in contents:
                    if content.name.upper() in [f.upper() for f in self.config['required_files'].keys()]:
                        metrics['required_files'][content.name] = True
                
                # Check .github folder for PR template
                try:
                    github_contents = repo.get_contents(".github")
                    for content in github_contents:
                        if content.name.upper() == 'PULL_REQUEST_TEMPLATE.MD':
                            metrics['required_files']['pull_request_template.md'] = True
                except:
                    pass
            except:
                pass
            
            # Calculate required files score with weights
            total_weight = sum(
                file_config['weight']
                for file_config in self.config['required_files'].values()
                if file_config['required']
            )
            
            weighted_sum = sum(
                self.config['required_files'][file]['weight']
                for file, present in metrics['required_files'].items()
                if present and self.config['required_files'][file]['required']
            )
            
            metrics['required_files_score'] = (weighted_sum / total_weight * 100) if total_weight > 0 else 0
            
            # Check security features
            security_config = self.config['security_requirements']
            try:
                security_info = repo.get_security_and_analysis()
                metrics['security_scanning'] = (
                    security_info.advanced_security.status == 'enabled'
                    if security_info.advanced_security
                    else False
                )
            except:
                pass
            
            # Check Dependabot with configured weights
            try:
                metrics['dependabot_enabled'] = repo.get_vulnerability_alert()
                if metrics['dependabot_enabled']:
                    alerts = repo.get_vulnerability_alerts()
                    for alert in alerts:
                        severity = alert.security_advisory.severity.lower()
                        if severity in metrics['dependabot_alerts']:
                            metrics['dependabot_alerts'][severity] += 1
            except:
                pass
            
            # Calculate alert score using configured weights
            weighted_sum = sum(
                metrics['dependabot_alerts'][severity] * weight
                for severity, weight in self.config['alert_severity_weights'].items()
            )
            metrics['alert_score'] = max(0, 100 - (weighted_sum * 10))
            
            # Calculate overall health score using configured weights
            component_weights = self.config['scoring']['component_weights']
            scores = {
                'required_files': metrics['required_files_score'],
                'security_scanning': 100 if metrics['security_scanning'] else 0,
                'dependabot': metrics['alert_score'] if metrics['dependabot_enabled'] else 0
            }
            
            metrics['overall_score'] = sum(
                scores[component] * weight
                for component, weight in component_weights.items()
            )
            
            # Determine traffic light using configured thresholds
            thresholds = self.config['scoring']['thresholds']
            metrics['traffic_light'] = (
                'GREEN' if metrics['overall_score'] >= thresholds['green']
                else 'AMBER' if metrics['overall_score'] >= thresholds['amber']
                else 'RED'
            )
            
            return metrics
            
        except Exception as e:
            print(f"Error processing repository {repo.full_name}: {str(e)}")
            return None
    
    def scan_organization(self):
        """Scan all repositories in the organization."""
        print(f"Scanning repositories in organization: {self.org.login}")
        
        repos = list(self.org.get_repos())
        print(f"Found {len(repos)} repositories")
        
        results = []
        max_workers = self.config['scanning']['max_workers']
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.check_single_repo, repo): repo for repo in repos}
            
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(repos)):
                result = future.result()
                if result:
                    results.append(result)
        
        df = pd.DataFrame(results)
        
        summary = {
            'total_repos': len(results),
            'archived_repos': df['is_archived'].sum(),
            'private_repos': df['is_private'].sum(),
            'avg_health_score': df['overall_score'].mean(),
            'traffic_light_distribution': df['traffic_light'].value_counts().to_dict(),
            'security_scanning_enabled': df['security_scanning'].sum(),
            'dependabot_enabled': df['dependabot_enabled'].sum(),
            'total_critical_alerts': df['dependabot_alerts'].apply(lambda x: x['critical']).sum(),
            'total_high_alerts': df['dependabot_alerts'].apply(lambda x: x['high']).sum(),
            'scan_date': datetime.now().isoformat()
        }
        
        return df, summary
    
    def generate_report(self):
        """Generate reports according to configuration."""
        output_dir = self.config['reporting']['output_directory']
        os.makedirs(output_dir, exist_ok=True)
        
        df, summary = self.scan_organization()
        reports = []
        
        # Generate configured report formats
        for format in self.config['reporting']['export_formats']:
            if format == 'csv':
                csv_path = os.path.join(output_dir, f"{self.org.login}_repo_health_{datetime.now().strftime('%Y%m%d')}.csv")
                df.to_csv(csv_path, index=False)
                reports.append(csv_path)
            
            elif format == 'markdown':
                summary_path = os.path.join(output_dir, f"{self.org.login}_summary_{datetime.now().strftime('%Y%m%d')}.md")
                with open(summary_path, 'w') as f:
                    f.write(f"# Repository Health Summary for {self.org.login}\n\n")
                    f.write(f"Scan Date: {summary['scan_date']}\n\n")
                    
                    f.write("## Overview\n")
                    f.write(f"- Total Repositories: {summary['total_repos']}\n")
                    f.write(f"- Archived Repositories: {summary['archived_repos']}\n")
                    f.write(f"- Private Repositories: {summary['private_repos']}\n")
                    f.write(f"- Average Health Score: {summary['avg_health_score']:.2f}%\n\n")
                    
                    f.write("## Traffic Light Distribution\n")
                    for status, count in summary['traffic_light_distribution'].items():
                        f.write(f"- {status}: {count}\n")
                    
                    f.write("\n## Security Status\n")
                    f.write(f"- Repositories with Security Scanning: {summary['security_scanning_enabled']}\n")
                    f.write(f"- Repositories with Dependabot: {summary['dependabot_enabled']}\n")
                    f.write(f"- Total Critical Alerts: {summary['total_critical_alerts']}\n")
                    f.write(f"- Total High Alerts: {summary['total_high_alerts']}\n")
                    
                    # Add top and bottom performers
                    top_n = self.config['reporting']['include_top_bottom']
                    f.write(f"\n## Top {top_n} Repositories by Health Score\n")
                    top = df.nlargest(top_n, 'overall_score')[['repository', 'overall_score', 'traffic_light']]
                    for _, row in top.iterrows():
                        f.write(f"- {row['repository']}: {row['overall_score']:.2f}% ({row['traffic_light']})\n")
                    
                    f.write(f"\n## Bottom {top_n} Repositories by Health Score\n")
                    bottom = df.nsmallest(top_n, 'overall_score')[['repository', 'overall_score', 'traffic_light']]
                    for _, row in bottom.iterrows():
                        f.write(f"- {row['repository']}: {row['overall_score']:.2f}% ({row['traffic_light']})\n")
                
                reports.append(summary_path)
        
        return reports


# Example usage
if __name__ == "__main__":
    args = parse_args()
    
    # Just create config and exit if --init-config is specified
    if args.init_config:
        ConfigManager().create_default_config()
        print("Created default configuration file: repo_health_config.yaml")
        sys.exit(0)
    
    # Validate required parameters
    if not args.token:
        print("Error: GitHub token not provided")
        sys.exit(1)
    
    if not args.org:
        print("Error: Organization name not provided")
        sys.exit(1)
    
    # Run health check
    checker = GitHubOrgHealthCheck(args.token, args.org)
    report_paths = checker.generate_report()
    
    print(f"\nReports generated:")
    for path in report_paths:
        print(f"- {path}")