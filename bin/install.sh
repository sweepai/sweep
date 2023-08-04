#!/bin/bash
# Check if Python 3.10 is installed
if ! command -v python3.10 &> /dev/null
then
    echo "Python 3.10 could not be found, installing..."
    wget https://www.python.org/ftp/python/3.10.0/Python-3.10.0.tgz
    tar xvf Python-3.10.0.tgz
    cd Python-3.10.0
    ./configure --enable-optimizations
    make altinstall
    cd ..
fi
# Check if poetry is installed
if ! command -v poetry &> /dev/null
then
    echo "Poetry could not be found, installing..."
    curl -sSL https://install.python-poetry.org | python3.10 -
fi
# Install packages with poetry
echo "Installing packages with poetry..."
poetry install
poetry shell
# Install deeplake with pip
echo "Installing deeplake with pip..."
pip install deeplake
echo "Installation complete!"
