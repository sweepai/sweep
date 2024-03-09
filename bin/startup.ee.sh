#!/bin/sh

echo PORT: ${PORT:-8079}
uvicorn ee.index:app --host 0.0.0.0 --port ${PORT:-8079} --workers 2
