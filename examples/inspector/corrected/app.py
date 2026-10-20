"""Corrected syntax fixture; a declaration does not prove runtime health."""
from fastapi import FastAPI

app = FastAPI(debug=False)


@app.get("/health")
def health():
    return {"ok": True}
