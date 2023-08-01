import os

# goes under Modal 'bitbucket' secret name
BITBUCKET_APP_ID = os.environ.get('BITBUCKET_APP_ID')
BITBUCKET_APP_SECRET = os.environ.get('BITBUCKET_APP_SECRET')
BITBUCKET_CONFIG_BRANCH = os.environ.get('BITBUCKET_CONFIG_BRANCH', 'sweep/add-sweep-config')