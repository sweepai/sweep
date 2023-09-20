#!/bin/bash
# Check if sandbox directory exists, if not clone the repository
if [ ! -d "./sandbox" ]
then
    git clone https://github.com/sweepai/sweep-closed sandbox
else
    if [ -d "./sandbox/.git" ]
    then
        echo "Fetching and pulling latest changes from the repository..."
        cd sandbox
        {
            git fetch
            git pull
        } || {
            echo "An error occurred while fetching and pulling the latest changes."
        }
        cd ..
    fi
fi
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
source $(poetry env info --path)/bin/activate
poetry shell
# Install deeplake with pip
echo "Installing deeplake with pip..."
pip install deeplake
echo "Installing robotexclusionrulesparser with pip..."
pip install robotexclusionrulesparser
echo "Installing e2b with pip..."
pip install e2b
echo "Installing whoosh with pip..."
pip install whoosh
echo "Initializing pre-commits"
pre-commit autoupdate
pre-commit install
echo "Installation complete!"
