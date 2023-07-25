def generate_issue_content(language: str):
    if language == 'Python':
        return 'Please set up black and pylint using GitHub Actions.'
    elif language == 'JavaScript':
        return 'Please set up eslint using GitHub Actions.'
    elif language == 'TypeScript':
        return 'Please set up tsc using GitHub Actions.'
    else:
        return 'Please set up the appropriate linters using GitHub Actions.'