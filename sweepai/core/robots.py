import requests
# Ensure that the `robotexclusionrulesparser` module is installed in the project's environment. If it's not, add it to the project's `pyproject.toml` file.
from robotexclusionrulesparser import RobotExclusionRulesParser

def is_url_allowed(url, user_agent='*'):
    robots_url = '/'.join(url.split('/')[:3]) + '/robots.txt'
    try:
        response = requests.get(robots_url)
        robots_txt = response.text
        
        rerp = RobotExclusionRulesParser()
        rerp.parse(robots_txt)
        return rerp.is_allowed(user_agent, url)
    except:
        return False