from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.routes import admin, api, health, twilio_sms, twilio_voice

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="Maya SMS Relay")
    app.include_router(health.router)
    app.include_router(twilio_sms.router)
    app.include_router(twilio_voice.router)
    app.include_router(api.router)
    app.include_router(admin.router)

    @app.get("/", include_in_schema=False)
    def root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/app", status_code=307)

    if FRONTEND_DIST.exists():
        assets_dir = FRONTEND_DIST / "assets"
        if assets_dir.exists():
            app.mount("/app/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

        @app.get("/app", include_in_schema=False)
        @app.get("/app/{path:path}", include_in_schema=False)
        def frontend_app(path: str = "") -> FileResponse:
            return FileResponse(FRONTEND_DIST / "index.html")

        @app.get("/proof/{path:path}", include_in_schema=False)
        def frontend_public_proof(path: str) -> FileResponse:
            return FileResponse(FRONTEND_DIST / "index.html")

        @app.get("/assets/{path:path}", include_in_schema=False)
        def frontend_public_assets(path: str) -> FileResponse:
            return FileResponse(FRONTEND_DIST / "index.html")

        @app.get("/reset-password", include_in_schema=False)
        def frontend_reset_password() -> FileResponse:
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()
