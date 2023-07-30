export OPENAI_DO_HAVE_32K_MODEL_ACCESS=true

# Lint the code and check the return code
if sh bin/lint.sh; then
    # Linting passed, continue with other commands
    echo "Successfully linted"
    
    # Deploy each module in the background and wait for all of them to finish
    modal deploy sweepai/api.py
    modal deploy sweepai/utils/utils.py
    modal deploy sweepai/core/vector_db.py
    wait
    
else
    # Linting failed, show an error message and exit
    echo "Linting failed. Aborting other commands."
    exit 1
fi