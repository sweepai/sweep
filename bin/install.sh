#!/bin/bash
rm -f poetry.lock
# Check if poetry is installed
if ! command -v poetry &> /dev/null
then
    echo "Poetry could not be found, installing..."
    curl -sSL https://install.python-poetry.org | python3 -
fi
# Install packages with poetry
echo "Installing packages with poetry..."
poetry install
poetry shell
# Install deeplake with pip
echo "Installing deeplake with pip..."
pip install deeplake
# Verify deeplake.core.vectorstore.deeplake_vectorstore is installed
echo "Verifying deeplake.core.vectorstore.deeplake_vectorstore is installed..."
python -c "
try:
    import deeplake.core.vectorstore.deeplake_vectorstore
    print('deeplake.core.vectorstore.deeplake_vectorstore is installed successfully.')
except ImportError:
    print('Error: deeplake.core.vectorstore.deeplake_vectorstore is not installed.')
"
# Install robotexclusionrulesparser with pip
echo "Installing robotexclusionrulesparser with pip..."
pip install robotexclusionrulesparser
# Verify robotexclusionrulesparser is installed
echo "Verifying robotexclusionrulesparser is installed..."
python -c "
try:
    import robotexclusionrulesparser
    print('robotexclusionrulesparser is installed successfully.')
except ImportError:
    print('Error: robotexclusionrulesparser is not installed.')
"
echo "Installation complete!"