# Runs pylint on all python files in the git diff
pylint `git diff --name-only --diff-filter=d | grep -E '\.py$' | tr '\n' ' '` --errors-only