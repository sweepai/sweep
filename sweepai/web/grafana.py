from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prometheus_fastapi_instrumentator import Instrumentator

security = HTTPBearer()


def auth_metrics(credentials: HTTPAuthorizationCredentials = Security(security)):
    if credentials.scheme != "Bearer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authentication scheme.",
        )
    if credentials.credentials != "example_token":  # grafana requires authentication
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token."
        )
    return True


def add_grafana(app: FastAPI):
    Instrumentator().instrument(app).expose(
        app,
        should_gzip=False,
        endpoint="/metrics",
        include_in_schema=True,
        tags=["metrics"],
        dependencies=[Depends(auth_metrics)],
    )
