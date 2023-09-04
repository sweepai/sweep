# sweep-self-deploy

> A GitHub App built with [Probot](https://github.com/probot/probot) that Self-hosted Sweep, an AI powered-junior developer

## Setup

```sh
# Clone the repo
git clone https://github.com/sweepai/sweep

# Build and run sweep locally
docker compose up
```

## Docker

```sh
# Build and run sweep locally
docker compose up
```

This command will build and run sweep locally, binding your directory and hot-reloading the docker image every time your local code changes.

Note: This process can be slow on Macs. We're open to suggestions here! An alternative is to run uvicorn directly, which is faster but doesn't reflect the docker image. You can do this with the following command:

```
uvicorn sweepai.api:app --host 0.0.0.0 --port 8080 --reload-dir '/app/sweepai' --reload
```

## Testing on Mac

To test the new workflow on a Mac, follow the updated instructions for setup and Docker. Monitor the performance and make any necessary adjustments based on your results.

## Contributing

If you have suggestions for how sweep-self-deploy could be improved, or want to report a bug, open an issue! We'd love all and any contributions.

For more, check out the [Contributing Guide](CONTRIBUTING.md).

## License

[ISC](LICENSE) © 2023 Kevin Lu
