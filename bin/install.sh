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
# Install deeplake with poetry
echo "Installing deeplake with poetry..."
poetry add deeplake
# Run pylint within the poetry environment
echo "Running pylint check..."
poetry run pylint sweepai --errors-only
echo "Installation complete!"