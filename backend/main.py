"""
FastAPI backend para AMS2 Delta.
"""
import os
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import sessions, analysis


# ─── CORS dinâmico: aceita qualquer deploy da Vercel do projeto ───
ALLOWED_ORIGIN_PATTERNS = [
    re.compile(r"^https://ams2-delta-.*\.vercel\.app$"),
    re.compile(r"^https://ams2-delta-web.*\.vercel\.app$"),
]

STATIC_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://ams2-delta-web-n8f4.vercel.app",
]


def is_origin_allowed(origin: str) -> bool:
    if origin in STATIC_ORIGINS:
        return True
    return any(p.match(origin) for p in ALLOWED_ORIGIN_PATTERNS)


app = FastAPI(
    title="AMS2 Delta API",
    description="Backend para análise de telemetria do Automobilista 2",
    version="2.0.0",
)

# CORS com wildcard pra Vercel (os patterns acima filtram)
app.add_middleware(
    CORSMiddleware,
    allow_origins=STATIC_ORIGINS,
    allow_origin_regex=r"https://ams2-delta.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(analysis.router)


@app.get("/")
async def root():
    return {"status": "ok", "service": "AMS2 Delta API", "version": "2.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
