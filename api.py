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

import gtm
import rag
import store
from action import generate_action_plan, simulate_impact
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


@app.get("/gtm")
def gtm_studio() -> FileResponse:
    return FileResponse(WEB_DIR / "gtm.html")


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
    status = row["status"] or "done"
    out = {"brand_id": brand_id, "status": status, "error_message": row["error_message"]}
    # Attach live counts while the run is in flight so the UI can show the real
    # procedure (panel size, answers collected, answers parsed) as it happens.
    if status in ("pending", "generating", "probing", "parsing"):
        try:
            out["progress"] = store.get_progress(brand_id)
        except Exception:
            pass
    return out


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


class GtmPlanRequest(BaseModel):
    idea: str


class GtmLandingRequest(BaseModel):
    idea: str
    plan: dict


@app.post("/api/gtm/plan")
def gtm_plan(req: GtmPlanRequest) -> dict:
    """Strategist agent: a founder's idea -> a structured GTM plan."""
    idea = (req.idea or "").strip()
    if not idea:
        raise HTTPException(status_code=400, detail="describe your startup first")
    return {"plan": gtm.generate_gtm_plan(idea)}


@app.post("/api/gtm/landing")
def gtm_landing(req: GtmLandingRequest) -> dict:
    """Designer agent: idea + plan -> a self-contained landing page (HTML)."""
    return {"html": gtm.generate_landing_html(req.idea, req.plan)}


def _audit_evidence(agg: dict) -> str:
    """Distill a brand's real audit into a compact evidence brief the build
    agents can ground in: who wins, the sources AI cites, the language owned and
    the language the brand is missing. All measured, nothing invented."""
    lines = []
    comps = [c["brand"] for c in (agg.get("competitors") or [])[:5]]
    if comps:
        lines.append("Brands AI recommends in this category: " + ", ".join(comps))
    srcs = [s["domain"] for s in (agg.get("provenance") or {}).get("top_sources", [])][:6]
    if srcs:
        lines.append("Sources AI cites most here: " + ", ".join(srcs))
    lex = agg.get("lexical") or {}
    you = [x["term"] for x in lex.get("you_own", [])][:8]
    they = [x["term"] for x in lex.get("they_own", [])][:8]
    if you:
        lines.append("Language AI already associates with you: " + ", ".join(you))
    if they:
        lines.append("Language competitors own that you don't: " + ", ".join(they))
    return "\n".join(lines)


class BuildRequest(BaseModel):
    mode: str  # "landing" | "gtm"


@app.post("/api/brands/{brand_id}/build")
def build_asset(brand_id: int, req: BuildRequest) -> dict:
    """Action layer: generate a grounded asset for a measured brand. The GTM
    strategist / landing designer are fed the brand's real audit so the output
    targets what AI demonstrably rewards in this category, not generic copy."""
    row = store.get_brand(brand_id)
    if row is None:
        raise HTTPException(status_code=404, detail="brand not found")
    agg = store.aggregate_brand(brand_id)
    evidence = _audit_evidence(agg)
    idea = f"{row['name']} — a brand in {row['category']}"
    plan = gtm.generate_gtm_plan(idea, evidence=evidence or None)
    if req.mode == "gtm":
        return {"mode": "gtm", "plan": plan, "evidence": evidence}
    if req.mode == "landing":
        html = gtm.generate_landing_html(idea, plan, evidence=evidence or None)
        return {"mode": "landing", "plan": plan, "html": html}
    raise HTTPException(status_code=400, detail="mode must be 'landing' or 'gtm'")


class SimulateRequest(BaseModel):
    brand_id: int
    content: str


@app.post("/api/simulate")
def simulate(req: SimulateRequest) -> dict:
    """Estimate the impact of a proposed change: inject the content and re-probe a
    sample of the brand's panel queries. An estimate, not causal proof."""
    row = store.get_brand(req.brand_id)
    if row is None:
        raise HTTPException(status_code=404, detail="brand not found")
    queries = store.get_queries_sample(req.brand_id, 6)
    if not queries:
        raise HTTPException(status_code=400, detail="no panel queries to simulate against")
    baseline = (store.aggregate_brand(req.brand_id) or {}).get("mention_rate", 0)
    sim = simulate_impact(row["name"], row["category"], req.content, queries)
    return {
        "baseline_rate": baseline,
        "simulated_rate": sim["simulated_rate"],
        "n": sim["n"],
        "note": "Estimate: the content is injected as trusted facts and a sample is re-asked; "
                "not a live re-crawl of the real engines.",
    }


# --- static assets (mounted last so it doesn't shadow routes above) ---------

app.mount("/", StaticFiles(directory=WEB_DIR), name="static")
