# Lint the code and check the return code
  if sh bin/lint.sh; then
    # Linting passed, continue with other commands
    echo "Successfully linted"

    [ "$(uname)" = "Darwin" ] && sed -i "" -E "s/PREFIX = '(prod|dev)'/PREFIX = 'dev2'/" sweepai/config/server.py || sed -i -E "s/PREFIX = '(prod|dev)'/PREFIX = 'dev2'/" sweepai/config/server.py
    modal deploy --env=staging sweepai/utils/utils.py &
    modal deploy --env=staging sweepai/core/vector_db.py &
    modal deploy --env=staging sweepai/core/documentation.py &
    modal deploy --env=staging sweepai/api.py

else
  # Linting failed, show an error message and exit
  echo "Linting failed. Aborting other commands."
  exit 1
fi
