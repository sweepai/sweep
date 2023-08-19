# Lint the code and check the return code
if sh bin/lint.sh; then
  # Linting passed, continue with other commands
  echo "Successfully linted"

    [ "$(uname)" = "Darwin" ] && sed -i "" -E "s/PREFIX = '(dev|dev2)'/PREFIX = 'prod'/" sweepai/config/server.py || sed -i -E "s/PREFIX = 'PREFIX = '(dev|dev2)'/PREFIX = 'prod'/" sweepai/config/server.py
    modal deploy --env=main sweepai/utils/utils.py &
    modal deploy --env=main sweepai/core/vector_db.py &
    modal deploy --env=main sweepai/core/documentation.py &
    modal deploy --env=main sweepai/api.py

else
  # Linting failed, show an error message and exit
  echo "Linting failed. Aborting other commands."
  exit 1
fi
