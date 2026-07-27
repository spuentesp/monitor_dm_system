# Construyendo MONITOR: La arquitectura detrás de un Game Master de IA

Llevo un buen tiempo construyendo algo llamado **MONITOR**: un sistema capaz de dirigir una campaña de rol de mesa completa con memoria persistente, narración coherente y reglas que se aplican de verdad, sin necesitar un ser humano al otro lado de la mesa.

Cualquiera puede abrir ChatGPT, decirle "Eres un Dungeon Master", y jugar un rato. Pero si lo has intentado, sabes que la ilusión se rompe rápido. El modelo olvida NPCs, inventa reglas que no existen, permite que tu personaje haga cosas imposibles, y termina filtrando los secretos de la trama porque no entiende la diferencia entre lo que *es verdad* y lo que *tú sabes*.

Para resolver eso, dejé de tratar a los LLMs como chatbots mágicos y empecé a tratarlos como componentes en una arquitectura de software determinista. 

MONITOR no es un *prompt* gigante. Es un motor impulsado por un grafo ontológico en Neo4j, bases de datos en MongoDB, un sistema de agentes en LangGraph, y código Python duro que tira dados reales.

Esta es la serie completa donde documento cómo construí el sistema, los problemas arquitectónicos que encontré, y por qué decidí hacerlo desde cero.

---

## Parte I: Los Fundamentos
Cómo pasamos de chats que alucinan a bases de datos estructuradas.

1. **[De mesas de juego de juegos de mesa (ha!) a Grados ontológicos: cómo empecé a construir un Game Master con IA](./post-01)**
   El problema estructural de la memoria en los LLMs y por qué un "mundo" narrativo se modela mejor como un Grafo Acíclico Dirigido (DAG).
2. **[El modelo ontológico y el sistema de agentes: cómo creció MONITOR](./post-02)**
   De un modelo en papel a Neo4j. La creación del `CanonKeeper` como una barrera contra alucinaciones y la distinción vital entre Arquetipos e Instancias.
3. **[La Arquitectura de Tres Capas: Por qué separar a los agentes de los datos](./post-03)**
   Por qué frameworks como AutoGen o CrewAI fracasan en juegos de rol. La necesidad de una máquina de estados estricta usando LangGraph.

## Parte II: Inmersión Técnica (Deep Dives)
Problemas específicos de ingeniería y cómo los resolvimos aislando la estocástica del LLM del determinismo del código.

4. **[El cerebro dividido de un Game Master: Por qué un LLM no puede tirar dados y contar historias a la vez](./post-04-split-brain)**
   La separación entre el `GMAgent` (Narrador) y el `Resolver` (Árbitro). Por qué forzar a un modelo a calcular matemáticas destruye su prosa.
5. **[¿Cómo haces testing unitario de un Game Master? Pruebas E2E con LLM vs LLM](./post-05-testing)**
   Construyendo una jaula determinista y usando otro LLM caótico para intentar romper los barrotes. Cómo probamos que el estado de Neo4j no se corrompe.
6. **[Cómo enseñarle a una IA a leer un manual de rol (y por qué RAG tradicional no sirve)](./post-06-ingestion)**
   Por qué el "naive chunking" crea una sopa de texto inútil, y cómo construimos un pipeline multimodal para extraer reglas duras a JSON.
7. **[La ontología de la Verdad: Cómo evitar que una IA filtre secretos de la trama](./post-07-ontology-of-truth)**
   Manejando mentiras en un espacio vectorial. El uso de niveles de canon (`canon`, `derived`, `rumor`) y grafos de creencias para proteger la trama.
8. **[Deja de escribir prompts, empieza a escribir tipos: El uso de DSPy](./post-08-dspy)**
   Cómo abandonamos el *prompt engineering* frágil y adoptamos tipado estricto en Python para forzar al LLM a devolver estructuras de datos válidas usando DSPy.

## Parte III: Cierre

9. **[La CLI, los Tests y el Estado Actual: Lo que funciona y lo que falta](./post-09-current-state)**
   Un vistazo a la interfaz, el problema de la latencia en inferencia, y el roadmap futuro para el modo Co-Pilot.

---
*Si te interesa seguir el desarrollo o ver cómo está construido por debajo, el repositorio completo es público: [github.com/spuentesp/monitor_dm_system](https://github.com/spuentesp/monitor_dm_system)*
