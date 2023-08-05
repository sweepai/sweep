from sweepai.utils.diff import generate_new_file_from_patch

modify_patch = """
```
<<<< ORIGINAL
    - name: Install dependencies
    run: npm install
====
    - name: Install dependencies
      run: npm install
>>>> UPDATED
```
"""

old_file = """
name: Run tests

on:
  pull_request:
    branches: [ master ]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2

    - name: Use Node.js
      uses: actions/setup-node@v2
      with:
        node-version: '14'

    - name: Install dependencies
    run: npm install

    - name: Run tests
      run: npm test
"""

if __name__ == "__main__":
    print(generate_new_file_from_patch(modify_patch, old_file))
