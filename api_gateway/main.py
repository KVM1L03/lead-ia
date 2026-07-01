from fastapi import FastAPI

from api_gateway.routes import approve, leads, status

app = FastAPI()

app.include_router(leads.router)
app.include_router(status.router)
app.include_router(approve.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
