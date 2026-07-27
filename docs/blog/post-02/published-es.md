
*Segunda parte de la serie sobre MONITOR. Si no leíste la primera parte, empieza ahí — acá cuento cómo evolucionó el sistema desde sus primeras líneas de código hasta lo que es hoy.*

---

MONITOR no nació como un sistema de agentes con cuatro bases de datos y un pipeline de canonización. Nació como un modelo ontológico para narraciones. La arquitectura que tiene hoy es el resultado de varios años de agregar capas encima de lo que ya había — y de resolver los problemas que cada capa nueva dejaba al descubierto.

---

## El modelo ontológico

El primer artefacto fue conceptual: un modelo que describía cómo se estructuran los elementos de una narración.

Personajes, lugares, facciones, objetos, conceptos. Relaciones entre ellos: quién pertenece a qué, quién está dónde, quién es aliado o enemigo de quién. Hechos que ocurren, y qué entidades involucran. Una línea de tiempo que registra cuándo pasa cada cosa.

Nada de código todavía. Solo la pregunta: ¿cómo se ve un mundo si lo tratas como un grafo?

Ese modelo ontológico estuvo dos semanas en papel antes de tocar código. Quería estar seguro de que la estructura podía sostener lo que imaginaba antes de comprometerme con una implementación.

