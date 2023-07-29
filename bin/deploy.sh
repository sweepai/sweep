export OPENAI_DO_HAVE_32K_MODEL_ACCESS=true

# Lint the code and check the return code
if sh bin/lint.sh; then
    # Linting passed, continue with other commands
    echo "Successfully linted"
    
    # Deploy the package in the background and wait for it to finish
    modal deploy my_package.my_file &
    wait
    
else
    # Linting failed, show an error message and exit
    echo "Linting failed. Aborting other commands."
    exit 1
fi