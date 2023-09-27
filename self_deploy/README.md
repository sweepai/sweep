# sweep-self-deploy

> A GitHub App built with [Probot](https://github.com/probot/probot) that Self-hosted Sweep, an AI powered-junior developer

## Setup

```sh
# Install dependencies
npm install

# Run the bot
npm start
```

## Docker

```sh
# 1. Build container
docker build -t sweep-self-deploy .

# 2. Start container
docker run -e APP_ID=<app-id> -e PRIVATE_KEY=<pem-value> sweep-self-deploy
```

## Contributing

Open an issue to suggest improvements or report bugs.

For more, check out the [Contributing Guide](CONTRIBUTING.md).

## License

[ISC](LICENSE) © 2023 Kevin Lu
