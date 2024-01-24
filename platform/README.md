# Sweep AI Unit Testing Tool

This is a fully locally running dev tool for getting Sweep to improve your unit testing suite. It uses your local machine to execute all unit tests for security and rapid iteration.

## Getting Started

### Step 0: Pre-requisites

For most user's the following script should work:

```sh
# For NVM (optional)
wget -qO- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
# For PNPM
npm install -g pnpm
```

But if that doesn't work, the installation for NVM can be found [here](https://github.com/nvm-sh/nvm?tab=readme-ov-file#install--update-script) and PNPM at [here](https://pnpm.io/installation#using-npm).

### Step 1: Set up the Environment and Building

Clone into the repo and set up the environment.

```sh
git clone https://github.com/sweepai/sweep
cd sweep/platform
nvm use
pnpm i
pnpm build
```

This should take a couple minutes to install. In the meantime, move onto the next step.

### Step 2: Get your OpenAI key

Add the following to your `.env.local`.

```sh
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Step 3: Run the Tool

Now you're ready to run the tool! Just run:

```sh
pnpm start
```

## Using Sweep Unit Test Tool

1. Insert the path to your local repository.
    - (Optional) Edit the branch name to checkout into a new branch for Sweep to work in (defaults to current branch).
2. Select an existing file for Sweep to add unit tests to.
3. Add meticulous instructions for the unit tests to add, such as the additional edge cases you would like covered.
4. Modify the "Test Script" to write your script for running unit tests, such as `python $FILE_PATH`. You may use the variable $FILE_PATH torefer to the current path. Click the "Run Tests" button to test the script.
    - Hint: use the $FILE_PATH parameter to only run the unit tests in the current file to reduce noise from the unit tests from other files.
5. Click "Generate Code" to get Sweep to generate additional unit tests.
6. Then click "Refresh" or the check mark to restart or approve the change.
