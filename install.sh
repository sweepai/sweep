#!/bin/bash

# Navigate to the root directory of the repo
cd "$(dirname "$0")"

# Install the necessary poetry packages
poetry install

# Install the `deeplake` package using pip
pip install deeplake