erDiagram
    OMNIVERSE {
        uuid id PK
        string name
        string description
        timestamp created_at
    }

    MULTIVERSE {
        uuid id PK
        uuid omniverse_id FK
        string name
        string system_name
        string description
        timestamp created_at
    }

    UNIVERSE {
        uuid id PK
        uuid multiverse_id FK
        string name
        string description
        string genre
        string tone
        string tech_level
        enum canon_level
        timestamp created_at
    }

    SOURCE {
        uuid id PK
        uuid universe_id FK
        string doc_id
        string title
        string edition
        string provenance
        enum source_type
        enum canon_level
        timestamp created_at
    }

    AXIOM {
        uuid id PK
        uuid universe_id FK
        string statement
        string domain
        float confidence
        enum canon_level
        enum authority
        timestamp created_at
    }

    AGENDA {
        uuid id PK
        uuid universe_id FK
        uuid owner_id FK
        string title
        string description
        enum agenda_type
        enum status
        int total_segments
        int current_segments
        timestamp created_at
        timestamp updated_at
    }

    ENTITY_AXIOMATICA {
        uuid id PK
        uuid universe_id FK
        string name
        enum entity_type
        string description
        map properties
        enum canon_level
        float confidence
        timestamp created_at
    }

    ENTITY_CONCRETA {
        uuid id PK
        uuid universe_id FK
        string name
        enum entity_type
        string description
        map properties
        list state_tags
        enum canon_level
        float confidence
        timestamp created_at
        timestamp updated_at
    }

    STORY {
        uuid id PK
        uuid universe_id FK
        string title
        enum story_type
        string theme
        string premise
        enum status
        timestamp start_time_ref
        timestamp end_time_ref
        timestamp created_at
        timestamp completed_at
    }

    SCENE {
        uuid id PK
        uuid story_id FK
        string title
        string purpose
        int order
        timestamp time_ref
        timestamp created_at
    }

    FACT {
        uuid id PK
        uuid universe_id FK
        string statement
        timestamp time_ref
        int duration
        float confidence
        enum canon_level
        enum authority
        uuid replaces FK
        timestamp created_at
    }

    EVENT {
        uuid id PK
        uuid scene_id FK
        string title
        string description
        timestamp time_ref
        int severity
        float confidence
        enum canon_level
        enum authority
        timestamp created_at
    }

    PLOTTHREAD {
        uuid id PK
        uuid story_id FK
        string title
        enum thread_type
        enum status
        timestamp created_at
    }

    OMNIVERSE ||--o{ MULTIVERSE : "CONTAINS"
    MULTIVERSE ||--o{ UNIVERSE : "CONTAINS"
    UNIVERSE ||--o{ SOURCE : "HAS_SOURCE"
    UNIVERSE ||--o{ AXIOM : "HAS_AXIOM"
    UNIVERSE ||--o{ ENTITY_AXIOMATICA : "HAS_ENTITY"
    UNIVERSE ||--o{ ENTITY_CONCRETA : "HAS_ENTITY"
    UNIVERSE ||--o{ STORY : "HAS_STORY"
    STORY ||--o{ STORY : "PARENT_STORY"
    STORY ||--o{ SCENE : "HAS_SCENE"
    STORY ||--o{ PLOTTHREAD : "HAS_THREAD"
    SCENE ||--o{ SCENE : "NEXT"
    SCENE ||--o{ EVENT : "HAS_EVENT"
    EVENT }o--o{ EVENT : "CAUSES"
    ENTITY_CONCRETA }o--o| ENTITY_AXIOMATICA : "DERIVES_FROM"
    ENTITY_CONCRETA }o--o{ ENTITY_CONCRETA : "LOCATED_IN"
    ENTITY_CONCRETA }o--o{ ENTITY_CONCRETA : "MEMBER_OF"
    ENTITY_CONCRETA }o--o{ ENTITY_CONCRETA : "ALLY_OF"
    ENTITY_CONCRETA }o--o{ ENTITY_CONCRETA : "ENEMY_OF"
    ENTITY_CONCRETA }o--o{ ENTITY_CONCRETA : "OWNS"
    ENTITY_CONCRETA }o--o{ SCENE : "PARTICIPATED_IN"
    ENTITY_CONCRETA }o--o{ EVENT : "INVOLVED_IN"
    ENTITY_CONCRETA }o--o{ FACT : "INVOLVED_IN"
    PLOTTHREAD }o--o{ SCENE : "ADVANCED_BY"
    PLOTTHREAD }o--o{ ENTITY_CONCRETA : "INVOLVES"
    FACT }o--o{ SOURCE : "SUPPORTED_BY"
    FACT }o--o{ SCENE : "SUPPORTED_BY"
    EVENT }o--o{ SOURCE : "SUPPORTED_BY"
    EVENT }o--o{ SCENE : "SUPPORTED_BY"
    AXIOM }o--o{ SOURCE : "SUPPORTED_BY"
    FACT }o--o| FACT : "REPLACES"

---

## Neo4j

El modelo conceptual necesitaba una implementación. La elección natural fue Neo4j — una base de datos de grafos donde los nodos son entidades y los bordes son relaciones.

Neo4j habla Cypher, un lenguaje de consulta diseñado para grafos. Una query como "dame todos los personajes aliados con esta facción que están actualmente en esta ciudad" se escribe en Cypher de forma mucho más directa que en SQL. Pero la razón real de elegir Neo4j no fue solo la sintaxis: necesitaba poder buscar directamente por tipos de relaciones y subsets de árboles. Pensando en que quería poder duplicar mundos, crear what-ifs, bifurcaciones, etc., me pareció mucho más adecuado y menos complejo que SQL.

Para un modelo de mundo con relaciones complejas, eso es bastante bueno.

```cypher
MATCH (c:Character)-[:ALLY_OF]->(f:Faction {name: "Silver Hand"})
WHERE "at_millhaven" IN c.state_tags
RETURN c.name, c.state_tags
```

Acá apareció la primera distinción importante del modelo: **EntityArchetype vs EntityInstance**.

- Un **Arquetipo** es una plantilla o concepto universal: "Mago", "Taberna", "La Fuerza"
- Una **Instancia** es algo concreto que existe en el mundo: "Gandalf el Gris", "El Pony Pisador", "La Fuerza tal como la usa Luke"

La separación no fue teórica — nació de un bug. Tenía dos universos: uno de fantasía medieval y uno de space opera. Un jugador preguntó por "el consejo" y el sistema devolvió información del Consejo Jedi mezclada con el Consejo de Magos. El embedding de "consejo" era similar, pero eran entidades completamente distintas. Ahí entendí: necesitaba que "Mago" (arquetipo) y "Gandalf" (instancia) vivan en namespaces separados, o los vectores se contaminan entre universos.

La distinción parece obvia dicha así, pero modelarla correctamente evita una cantidad enorme de ambigüedades más adelante.

Así es como se ve el modelo ontológico completo (la capa canónica mapeada en Neo4j):

![Diagram](./published-en_diagram_1.png)

La jerarquía Omniverse → Multiverse → Universe → Source no fue arbitraria: la idea era crear mundos persistentes desde el principio. Si tenía un mundo, quería poder tener más partidas con esa misma data que ya hice.

---

## Fase 3: el CRUD y la primera capa de datos

Con el grafo funcionando, el siguiente paso fue construir la capa de acceso: funciones para crear, leer, actualizar y consultar entidades, hechos y relaciones.

Acá el modelo empezó a ganar estructura real. Cada entidad tiene un `canon_level` — una etiqueta que dice cuánto confiar en esa información:

| Nivel | Significado |
|-------|-------------|
| `canon` | Verdad verificada del mundo |
| `derived` | Deducido por el sistema a partir de otros hechos |
| `rumor` | Lo que un personaje *cree* que es verdad (puede ser falso) |
| `proposed` | Generado por un agente, pendiente de revisión |

Los rumores se modelan como una relación: Character → Rumor → Fact. Esto permite que el mundo contenga mentiras y creencias subjetivas sin que contaminen la verdad objetiva del grafo.

El campo `replaces` en Fact hace explícito el retcon: los grafos no se reescriben, solo se reemplazan con nueva versión.

---

## El problema: las narrativas que colapsaban

Hasta acá el sistema sabía representar un mundo. Pero no sabía narrarlo.

El primer intento fue el más simple: pasarle todo el contexto relevante a un LLM y pedirle que narrara. Y funcionaba — por un rato.

El problema llegaba cuando la sesión se extendía. El LLM empezaba a inventar detalles que contradecían lo establecido. Un personaje que había muerto en la escena tres aparecía vivo en la siete. Un lugar que estaba al norte de la ciudad de repente quedaba al sur. Hechos que el jugador había establecido explícitamente desaparecían del relato.

El peor caso fue cuando un personaje entró a una estación espacial, cruzó una puerta, y terminó tomando cerveza en una taberna medieval. Salió, y su nave ya no era la misma. El LLM había "olvidado" el setting entre turnos. No era alucinación — era que el context window se había desbordado y el modelo rellenó los gaps con estadísticas de su training data.

Antes de llegar a la solución final, probé alternativas más baratas: dar más contexto en cada turno, hacer resúmenes y comparar contra ellos, comparar contra el historial de conversación completo. Ninguna funcionó realmente.

Las narrativas colapsaban. Las historias quedaban a medias. Era frustrante — y no era un problema de los modelos. Era un problema de arquitectura.

El LLM no tenía forma de saber qué era verdad canónica y qué estaba inventando. Necesitaba una barrera.

---

## La solución: el CanonKeeper

La decisión de diseño que más cambió el sistema: **ningún agente puede escribir directamente al grafo de Neo4j. Solo uno puede hacerlo: el CanonKeeper.**

El flujo funciona así:

1. Durante la narración, los agentes detectan que algo cambió en el mundo — un personaje murió, una facción tomó el control de una ciudad, se reveló un secreto
2. En lugar de escribir ese cambio directamente, el agente crea un `ProposedChange` en MongoDB: una propuesta pendiente de evaluación
3. Al final de la escena, el CanonKeeper evalúa todas las propuestas acumuladas
4. Verifica que no contradigan hechos canónicos existentes
5. Acepta las válidas y las escribe a Neo4j. Rechaza las que rompen consistencia

¿Por qué MongoDB para los cambios pendientes y no una tabla en Neo4j? En parte porque la estructura de documentos JSON se ajusta mejor a conversaciones en progreso que los grafos rígidos. Pero también fue un ejercicio deliberado de aprendizaje: quería forzarme a operar múltiples bases de datos en paralelo.

Cuando hay contradicción entre dos propuestas de la misma escena, el CanonKeeper resuelve por grado de veracidad, o bien el gamemaster desempata.

sequenceDiagram
    participant Agente as Agente (Narrador/Resolver)
    participant MongoDB as MongoDB (Estado Pendiente)
    participant CanonKeeper as CanonKeeper
    participant Neo4j as Neo4j (Grafo Canónico)

    Agente->>MongoDB: Registra ProposedChange
    Note over Agente,Neo4j: Termina la escena
    CanonKeeper->>MongoDB: Lee propuestas acumuladas
    CanonKeeper->>CanonKeeper: Evalúa consistencia
    alt Es Consistente
        CanonKeeper->>Neo4j: Escribe al Canon
    else Contradicción
        CanonKeeper->>MongoDB: Marca como Rechazado
    end

El LLM puede generar lo que quiera durante la narración. Nada de eso toca el canon hasta que pasa por el CanonKeeper. La barrera existe.

Aquí tienes el JSON concreto de un `ProposedChange` cuando recién se inserta en MongoDB:

```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "scene_id": "f50b2401-4444-42b7-a36c-2f9543168888",
  "story_id": "b3f3b97b-8888-4222-969f-431e6783d777",
  "turn_id": "a90b6701-4c12-42b7-a36c-9f854316abcd",
  "status": "pending",
  "change_type": "fact",
  "content": {
    "statement": "El personaje ha recogido una espada oxidada de la cueva de los goblins.",
    "fact_type": "inventory",
    "canon_level": "local"
  },
  "evidence": [
    {
      "type": "turn",
      "ref_id": "a90b6701-4c12-42b7-a36c-9f854316abcd"
    }
  ],
  "confidence": 0.95,
  "authority": "player",
  "proposer": "ContextAssembly",
  "created_at": "2026-06-28T15:00:00Z"
}
```

**¿Qué detecta el Agente en este caso?**

1. `change_type`: "fact" — Sabe que no es una entidad nueva completa (no ha aparecido un dragón nuevo), sino un hecho o estado: "el inventario ha cambiado". Podría haber sido "entity" si quisiese registrar un PNJ nuevo.
2. `content` — Es un JSON flexible donde el agente mete los detalles de la extracción. Nota sobre el diseño: es un `Dict[str, Any]` a propósito. No quise crear un schema rígido porque no sabía qué tipo de cambios propondrían los agentes en el futuro.
3. `evidence` — Deja apuntado el UUID del turno exacto del chat que justificó este cambio, para que la decisión sea rastreable.
4. `authority` & `proposer` — Quién y cómo se propuso el cambio.

**¿Qué evalúa el CanonKeeper?**

Busca en MongoDB todos los documentos con `"status": "pending"`. Su trabajo es evitar contradicciones:

1. Axiomas del sistema: Si el jugador no tenía manos libres, ¿puede coger la espada?
2. Duplicidad: ¿Ya sabíamos que tenía esta espada de un turno anterior?
3. Jerarquía (Authority): ¿Un comentario del jugador choca contra una regla oficial del manual?

Si aprueba el cambio, crea un nodo en Neo4j y actualiza el JSON:

```json
{
  "status": "accepted",
  "decision_metadata": {
    "decided_by": "CanonKeeper",
    "decided_at": "2026-06-28T15:05:22Z",
    "reason": "No conflict with existing inventory limits.",
    "canonical_ref": "d1e457f7-b89b-12d3-c456-426614176543"
  }
}
```

---

## El segundo problema: no quería programar un sistema por juego

Mientras resolvía el problema de la alucinación, había otro problema esperando: la especificidad de los sistemas de juego.

D&D 5e tiene Fuerza, Destreza, Constitución, y tira 1d20 contra una Clase de Dificultad. Blades in the Dark tiene Position y Effect y tira un pool de d6. City of Mist no tiene stats numéricos — tiene Tags y Mystery. Vampire: The Masquerade tiene Atributos, Habilidades y pools de d10.

Cada sistema tiene su propia lógica para resolver acciones. Programar esa lógica manualmente para cada juego que quisiera soportar era inviable — y cerrado. Quería que el sistema pudiera aprender sistemas nuevos sin que yo tuviera que reescribir código.

La solución fue la **ingesta de documentos**, pero con un enfoque distinto al estándar de RAG.

Al principio intentamos lo básico: *naive chunking* (partir los PDFs en bloques de texto crudo y meterlos en la base vectorial). Eso fue un desastre. Rompió tablas de reglas y también el orden lógico de las cosas. Preguntabas sobre un clan y te traía desde fluff y background hasta listas del apéndice. Llenábamos todo de basura.

Tuvimos que descartar el chunking ingenuo y dedicarnos a entender la estructura del libro. El agente tagea primero por secciones, y subsecciones, etc. Después cada tag es interpretado de acuerdo a lo que es: esto es una regla, esto es lore, esto es una tabla de botín.

Fue ahí donde me di cuenta de que este proceso no solo servía para extraer el "mundo" (lo que el texto describe como realidad de la ficción), sino el **sistema**. El pipeline podía sintetizar un sistema de dados, sus mecánicas de dificultad y sus tablas, y extraer esa lógica para que el agente Resolver la aplicara. 

Con eso logramos crear sistemas de juego 100% configurables expresables como esquemas de datos puros. (Si bien en la práctica usamos JSON vía los esquemas de Pydantic para guardarlos en MongoDB, la experiencia es tan declarativa como un archivo YAML). No hay límite en los juegos que el sistema puede soportar, porque no hay código duro para las reglas, solo esquemas descriptivos.

Para lograr esto, construimos un loop de ingestión multimodal usando LangGraph. El sistema no asume que todo es texto plano; en su lugar, detecta el formato y rutea el contenido a agentes especializados en extraer lo que realmente importa (reglas vs. lore vs. coordenadas):

stateDiagram-v2
    direction TB
    [*] --> DetectModality: Archivo / Documento
    
    DetectModality --> ProcessText : PDFs y Textos
    DetectModality --> ProcessVision : Mapas e Imágenes
    DetectModality --> ProcessSession : Transcripciones
    
    state ProcessText {
        Indexer --> Analyzer
        note right of Analyzer
            Separa mecánicas de juego,
            lore y tablas.
        end note
    }
    
    state ProcessVision {
        MapExtractor --> SpatialEntities
        note right of SpatialEntities
            Extrae relaciones LOCATED_IN
            y coordenadas.
        end note
    }
    
    state ProcessSession {
        SessionListener --> EventsAndFacts
    }
    
    ProcessText --> TemporalValidation
    ProcessVision --> TemporalValidation
    ProcessSession --> TemporalValidation
    
    TemporalValidation --> CompileKnowledgePack
    note right of CompileKnowledgePack
        Paquete de Conocimiento
        listo para ser aplicado al Canon.
    end note
    CompileKnowledgePack --> [*]

En general fue sorprendente que los sistemas sin dados fueron mucho más fáciles de absorber de lo esperado. City of Mist, puramente narrativo, se convirtió en "elegir maniobras, tirar dados, contar" — casi trivial. Pero los sistemas que tuvieron más problemas son los sistemas con puntos, como Vampire: La Mascarada. El gran problema es con las disciplinas, ya que cada punto es un poder específico. Lo mismo la libertad de gastar puntos gratuitos para comprar cosas que no están en la hoja. Es técnicamente "forma libre" pero los puntos gratis son equivalencias, y no es lo mismo que la experiencia. Eso complicó mucho al sistema de reglas.

---

## Dónde dejó esto el sistema

Al final de estas tres fases, MONITOR tenía:

- Un grafo canónico en Neo4j con modelo ontológico completo
- Un patrón de escritura segura (ProposedChange → CanonKeeper)
- Una capa de búsqueda semántica para recuperar reglas de juego
- Los primeros agentes especializados

Lo que no tenía todavía era entender cómo estos componentes se organizaban en capas que no se convirtieran en spaghetti. Ni por qué necesitaba **cuatro bases de datos diferentes** — cada una con un trabajo específico: una para la verdad absoluta, otra para los cambios pendientes, otra para la memoria semántica, y otra para los archivos. Eso vino después — y lo cuento en el siguiente post.

*Siguiente: las tres capas, los cinco sistemas de datos, y por qué los agentes no pueden hablar directamente con la base de datos.*

---