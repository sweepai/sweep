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

If you have suggestions for how sweep-self-deploy could be improved, or want to report a bug, open an issue! We'd love all and any contributions.

For more, check out the [Contributing Guide](CONTRIBUTING.md).

## License

[ISC](LICENSE) © 2023 Kevin Lu
