#!/bin/bash

# Check if poetry is installed
if ! command -v poetry &> /dev/null
then
    echo "Poetry could not be found. Installing..."
    curl -sSL https://install.python-poetry.org | bash
fi

# Install poetry packages
echo "Installing poetry packages..."
poetry install

# Install deeplake using pip
echo "Installing deeplake..."
pip install deeplake

echo "Installation complete!"