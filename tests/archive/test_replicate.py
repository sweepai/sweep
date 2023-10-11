import json

import replicate

REPLICATE_API_KEY = "r8_Zw5bOTnKa2xhtWLQGKOrVmJUSDvWJTC0vRDkY"
client = replicate.Client(api_token=REPLICATE_API_KEY)
deployment = client.deployments.get("sweepai/all-mpnet-base-v2")
prediction = deployment.predictions.create(
    input={"text_batch": json.dumps(["Hello world!"])}
)
prediction.wait()
print([output["embedding"] for output in prediction.output])
