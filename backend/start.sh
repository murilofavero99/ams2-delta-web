#!/bin/bash

echo "=========================================="
echo "  AMS2 Delta - Backend API"
echo "=========================================="
echo ""

cd "$(dirname "$0")"

# Verifica se tem venv
if [ ! -d "venv" ]; then
    echo "Criando ambiente virtual..."
    python3 -m venv venv
fi

source venv/bin/activate

# Instala dependências
echo "Instalando dependências..."
pip install -q -r requirements.txt

# Inicia servidor
echo ""
echo "Iniciando servidor FastAPI em http://localhost:8000"
echo "Documentação: http://localhost:8000/docs"
echo ""
echo "Pressione Ctrl+C para parar"
echo ""

uvicorn main:app --reload --host 0.0.0.0 --port 8000
