import os

def generate_linter_config(language):
    if language == 'python':
        return """
        name: Lint

        on: [push]

        jobs:
          build:

            runs-on: ubuntu-latest

            steps:
            - uses: actions/checkout@v2
            - name: Set up Python
              uses: actions/setup-python@v2
              with:
                python-version: '3.x'
            - name: Install dependencies
              run: |
                python -m pip install --upgrade pip
                pip install pylint
            - name: Analyze code with pylint
              run: pylint --errors-only
        """
    elif language in ['javascript', 'typescript']:
        return """
        name: Lint

        on: [push]

        jobs:
          build:

            runs-on: ubuntu-latest

            steps:
            - uses: actions/checkout@v2
            - name: Use Node.js
              uses: actions/setup-node@v2
              with:
                node-version: '14'
            - name: Install dependencies
              run: |
                npm ci
                npm install eslint tsc
            - name: Analyze code with eslint or tsc
              run: eslint . || tsc
        """
    else:
        raise ValueError(f"Unsupported language: {language}")