from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from elenchos import __version__
from elenchos.benchmarks import BenchmarkNotFoundError, format_suite_error
from elenchos.benchmarks.schema import SuiteValidationError
from elenchos.web.routers import benchmarks, providers, runs


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


def create_app() -> FastAPI:
    app = FastAPI(
        title="Elenchos",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url="/api/redoc",
    )
    _register_exception_handlers(app)

    api = APIRouter(prefix="/api")

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    api.include_router(providers.router)
    api.include_router(benchmarks.router)
    api.include_router(runs.router)

    app.include_router(api)
    return app


app = create_app()
