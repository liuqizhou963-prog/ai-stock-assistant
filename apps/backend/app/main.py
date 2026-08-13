from fastapi import FastAPI

app = FastAPI(title="Desktop Agent Backend")


@app.get("/health")
def health() -> dict[str, str]:
    return {"service": "desktop-agent-backend", "status": "ok"}
