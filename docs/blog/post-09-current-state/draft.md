# MONITOR hoy: qué funciona, qué falta, y qué viene

*Cuarta y última parte de la serie (por ahora). Estado real del sistema en junio de 2026.*

---

Esta es la parte donde sería fácil terminar con una lista de features impresionantes y una promesa de que todo está casi listo. No voy a hacer eso.

MONITOR es un proyecto funcional con deuda técnica, casos borde sin cubrir, y flujos que todavía están a medio terminar. También es el sistema más ambicioso que he construido, y hay partes que funcionan mejor de lo que esperaba. Las dos cosas son verdad al mismo tiempo.

---

## Lo que funciona hoy

### La interfaz web

El modo de juego principal es una interfaz web: chat con el GM, gestión de personajes, visualización del estado de la escena. El backend corre en FastAPI, el frontend en Next.js.

No es bonita todavía. Pero es funcional — puedes crear un universo, ingestar documentos, iniciar una sesión, y jugar turnos completos con el sistema como GM.

### Los comandos CLI

Ocho grupos de comandos disponibles:

```bash
monitor play        # iniciar o continuar una historia
monitor manage      # gestionar entidades (NPCs, lugares, objetos)
monitor universe    # crear y administrar universos
monitor ingest      # ingestar documentos al world knowledge base
monitor state       # estado del personaje (HP, recursos)
monitor rules       # gestionar sistemas de juego
monitor mechanics   # resolver mecánicas (tiradas, checks)
monitor playtest    # correr sesiones de prueba automatizadas
```

### La capa de datos MCP

Cuatro familias de herramientas MCP activas: `neo4j_*`, `mongodb_*`, `qdrant_*`, `ingest_*`. Los agentes las llaman de forma asíncrona para leer y escribir datos sin acoplarse directamente a los clientes de base de datos.

El cumplimiento de las capas arquitectónicas se aplica despiadadamente. Si abres `packages/cli/src/monitor_cli/commands/play.py`, el *docstring* inicial lo deja claro:
```python
"""
MONITOR Play — Solo Play interactive REPL.

LAYER: 3 (cli)
IMPORTS FROM: monitor_agents (Layer 2)
NEVER IMPORTS: monitor_data (Layer 1)
"""
```


### Las pruebas

Aproximadamente 5.900 tests en el suite completo. Los tests unitarios y de integración corren sin red ni claves de API — todo mockeado. Los e2e requieren el stack completo levantado.

```bash
uv run pytest packages tests -q          # ~5900 tests, < 6 minutos
RUN_E2E=1 uv run pytest tests/e2e -q    # full stack e2e
```

### El playtest con LLM como jugador

El indicador más confiable del estado del sistema: corremos sesiones donde un segundo LLM hace de jugador y vemos si la sesión se sostiene de principio a fin.

Los logs de esas sesiones están en `tests/e2e/logs/`. El más reciente fue una sesión de 13 entradas, `player_mode: llm`, cero fallbacks, cero preguntas de clarificación del GM. La narración es coherente. El estado del mundo se actualiza correctamente. Los dados ruedan cuando corresponde.

---

## Lo que falta

Lo que más me frustra hoy no es la arquitectura, es la **latencia**. Cuando el jugador declara una acción compleja, el sistema tiene que armar el contexto, pedirle un veredicto al GMAgent, resolver las mecánicas, y luego generar la prosa final. Son múltiples llamadas a modelos grandes en serie. Técnicamente funciona impecable y el estado queda inmaculado. Pero desde que aprietas 'Enter' hasta que lees la respuesta pueden pasar 10 segundos o más. En una mesa real, el GM te responde al instante. Esa pausa te saca inevitablemente de la ficción.

Algunos puntos concretos del estado actual:

**El modo Co-Pilot está incompleto.** La arquitectura para que el sistema asista a un GM humano — tomando notas de sesión, detectando contradicciones, sugiriendo hooks — está diseñada y parcialmente implementada. Pero no hay un flujo de usuario pulido todavía.

