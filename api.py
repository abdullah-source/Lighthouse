"""
api.py - FastAPI backend + premium frontend.

Run:
    .venv/bin/uvicorn api:app --reload --port 8000
Then open http://localhost:8000  (landing)  /  http://localhost:8000/app  (product)

Routes:
    GET  /                          -> marketing landing (web/index.html)
    GET  /app                       -> product dashboard (web/app.html)
    GET  /api/config                -> { clerk_enabled, clerk_publishable_key }
    GET  /api/brands                -> list audited brands + headline metric
    POST /api/audits                -> start a new audit {brand, category}
    GET  /api/brands/{id}           -> full dashboard payload (normalized)
    GET  /api/brands/{id}/status    -> {status} for polling
    POST /api/recommendations/generate -> publish-ready action artifact (the wedge)

The audit runs in a background thread; the frontend polls status until 'done'.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import rag
import store
from action import generate_action_plan
from audit import run_audit
from config import CLERK_ENABLED, CLERK_PUBLISHABLE_KEY, require_api_keys

WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(title="GEO Brand Visibility", version="1.0")


@app.on_event("startup")
def _startup() -> None:
    store.migrate()
    require_api_keys()


# --- pages ------------------------------------------------------------------

@app.get("/")
def landing() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/app")
def product() -> FileResponse:
    return FileResponse(WEB_DIR / "app.html")


@app.get("/api/config")
def get_config() -> dict:
    return {
        "clerk_enabled": CLERK_ENABLED,
        "clerk_publishable_key": CLERK_PUBLISHABLE_KEY,
    }


# --- audits -----------------------------------------------------------------

class AuditRequest(BaseModel):
    brand: str
    category: str
    context: str | None = None       # optional first-party context → grounded panel
    competitor: str | None = None    # optional rival to benchmark against


class GenerateRequest(BaseModel):
    brand_id: int
    competitor: str | None = None
    query: str | None = None


class AskRequest(BaseModel):
    question: str


@app.get("/api/brands")
def list_brands() -> list[dict]:
    return store.list_brands()


@app.post("/api/audits")
def start_audit(req: AuditRequest, background: BackgroundTasks) -> dict:
    brand = req.brand.strip()
    category = req.category.strip()
    if not brand or not category:
        raise HTTPException(status_code=400, detail="brand and category are required")
    context = (req.context or "").strip() or None
    competitor = (req.competitor or "").strip() or None
    brand_id = store.create_brand(brand, category, competitor)
    background.add_task(run_audit, brand_id, brand, category, context)
    return {"brand_id": brand_id, "status": "pending"}


@app.post("/api/brands/{brand_id}/cancel")
def cancel_audit(brand_id: int) -> dict:
    """Cancel/kill a run: remove the brand and its rows. The background task
    aborts on the next write (missing FK)."""
    row = store.get_brand(brand_id)
    if row is None:
        raise HTTPException(status_code=404, detail="brand not found")
    store.delete_brand(brand_id)
    return {"ok": True}


@app.get("/api/brands/{brand_id}")
def get_brand(brand_id: int) -> dict:
    row = store.get_brand(brand_id)
    if row is None:
        raise HTTPException(status_code=404, detail="brand not found")
    status = row["status"] or "done"
    if status != "done":
        return {"brand_id": brand_id, "name": row["name"], "category": row["category"],
                "status": status, "error_message": row["error_message"]}
    return store.aggregate_brand(brand_id)


@app.get("/api/brands/{brand_id}/status")
def get_status(brand_id: int) -> dict:
    row = store.get_brand(brand_id)
    if row is None:
        raise HTTPException(status_code=404, detail="brand not found")
    return {"brand_id": brand_id, "status": row["status"] or "done", "error_message": row["error_message"]}


@app.post("/api/brands/{brand_id}/ask")
def ask(brand_id: int, req: AskRequest) -> dict:
    """RAG Q&A over the brand's own indexed context."""
    row = store.get_brand(brand_id)
    if row is None:
        raise HTTPException(status_code=404, detail="brand not found")
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    return rag.answer(brand_id, question)


@app.post("/api/recommendations/generate")
def generate(req: GenerateRequest) -> dict:
    row = store.get_brand(req.brand_id)
    if row is None:
        raise HTTPException(status_code=404, detail="brand not found")
    query = (req.query or "").strip() or store.get_sample_query(req.brand_id) or f"best {row['category']}"
    # Ground the action plan in the audit: the vibes the brand owns + the sources
    # the AI trusts. So content + schema target what actually drives recommendations.
    agg = store.aggregate_brand(req.brand_id)
    owned = [x["term"] for x in (agg.get("lexical") or {}).get("you_own", [])][:8]
    sources = [s["domain"] for s in (agg.get("provenance") or {}).get("top_sources", [])][:6]
    plan = generate_action_plan(
        brand=row["name"], category=row["category"], query=query,
        competitor=req.competitor, owned_vibes=owned, target_sources=sources,
    )
    plan["target_query"] = query
    plan["competitor"] = req.competitor
    return plan


# --- static assets (mounted last so it doesn't shadow routes above) ---------

app.mount("/", StaticFiles(directory=WEB_DIR), name="static")
