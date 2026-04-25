"""
FastAPI backend para AMS2 Delta.

Endpoints:
  GET /sessions - lista sessões
  GET /sessions/{id} - detalhes
  GET /sessions/{id}/laps/{lap}/telemetry - telemetria
  POST /analysis/ai - análise com IA
  GET /analysis/{id}/delta/{lap1}/{lap2} - delta
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import sessions, analysis

app = FastAPI(
    title="AMS2 Delta API",
    description="Backend para análise de telemetria do Automobilista 2",
    version="2.0.0",
)

# CORS - permite frontend local e produção
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # React dev alternativo
        "https://ams2-delta.vercel.app",  # produção (ajustar depois)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registra routers
app.include_router(sessions.router)
app.include_router(analysis.router)


@app.get("/")
async def root():
    """Health check."""
    return {
        "status": "ok",
        "service": "AMS2 Delta API",
        "version": "2.0.0",
    }


@app.get("/health")
async def health():
    """Health check detalhado."""
    return {
        "status": "healthy",
        "database": "ok",  # placeholder
        "ollama": "unknown",  # poderia checar se está rodando
    }