**La UI necesita trabajo.** El chat funciona. La gestión de personajes funciona. La visualización del grafo de mundo está básica. Todo lo que tiene que ver con World Design — construir un universo desde cero, gestionar la ontología, revisar entidades propuestas — vive mayoritariamente en CLI.

**La ingesta de documentos es frágil con PDFs complejos.** PDFs bien estructurados (columna única, texto limpio) ingestán bien. Manuales con múltiples columnas, tablas complejas o mucho texto en imágenes todavía dan problemas.

**El CanonKeeper necesita más políticas de evaluación.** Hoy detecta contradicciones directas. No detecta todavía inconsistencias más sutiles — implicaciones lógicas que se contradicen, cambios de estado que son imposibles dado el historial.

---

## Lo que aprendí en el proceso

Lo más difícil no fue hacer que los LLMs escribieran buena prosa. Fue hacer que dejaran de escribir.

Al principio perdí semanas enteras intentando arreglar los problemas de consistencia afinando los *system prompts*. "No inventes NPCs". "Usa solo las reglas del manual". No sirve. El modelo es un motor estocástico diseñado para predecir la siguiente palabra, no una base de datos relacional. 

Si empezara de nuevo, no perdería ni un solo día en *prompt engineering* para control de estado. Construiría la barrera del CanonKeeper y la arquitectura de herramientas desde el día uno. Las reglas duras se resuelven en Python. La prosa y la interpretación de intención se delegan al LLM. Cuando separé esas dos cosas —el razonamiento determinista por un lado, y la generación estocástica por el otro— el sistema empezó a funcionar de verdad.

## Qué viene

El roadmap inmediato tiene dos prioridades:

**Primero, el modo Co-Pilot.** Es el que tiene el caso de uso más claro para alguien que ya dirige juegos — tener un asistente que recuerda todo lo que pasó en la campaña, detecta inconsistencias, y te avisa cuando la historia se está enredando. No requiere que el jugador ceda el control narrativo.

**Segundo, la UI de World Design.** El modelo de datos para construir mundos es sólido. Lo que falta es una interfaz que haga ese proceso accesible sin tener que escribir comandos CLI.

A largo plazo, lo que más me interesa explorar es el modelo de universos paralelos — la capacidad de tomar un mundo existente, divergirlo en un punto histórico específico, y explorar qué hubiera pasado si una decisión clave hubiera sido diferente. La arquitectura ya lo soporta. El flujo de usuario no existe todavía.

---

## Cierre

MONITOR es un proyecto que empezó con una pregunta simple: ¿puedo construir un sistema que recuerde un mundo y lo narre sin inventarse cosas?

La respuesta, después de varios años y muchas capas de arquitectura, es: sí, con condiciones. El sistema recuerda. No inventa (o cuando lo intenta, hay una barrera que lo detiene). Y puede narrar con una calidad que todavía me sorprende a veces cuando leo los logs de las sesiones de prueba.

Falta mucho. Pero es un proyecto vivo, y eso es suficiente por ahora.

Construir MONITOR me enseñó que la mejor manera de entender realmente cómo funciona la inteligencia artificial generativa no es hacerle preguntas ingeniosas en una ventana de chat. Es intentar acoplarla a una base de datos estricta y forzarla a respetar sus reglas.

Es un proyecto personal inmenso, y probablemente nunca esté "terminado" del todo. Pero cada vez que leo el log de una sesión automatizada donde el sistema aplica una regla oscura de *City of Mist* perfectamente, sin que nadie haya programado esa mecánica a mano... sé que el esfuerzo técnico valió la pena.

*Si llegaste hasta acá y te interesa seguir el desarrollo, el repositorio es público: [github.com/spuentesp/monitor_dm_system](https://github.com/spuentesp/monitor_dm_system)*
