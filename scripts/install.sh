#!/bin/bash

# Navigate to the root directory of the project
cd "$(dirname "$0")/.."

# Install the poetry packages
poetry install

# Install the deeplake package using pip
pip install deeplake
```