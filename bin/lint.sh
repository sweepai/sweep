python_files=`git diff --name-only --diff-filter=d | grep -E '\.py$' | tr '\n' ' '`; \
if [ -z "$python_files" ]; then true; else pylint $python_files --errors-only; fi
