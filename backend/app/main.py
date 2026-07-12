from fastapi import FastAPI

app = FastAPI(title="RepoPilot")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
