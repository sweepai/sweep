#!/bin/bash
# Check Python version
if ! python3.10 --version &> /dev/null
then
    echo "Python 3.10 is not installed, installing..."
    pyenv install 3.10.0
    pyenv global 3.10.0
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
