import json

import replicate

REPLICATE_API_KEY = "r8_Zw5bOTnKa2xhtWLQGKOrVmJUSDvWJTC0vRDkY"
client = replicate.Client(api_token=REPLICATE_API_KEY)
outputs = client.run(
    "replicate/all-mpnet-base-v2:b6b7585c9640cd7a9572c6e129c9549d79c9c31f0d3fdce7baac7c67ca38f305",
    input={"text_batch": json.dumps(["test1", "test2"])},
)
print([len(output["embedding"]) for output in outputs])
