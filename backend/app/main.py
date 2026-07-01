from fastapi import FastAPI

app = FastAPI(
    title="MaxVPN API",
    version="0.1.0"
)

@app.get("/")
def root():
    return {
        "project": "MaxVPN",
        "status": "running"
    }

@app.get("/health")
def health():
    return {
        "status": "ok"
    }