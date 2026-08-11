from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from structlog.contextvars import bind_contextvars

from .agent import LabAgent
from .audit import write_audit_event
from .incidents import disable, enable, status
from .logging_config import configure_logging, get_logger
from .metrics import record_error, snapshot
from .middleware import CorrelationIdMiddleware
from .pii import hash_user_id, summarize_text
from .runtime_config import set_cost_optimization, snapshot as runtime_config_snapshot
from .schemas import ChatRequest, ChatResponse, CostOptimizationRequest
from .tracing import tracing_enabled

configure_logging()
log = get_logger()
app = FastAPI(title="Day 13 Observability Lab")
app.add_middleware(CorrelationIdMiddleware)
agent = LabAgent()


@app.on_event("startup")
async def startup() -> None:
    log.info(
        "app_started",
        service=os.getenv("APP_NAME", "day13-observability-lab"),
        correlation_id="system",
        env=os.getenv("APP_ENV", "dev"),
        payload={"tracing_enabled": tracing_enabled()},
    )


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "tracing_enabled": tracing_enabled(),
        "incidents": status(),
        "runtime_config": runtime_config_snapshot(),
    }


@app.get("/metrics")
async def metrics() -> dict:
    return snapshot()


@app.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    bind_contextvars(
        user_id_hash=hash_user_id(body.user_id),
        session_id=body.session_id,
        feature=body.feature,
        model=agent.model,
        env=os.getenv("APP_ENV", "dev"),
    )

    log.info(
        "request_received",
        service="api",
        payload={"message_preview": summarize_text(body.message)},
    )
    try:
        result = agent.run(
            user_id=body.user_id,
            feature=body.feature,
            session_id=body.session_id,
            message=body.message,
        )
        log.info(
            "response_sent",
            service="api",
            latency_ms=result.latency_ms,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_usd=result.cost_usd,
            quality_score=result.quality_score,
            payload={"answer_preview": summarize_text(result.answer)},
        )
        return ChatResponse(
            answer=result.answer,
            correlation_id=request.state.correlation_id,
            latency_ms=result.latency_ms,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_usd=result.cost_usd,
            quality_score=result.quality_score,
        )
    except Exception as exc:  # pragma: no cover
        error_type = type(exc).__name__
        record_error(error_type)
        log.error(
            "request_failed",
            service="api",
            error_type=error_type,
            payload={"detail": str(exc), "message_preview": summarize_text(body.message)},
        )
        raise HTTPException(status_code=500, detail=error_type) from exc


@app.post("/incidents/{name}/enable")
async def enable_incident(request: Request, name: str) -> JSONResponse:
    try:
        enable(name)
        write_audit_event(
            "incident_enabled",
            correlation_id=request.state.correlation_id,
            payload={"name": name},
        )
        log.warning("incident_enabled", service="control", payload={"name": name})
        return JSONResponse({"ok": True, "incidents": status()})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/incidents/{name}/disable")
async def disable_incident(request: Request, name: str) -> JSONResponse:
    try:
        disable(name)
        write_audit_event(
            "incident_disabled",
            correlation_id=request.state.correlation_id,
            payload={"name": name},
        )
        log.warning("incident_disabled", service="control", payload={"name": name})
        return JSONResponse({"ok": True, "incidents": status()})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/config/cost-optimization")
async def get_cost_optimization() -> dict:
    return {"ok": True, "cost_optimization": runtime_config_snapshot()}


@app.post("/config/cost-optimization")
async def update_cost_optimization(
    request: Request, body: CostOptimizationRequest
) -> JSONResponse:
    try:
        config = set_cost_optimization(
            enabled=body.enabled,
            max_output_tokens=body.max_output_tokens,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    write_audit_event(
        "config_changed",
        correlation_id=request.state.correlation_id,
        payload={"setting": "cost_optimization", **config},
    )
    log.info("config_changed", service="control", payload={"setting": "cost_optimization", **config})
    return JSONResponse({"ok": True, "cost_optimization": config})
