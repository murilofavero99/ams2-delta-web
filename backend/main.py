"""
FastAPI backend para AMS2 Delta.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import sessions, analysis

app = FastAPI(
    title="AMS2 Delta API",
    description="Backend para análise de telemetria do Automobilista 2",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://ams2-delta-web-n8f4.vercel.app",
    ],
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
