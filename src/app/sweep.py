import os
import webbrowser
import getpass
import configparser
from github import Github

CONFIG_FILE = "config.ini"
CLIENT_ID = "your_client_id"
CLIENT_SECRET = "your_client_secret"

def generate_auth_url():
    g = Github()
    auth_url = g.get_authorize_url(scope='repo')
    return auth_url

def login():
    auth_url = generate_auth_url()
    print("Please open the following URL in your browser to authorize the application:")
    print(auth_url)
    webbrowser.open(auth_url)

    code = input("Enter the code from the authorization page: ")

    try:
        g = Github(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
        token = g.get_access_token(code)
        save_config(token)
        print("Login successful! Personal access token (PAT) has been saved.")
    except Exception as e:
        print("Login failed:", str(e))


def save_config(token):
    # config = configparser.ConfigParser()
    # config['github'] = {'token': token}
    # with open(CONFIG_FILE, 'w') as config_file:
    #     config.write(config_file)
    print(token)

# def load_config():
#     config = configparser.ConfigParser()
#     if os.path.exists(CONFIG_FILE):
#         config.read(CONFIG_FILE)
#         if 'github' in config and 'token' in config['github']:
#             return config['github']['token']
#     return None

def main():
    # token = load_config()

    # if token:
    #     print("You are already logged in!")
    # else:
    login()

if __name__ == '__main__':
    main()