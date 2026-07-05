from fastapi import FastAPI

from app.api.v1.router import router as api_router

app = FastAPI(title="MaxVPN API", version="0.1.0")

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def root():
    return {"project": "MaxVPN", "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}
