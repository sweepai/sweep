#!/bin/bash
# Check Python version
version=$(python --version 2>&1 | awk '{print $2}')
required_version="3.10"
if [ "${version:0:4}" != "$required_version" ]; then
    echo "The project requires Python $required_version. Please switch to Python $required_version and try again."
    exit 1
fi
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
echo "Installation complete!"
