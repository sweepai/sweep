# Lint the code and check the return code
if sh bin/lint.sh; then
  # Linting passed, continue with other commands
  echo "Successfully linted"

  modal deploy --env=dev sweepai/entrypoints/chunker.py &&
    modal deploy --env=dev sweepai/entrypoints/vector_db.py &&
    modal deploy --env=dev sweepai/entrypoints/doc_parser.py &&
    modal deploy --env=dev sweepai/entrypoints/api/api.py

else
  # Linting failed, show an error message and exit
  echo "Linting failed. Aborting other commands."
  exit 1
fi
