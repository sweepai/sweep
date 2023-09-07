from fastapi import FastAPI, Request, HTTPException
from starlette.responses import Response, JSONResponse, HTMLResponse
import httpx

app = FastAPI()

TARGET_SERVER = (
    "http://0.0.0.0:8080"  # Replace with the URL of the server you want to forward to
)


@app.middleware("http")
async def reroute_request(request: Request, call_next):
    async with httpx.AsyncClient() as client:
        # Capture original request data
        data = await request.body()
        headers = dict(request.headers)

        # Exclude certain headers to avoid issues with forwarding
        exclude_headers = ["host", "connection", "accept-encoding"]
        for header in exclude_headers:
            headers.pop(header, None)

        try:
            # Forward the request to the target server
            response = await client.request(
                request.method,
                f"{TARGET_SERVER}{request.url.path}",
                data=data,
                headers=headers,
                params=request.query_params,
            )

            content_type = response.headers.get("content-type")

            # Depending on the content type, wrap the bytes response in an appropriate FastAPI response class
            if "json" in content_type:
                return JSONResponse(content=response.json())
            elif "html" in content_type:
                return HTMLResponse(content=response.text)
            else:
                return Response(content=response.content, media_type=content_type)

        except httpx.RequestError as exc:
            raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
