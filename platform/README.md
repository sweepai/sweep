# Sweep AI Unit Testing Tool

This is a fully locally running dev tool for getting Sweep to generate unit tests. 

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