# Check Python version
python_version=$(python --version | cut -d " " -f 2 | cut -d "." -f 1,2)
required_python_version="3.10"

if [ "$python_version" != "$required_python_version" ]; then
    echo "Installing and activating Python $required_python_version..."
    pyenv install $required_python_version
    pyenv global $required_python_version
fi

export PYTHONPATH=.
python sweepai/app/cli.py