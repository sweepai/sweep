#!/bin/bash

# Lint the code and check the return code
if sh bin/lint.sh; then
  # Linting passed, continue with other commands
  echo "Successfully linted"

  # Sync deployment is required due to instances depending on each other
  modal deploy --env=main sweepai/entrypoints/chunker.py &&
    modal deploy --env=main sweepai/entrypoints/vector_db.py &&
    modal deploy --env=main sweepai/entrypoints/doc_parser.py &&
    modal deploy --env=main sweepai/entrypoints/api/api.py

else
  # Linting failed, show an error message and exit
  echo "Linting failed. Aborting other commands."
  exit 1
fi
