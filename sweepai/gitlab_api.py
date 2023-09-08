import requests

class GitLabAPI:
    def __init__(self, base_url, access_token):
        self.base_url = base_url
        self.access_token = access_token
        self.headers = {'Authorization': f'Bearer {self.access_token}'}

    def get_project(self, project_id):
        try:
            response = requests.get(f'{self.base_url}/projects/{project_id}', headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            print(f'HTTP error occurred: {err}')
        except Exception as err:
            print(f'Other error occurred: {err}')

    def create_issue(self, project_id, title, description):
        try:
            payload = {'title': title, 'description': description}
            response = requests.post(f'{self.base_url}/projects/{project_id}/issues', headers=self.headers, data=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            print(f'HTTP error occurred: {err}')
        except Exception as err:
            print(f'Other error occurred: {err}')

    # Add more methods as needed for other GitLab API endpoints
