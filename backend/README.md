# AMS2 Delta - Backend API

Backend FastAPI para o AMS2 Delta v2.0 (web app moderno).

## Setup

### Windows
```bash
cd backend
start.bat
```

### Linux/Mac
```bash
cd backend
chmod +x start.sh
./start.sh
```

## Endpoints

Acesse http://localhost:8000/docs para documentação interativa (Swagger).

### Sessões
- `GET /sessions` - lista todas as sessões
- `GET /sessions/{id}` - detalhes de uma sessão
- `GET /sessions/{id}/laps/{lap}/telemetry` - telemetria de uma volta

### Análise
- `POST /analysis/ai` - análise com IA (Ollama ou Claude)
- `GET /analysis/{id}/delta/{lap1}/{lap2}` - delta entre voltas

## Estrutura

```
backend/
├── app/
│   ├── routers/        - endpoints HTTP
│   ├── services/       - lógica de negócio
│   └── models/         - schemas Pydantic
├── main.py            - FastAPI app
├── requirements.txt
└── start.bat/sh       - scripts de inicialização
```

## Desenvolvimento

O backend reutiliza 100% do código de análise do projeto original (`ams2_delta/`).
O link simbólico em `../shared/ams2_delta/` aponta pro código original.

## Testing

Acesse http://localhost:8000/docs e teste os endpoints diretamente no Swagger UI.
