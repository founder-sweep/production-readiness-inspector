"""Synthetic static-analysis fixture; never run by Inspector."""
from fastapi import FastAPI
import uvicorn

app = FastAPI(debug=True)


def health():
    # A function name alone does not register an HTTP route.
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, reload=True)
