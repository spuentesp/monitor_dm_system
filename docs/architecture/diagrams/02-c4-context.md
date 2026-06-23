# 02 — C4 Contexto (Nivel 1)

> Diagrama de contexto del sistema según el modelo C4.
> Muestra MONITOR como caja negra, sus usuarios y sus dependencias externas.

## Descripción

**Alcance**: Una sola caja "MONITOR" con:
- **3 tipos de usuario**: Jugador (solo play), Game Master (asistido), World Architect (creación/ingesta)
- **4 dependencias externas**: APIs de LLM (OpenAI, Anthropic, Gemini) + modelos locales vía LiteLLM

Este es el punto de entrada para cualquier stakeholder que quiera entender
qué hace el sistema y con qué interactúa.

## Diagrama

```mermaid
graph TB
    PLAYER["👤 Jugador\nJuega campañas solo\nToma decisiones narrativas\nModo: Autonomous GM"]
    GM["👤 Game Master\nDirige partidas humanas\nUsa MONITOR como asistente\nModo: GM Assistant"]
    ARCHITECT["👤 World Architect\nCrea y mantiene mundos\nIngesta documentos de setting\nModo: World Architect"]

    MONITOR["🎲 MONITOR\nSistema de Inteligencia Narrativa\nMulti-Ontología · Multi-Agente\n12 agentes · 6 loops · 5 DBs"]

    LLM_OPENAI["OpenAI API\nGPT-4, GPT-4o"]
    LLM_ANTHROPIC["Anthropic API\nClaude 3.5, Claude 4"]
    LLM_GEMINI["Google Gemini API"]
    LLM_LOCAL["Modelos Locales\n(via LiteLLM)"]

    PLAYER -->|"juega, interactúa\nrecibe narrativa"| MONITOR
    GM -->|"consulta, registra\nrecibe asistencia"| MONITOR
    ARCHITECT -->|"crea mundos\ningesta PDFs/EPUBs"| MONITOR

    MONITOR -->|"llamadas LLM\nDSPy + instructor"| LLM_OPENAI
    MONITOR -->|"llamadas LLM\nDSPy + instructor"| LLM_ANTHROPIC
    MONITOR -->|"llamadas LLM\nDSPy + instructor"| LLM_GEMINI
    MONITOR -->|"llamadas LLM\nDSPy + instructor"| LLM_LOCAL

    classDef person fill:#08427b,stroke:#052e56,color:#fff
    classDef system fill:#1168bd,stroke:#0b4884,color:#fff
    classDef external fill:#999,stroke:#666,color:#fff

    class PLAYER,GM,ARCHITECT person
    class MONITOR system
    class LLM_OPENAI,LLM_ANTHROPIC,LLM_GEMINI,LLM_LOCAL external
```
