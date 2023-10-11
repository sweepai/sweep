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

## Test other LLMs

### Huggingface, Palm, Ollama, TogetherAI, AI21, Cohere etc.[Full List](https://docs.litellm.ai/docs/providers)

#### Create OpenAI-proxy
We'll use [LiteLLM](https://docs.litellm.ai/docs/) to create an OpenAI-compatible endpoint, that translates OpenAI calls to any of the [supported providers](https://docs.litellm.ai/docs/providers).

Example to use a local CodeLLama model from Ollama.ai with Sweep: 

Let's spin up a proxy server to route any OpenAI call from Sweep to Ollama/CodeLlama
```python
pip install litellm
```
```python
$ litellm --model ollama/codellama

#INFO: Ollama running on http://0.0.0.0:8000
```

[Docs](https://docs.litellm.ai/docs/proxy_server)

### Update Sweep

Update your .env 

```shell
os.environ["OPENAI_API_BASE"] = "http://0.0.0.0:8000"
os.environ["OPENAI_API_KEY"] = "my-fake-key"
```


## Contributing

If you have suggestions for how sweep-self-deploy could be improved, or want to report a bug, open an issue! We'd love all and any contributions.

For more, check out the [Contributing Guide](CONTRIBUTING.md).

## License

[ISC](LICENSE) © 2023 Kevin Lu
