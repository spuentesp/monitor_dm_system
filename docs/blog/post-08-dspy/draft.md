# Deja de escribir prompts, empieza a escribir tipos: El uso de DSPy

Si has pasado más de una hora construyendo aplicaciones con modelos de lenguaje, conoces el dolor del *prompt engineering*. 

Empiezas con una instrucción simple: *"Eres un Game Master. Describe lo que pasa."*
Luego te das cuenta de que el modelo habla demasiado, así que agregas: *"Mantén tu respuesta en menos de 3 párrafos."*
Luego necesitas integrarlo con tu código Python, así que le ruegas: *"Por favor, responde SOLO en formato JSON. No uses bloques de markdown. Asegúrate de incluir la llave 'intent'."*

Eventualmente, tu *system prompt* es un monolito frágil de 2000 tokens de súplicas estocásticas. Y cuando cambias de modelo (digamos, de GPT-4 a Claude), todo se rompe, porque cada modelo reacciona distinto a tus súplicas.

Para construir MONITOR, donde docenas de agentes tienen que pasarse datos estructurados a la perfección para que el juego no colapse, rogarle al modelo no era una opción. Necesitaba que los LLMs se comportaran como funciones tipadas de Python. 

La solución fue **DSPy**.

## ¿Qué es DSPy?

[DSPy](https://github.com/stanfordnlp/dspy) es un framework desarrollado por Stanford que cambia fundamentalmente cómo interactúas con los LLMs. En lugar de escribir prompts a mano, defines **Signatures** (Firmas). 

Una firma es simplemente la declaración de qué variables entran (Inputs) y qué variables deben salir (Outputs). DSPy se encarga de compilar el prompt óptimo por debajo. 

## Tipado Estricto en MONITOR

Si revisas los directorios de los agentes en el código de MONITOR (por ejemplo, `packages/agents/src/monitor_agents/analyzer/`), notarás algo extraño: casi no hay "prompts" tradicionales. En su lugar, hay clases de Python fuertemente tipadas co-ubicadas con sus respectivos agentes.

Mira cómo se define el agente `Analyzer` (encargado de decidir si el jugador hizo algo que requiere tirar dados):

```python
import dspy

class ActionAnalyzer(dspy.Signature):
    """Analyzes player action and determines if it requires mechanical resolution based on the rules."""
    
    context = dspy.InputField(desc="Relevant facts, entities, and scene state")
    rules = dspy.InputField(desc="Relevant game mechanics extracted from Qdrant")
    player_action = dspy.InputField(desc="The raw declaration from the player")
    
    requires_roll = dspy.OutputField(desc="Boolean, true if the action has a chance of failure and requires dice")
    selected_mechanic = dspy.OutputField(desc="The mechanic_id to execute, if applicable")
    rationale = dspy.OutputField(desc="Why this decision was made")
```

No le estoy diciendo al LLM "piensa paso a paso y devuélveme un JSON". Simplemente defino el `InputField` y el `OutputField`. 

Cuando llamo a este agente usando nuestro motor interno `dspy_runtime`, DSPy genera dinámicamente un prompt estructurado, obliga al modelo a adherirse a la estructura, y si el modelo alucina y devuelve texto en lugar de un booleano en `requires_roll`, el framework puede auto-corregirse y pedirle que arregle el error de tipo.

## El fin de la "Ingeniería de Prompts"

La mayor ventaja de esta arquitectura es el agnosticismo de modelos. Cuando construí el `CanonKeeper`, usé GPT-4. Más tarde, quise ver si Claude 3.5 Sonnet era más rápido. Si hubiera usado prompts manuales, habría tenido que reescribirlos todos para ajustarlos a la "personalidad" de Claude. 

Con DSPy, solo cambié el motor en `dspy_context_for`. Las *Signatures* siguieron siendo exactamente las mismas. El framework se encargó de la adaptación.

Cuando aíslas el lenguaje natural del tipado estricto, los LLMs dejan de ser "chatbots mágicos" impredecibles y se convierten en módulos predecibles y compilables de tu arquitectura de software. Deja de escribir prompts. Empieza a escribir tipos.

---

### Referencias y Enlaces al Código
- **[analyzer.py](https://github.com/spuentesp/monitor_dm_system/blob/main/packages/agents/src/monitor_agents/analyzer/analyzer.py)**: El módulo donde implementamos las firmas de DSPy para el análisis estricto de intenciones.
- **[dspy_runtime.py](https://github.com/spuentesp/monitor_dm_system/blob/main/packages/agents/src/monitor_agents/dspy_runtime.py)**: El entorno base que inicializa el modelo subyacente.
- [Khattab et al. (Stanford NLP)](https://arxiv.org/abs/2310.03714): *DSPy: Compiling Declarative Language Model Calls into State-of-the-Art Pipelines*.
