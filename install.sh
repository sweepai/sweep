#!/bin/bash
# Check if poetry is installed
if ! command -v poetry &> /dev/null
then
    echo "Poetry could not be found, installing..."
    curl -sSL https://install.python-poetry.org | python3 -
fi
# Install packages with poetry
echo "Installing packages with poetry..."
poetry install
# Install deeplake with pip
echo "Installing deeplake with pip..."
pip install deeplake
echo "Installing black with Jupyter dependencies..."
pip install black[jupyter]
echo "Installation complete!"
