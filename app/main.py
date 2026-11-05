from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import make_session_factory
from .hub import Monitor
from .llm import LLMError, get_llm
from .routes import router
from .ws_monitor import router as ws_router

DIST = Path(__file__).parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if getattr(app.state, "monitor", None) is None:  # tests put their own in place first
        app.state.monitor = Monitor(make_session_factory(settings.database_url), get_llm)
    yield
    await app.state.monitor.shutdown()


app = FastAPI(
    title="qa-scoring-dashboard",
    description="Score support calls against a rubric as they happen, and let supervisors watch live.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(ws_router)


@app.exception_handler(LLMError)
async def llm_error(_: Request, exc: LLMError):
    return JSONResponse(status_code=502, content={"detail": f"The language model failed: {exc}"})


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


# the built React app, if it has been built (cd frontend && npm run build)
if (DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(DIST / "index.html")
