from fastapi import FastAPI

from app.routes import admin, api, health, twilio_sms


def create_app() -> FastAPI:
    app = FastAPI(title="Maya SMS Relay")
    app.include_router(health.router)
    app.include_router(twilio_sms.router)
    app.include_router(api.router)
    app.include_router(admin.router)
    return app


app = create_app()
