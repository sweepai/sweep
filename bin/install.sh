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
echo "Installing robotexclusionrulesparser with pip..."
pip install robotexclusionrulesparser
echo "Installing e2b with pip..."
pip install e2b
echo "Initializing pre-commits"
pre-commit autoupdate
pre-commit install
echo "Installation complete!"
