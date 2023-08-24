git diff --name-only --cached | grep '\.py$' | xargs -r pylint --errors-only || echo "Pylint failed with error code $?"
