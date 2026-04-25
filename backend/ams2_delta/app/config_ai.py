"""
Configuração de APIs de IA para análise.

Usuário escolhe qual modelo usar na interface.
Chave da API é pedida na interface (não é guardada em disco por segurança).
"""

# Modelos disponíveis
MODELS = {
    "ollama": {
        "name": "Ollama (Grátis)",
        "description": "Mistral 7B rodando localmente no seu PC. Offline, sem custo.",
        "requires_key": False,
        "speed": "30-60s",
        "quality": "Bom (70%)",
    },
    "claude": {
        "name": "Claude 3.5 Sonnet (Premium)",
        "description": "Anthropic Claude via API. Feedback de qualidade profissional, mais rápido.",
        "requires_key": True,
        "speed": "5-10s",
        "quality": "Excelente (100%)",
        "cost_estimate": "~R$ 0.10–0.15 por análise",
    },
}

# Endpoints
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"
CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
