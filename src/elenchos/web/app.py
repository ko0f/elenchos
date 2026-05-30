from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from elenchos import __version__
from elenchos.benchmarks import BenchmarkNotFoundError, format_suite_error
from elenchos.benchmarks.schema import SuiteValidationError
from elenchos.compare import CompareError
from elenchos.console import setup_logging
from elenchos.reporter import ReportError
from elenchos.runner import SuiteRunError
from elenchos.web.routers import benchmarks, compare, jobs, providers, runs
from elenchos.web.static_files import has_built_ui, mount_ui, static_root

VITE_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BenchmarkNotFoundError)
    async def benchmark_not_found(
        _request: Request,
        exc: BenchmarkNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(SuiteValidationError)
    async def suite_validation_error(
        _request: Request,
        exc: SuiteValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": format_suite_error(exc)},
        )

    @app.exception_handler(SuiteRunError)
    async def suite_run_error(
        _request: Request,
        exc: SuiteRunError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(CompareError)
    async def compare_error(
        _request: Request,
        exc: CompareError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(ReportError)
    async def report_error(
        _request: Request,
        exc: ReportError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})


def create_app(
    *,
    static_dir: Path | None = None,
    enable_dev_cors: bool | None = None,
) -> FastAPI:
    resolved_static = static_dir or static_root()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        setup_logging()
        yield

    app = FastAPI(
        title="Elenchos",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url="/api/redoc",
        lifespan=lifespan,
    )
    _register_exception_handlers(app)

    ui_available = has_built_ui(resolved_static)
    if enable_dev_cors is None:
        enable_dev_cors = not ui_available

    if enable_dev_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=VITE_DEV_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    api = APIRouter(prefix="/api")

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    api.include_router(providers.router)
    api.include_router(benchmarks.router)
    api.include_router(runs.router)
    api.include_router(jobs.router)
    api.include_router(compare.router)

    app.include_router(api)
    mount_ui(app, resolved_static)
    return app


app = create_app()
