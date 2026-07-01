from fastapi import FastAPI

from api_gateway.routes import leads

app = FastAPI()

app.include_router(leads.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
