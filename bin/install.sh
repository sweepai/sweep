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
        ...
        # Install deeplake with pip
        echo "Installing deeplake with pip..."
        pip install deeplake
        echo "Installing robotexclusionrulesparser with pip..."
        pip install robotexclusionrulesparser
        echo "Installing e2b with pip..."
        pip install e2b
        echo "Installing whoosh with pip..."
        pip install whoosh
        echo "Installing black[jupyter] with pip..."
        pip install "black[jupyter]"
        ...
pre-commit autoupdate
pre-commit install
echo "Installation complete!"
