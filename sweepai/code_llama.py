# # Hosting any LLaMA 2 model with Text Generation Inference (TGI)
#
# In this example, we show how to run an optimized inference server using [Text Generation Inference (TGI)](https://github.com/huggingface/text-generation-inference)
# with performance advantages over standard text generation pipelines including:
# - continuous batching, so multiple generations can take place at the same time on a single container
# - PagedAttention, an optimization that increases throughput.
#
# This example deployment, [accessible here](https://modal-labs--tgi-app.modal.run), can serve LLaMA 2 70B with
# 70 second cold starts, up to 200 tokens/s of throughput and per-token latency of 55ms.

# ## Setup
#
# First we import the components we need from `modal`.

from pathlib import Path

from modal import Image, Mount, Secret, Stub, asgi_app, gpu, method

# Next, we set which model to serve, taking care to specify the number of GPUs required
# to fit the model into VRAM, and the quantization method (`bitsandbytes` or `gptq`) if desired.
# Note that quantization does degrade token generation performance significantly.
#
# Any model supported by TGI can be chosen here.

N_GPUS = 4
# MODEL_ID = "meta-llama/Llama-2-70b-chat-hf"
MODEL_ID = "codellama/CodeLlama-34b-Instruct-hf"
# Add `["--quantize", "gptq"]` for TheBloke GPTQ models.
LAUNCH_FLAGS = ["--model-id", MODEL_ID]

# ## Define a container image
#
# We want to create a Modal image which has the Huggingface model cache pre-populated.
# The benefit of this is that the container no longer has to re-download the model from Huggingface -
# instead, it will take advantage of Modal's internal filesystem for faster cold starts. On
# the largest 70B model, the 135GB model can be loaded in as little as 70 seconds.
#
# ### Download the weights
# Since TGI uses `snapshot_download` under the hood, running this function for our image build
# will place the weights into the cache directly. There are no progress bars as this uses
# the high-throughput `hf-transfer` library, but expect ~700MB/s for this step.
#


def download_model():
    from huggingface_hub import snapshot_download

    snapshot_download(MODEL_ID, ignore_patterns="*.bin")


# ### Image definition
# We’ll start from a Dockerhub image recommended by TGI, and override the default `ENTRYPOINT` for
# Modal to run its own which enables seamless serverless deployments.
#
# Next we run the download step to pre-populate the image with our model weights.
#
# For this step to work on a gated model such as LLaMA 2, the HUGGING_FACE_HUB_TOKEN environment
# variable must be set ([reference](https://github.com/huggingface/text-generation-inference#using-a-private-or-gated-model)).
# After [creating a HuggingFace access token](https://huggingface.co/settings/tokens),
# head to the [secrets page](https://modal.com/secrets) to create a Modal secret.
#
# The key should be `HUGGING_FACE_HUB_TOKEN` and the value should be your access token.
#
# Finally, we install the `text-generation` client to interface with TGI's Rust webserver over `localhost`.

image = (
    Image.from_dockerhub("ghcr.io/huggingface/text-generation-inference:1.0.1")
    .dockerfile_commands("ENTRYPOINT []")
    .run_function(download_model, secret=Secret.from_name("huggingface"))
    .pip_install("text-generation")
)

stub = Stub("example-tgi-" + MODEL_ID.split("/")[-1], image=image)


# ## The model class
#
# The inference function is best represented with Modal's [class syntax](/docs/guide/lifecycle-functions).
# The class syntax is a special representation for a Modal function which splits logic into two parts:
# 1. the `__enter__` method, which runs once per container when it starts up, and
# 2. the `@method()` function, which runs per inference request.
#
# This means the model is loaded into the GPUs, and the backend for TGI is launched just once when each
# container starts, and this state is cached for each subsequent invocation of the function.
# Note that on start-up, we must wait for the Rust webserver to accept connections before considering the
# container ready.
#
# Here, we also
# - specify the secret so the `HUGGING_FACE_HUB_TOKEN` environment variable is set
# - specify how many A100s we need per container
# - specify that each container is allowed to handle up to 10 inputs (i.e. requests) simultaneously
# - keep idle containers for 10 minutes before spinning down
# - lift the timeout of each request.


