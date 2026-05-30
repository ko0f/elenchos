"""Serve built frontend assets from the installed package."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def static_root() -> Path:
    return Path(__file__).resolve().parent / "static"


def has_built_ui(static_dir: Path | None = None) -> bool:
    root = static_dir or static_root()
    return (root / "index.html").is_file()


def _safe_static_file(root: Path, full_path: str) -> Path | None:
    if not full_path:
        return None
    candidate = (root / full_path).resolve()
    root_resolved = root.resolve()
    if not candidate.is_relative_to(root_resolved):
        return None
    return candidate if candidate.is_file() else None


def mount_ui(app: FastAPI, static_dir: Path | None = None) -> bool:
    """Mount built SPA assets. Returns True when static files are available."""
    root = static_dir or static_root()
    index = root / "index.html"
    if not index.is_file():
        return False

    assets_dir = root / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="ui-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not Found")
        safe = _safe_static_file(root, full_path)
        if safe is not None:
            return FileResponse(safe)
        return FileResponse(index)

    return True
