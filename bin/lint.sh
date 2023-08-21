git diff --name-only --cached | grep '\.py$' | xargs pylint --errors-only || echo "Pylint failed with error code $?"