@stub.cls(
    secret=Secret.from_name("huggingface"),
    gpu=gpu.A100(count=N_GPUS),
    allow_concurrent_inputs=10,
    container_idle_timeout=60 * 10,
    timeout=60 * 60,
)
class Model:
    def __enter__(self):
        import socket
        import subprocess
        import time

        from text_generation import AsyncClient

        self.launcher = subprocess.Popen(["text-generation-launcher"] + LAUNCH_FLAGS)
        self.client = AsyncClient("http://0.0.0.0:80", timeout=60)
        self.template = """<s>[INST] <<SYS>>
{system}
<</SYS>>

{user} [/INST] """

        # Poll until webserver at 0.0.0.0:80 accepts connections before running inputs.
        def webserver_ready():
            try:
                socket.create_connection(("0.0.0.0", 80), timeout=1).close()
                return True
            except (socket.timeout, ConnectionRefusedError):
                return False

        while not webserver_ready():
            time.sleep(1.0)

        print("Webserver ready!")

    def __exit__(self, _exc_type, _exc_value, _traceback):
        self.launcher.terminate()

    @method()
    async def generate(self, question: str):
        prompt = self.template.format(system="", user=question)
        result = await self.client.generate(prompt, max_new_tokens=1024)

        return result.generated_text

    @method()
    async def generate_stream(self, question: str):
        prompt = self.template.format(system="", user=question)

        async for response in self.client.generate_stream(prompt, max_new_tokens=1024):
            if not response.token.special:
                yield response.token.text


# ## Run the model
# We define a [`local_entrypoint`](/docs/guide/apps#entrypoints-for-ephemeral-apps) to invoke
# our remote function. You can run this script locally with `modal run text_generation_inference.py`.
@stub.local_entrypoint()
def main():
    print(
        Model().generate.remote(
            "Implement a Python function to compute the Fibonacci numbers."
        )
    )


# ## Serve the model
# Once we deploy this model with `modal deploy text_generation_inference.py`, we can serve it
# behind an ASGI app front-end. The front-end code (a single file of Alpine.js) is available
# [here](https://github.com/modal-labs/modal-examples/blob/main/06_gpu_and_ml/llm-frontend/index.html).
#
# You can try our deployment [here](https://modal-labs--example-falcon-gptq-get.modal.run/?question=Why%20are%20manhole%20covers%20round?).

frontend_path = Path(__file__).parent / "llm-frontend"


@stub.function(
    mounts=[Mount.from_local_dir(frontend_path, remote_path="/assets")],
    keep_warm=1,
    allow_concurrent_inputs=10,
    timeout=60 * 10,
)
@asgi_app(label="tgi-app")
def app():
    import json

    import fastapi
    import fastapi.staticfiles
    from fastapi.responses import StreamingResponse

    web_app = fastapi.FastAPI()

    @web_app.get("/stats")
    def stats():
        stats = Model().generate_stream.get_current_stats()
        return {
            "backlog": stats.backlog,
            "num_total_runners": stats.num_total_runners,
        }

    @web_app.get("/completion/{question}")
    def completion(question: str):
        from urllib.parse import unquote

        def generate():
            for text in Model().generate_stream.remote(unquote(question)):
                yield f"data: {json.dumps(dict(text=text), ensure_ascii=False)}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    web_app.mount("/", fastapi.staticfiles.StaticFiles(directory="/assets", html=True))
    return web_app


# ## Invoke the model from other apps
# Once the model is deployed, we can invoke inference from other apps, sharing the same pool
# of GPU containers with all other apps we might need.
#
# ```
# $ python
# >>> import modal
# >>> f = modal.Function.lookup("example-tgi-Llama-2-70b-chat-hf", "Model.generate")
# >>> f.remote("What is the story about the fox and grapes?")
# 'The story about the fox and grapes ...
# ```
