# De un modelo ontológico a un sistema de agentes: cómo creció MONITOR

*Segunda parte de la serie sobre MONITOR. Si no leíste la primera parte, empieza ahí — acá cuento cómo evolucionó el sistema desde sus primeras líneas de código hasta lo que es hoy.*

---

MONITOR no nació como un sistema de agentes con cuatro bases de datos y un pipeline de canonización. Nació como un modelo ontológico para narraciones. La arquitectura que tiene hoy es el resultado de varios años de agregar capas encima de lo que ya había — y de resolver los problemas que cada capa nueva dejaba al descubierto.

---

## Fase 1: el modelo ontológico

El primer artefacto fue conceptual: un modelo que describía cómo se estructuran los elementos de una narración.

Personajes, lugares, facciones, objetos, conceptos. Relaciones entre ellos: quién pertenece a qué, quién está dónde, quién es aliado o enemigo de quién. Hechos que ocurren, y qué entidades involucran. Una línea de tiempo que registra cuándo pasa cada cosa.

Nada de código todavía. Solo la pregunta: ¿cómo se ve un mundo si lo tratas como un grafo?

<!-- [VOZ PROPIA]: ¿Cómo fue ese proceso? ¿Fue en papel, en un documento, en un whiteboard? ¿Cuánto tardó en tomar forma? -->

---

## Fase 2: Neo4j

El modelo conceptual necesitaba una implementación. La elección natural fue Neo4j — una base de datos de grafos donde los nodos son entidades y los bordes son relaciones.

Neo4j habla Cypher, un lenguaje de consulta diseñado para grafos. Una query como "dame todos los personajes aliados con esta facción que están actualmente en esta ciudad" se escribe en Cypher de forma mucho más directa que en SQL. Para un modelo de mundo con relaciones complejas, eso importa.

```cypher
MATCH (c:Character)-[:ALLY_OF]->(f:Faction {name: "Silver Hand"})
WHERE "at_millhaven" IN c.state_tags
RETURN c.name, c.state_tags
```

Acá apareció la primera distinción importante del modelo: **EntityArchetype vs EntityInstance**.

- Un **Arquetipo** es una plantilla o concepto universal: "Mago", "Taberna", "La Fuerza"
- Una **Instancia** es algo concreto que existe en el mundo: "Gandalf el Gris", "El Pony Pisador", "La Fuerza tal como la usa Luke"

Un personaje jugador siempre es una Instancia. Una clase de personaje es un Arquetipo. La distinción parece obvia dicha así, pero modelarla correctamente evita una cantidad enorme de ambigüedades más adelante.

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

Esto permite que el mundo contenga rumores, mentiras y creencias subjetivas sin que contaminen la verdad objetiva del grafo.

<!-- [VOZ PROPIA]: ¿Hubo alguna decisión de diseño acá que fue difícil o no obvia? ¿Algo que cambiaste varias veces? -->

---

## El problema: las narrativas que colapsaban

Hasta acá el sistema sabía representar un mundo. Pero no sabía narrarlo.

El primer intento fue el más simple: pasarle todo el contexto relevante a un LLM y pedirle que narrara. Y funcionaba — por un rato.

El problema llegaba cuando la sesión se extendía. El LLM empezaba a inventar detalles que contradecían lo establecido. Un personaje que había muerto en la escena tres aparecía vivo en la siete. Un lugar que estaba al norte de la ciudad de repente quedaba al sur. Hechos que el jugador había establecido explícitamente desaparecían del relato.

Las narrativas colapsaban. Las historias quedaban a medias. Era frustrante — y no era un problema de los modelos. Era un problema de arquitectura.

<!-- [VOZ PROPIA]: ¿Hubo una sesión específica donde esto fue especialmente frustrante? ¿Algún ejemplo concreto de algo que el LLM rompió? -->

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

```
Narrador detecta cambio
        ↓
  ProposedChange → MongoDB
        ↓
  (fin de escena)
        ↓
  CanonKeeper evalúa
        ↓
  ¿Consistente? → Neo4j
  ¿Contradicción? → rechazado
```

El LLM puede generar lo que quiera durante la narración. Nada de eso toca el canon hasta que pasa por el CanonKeeper. La barrera existe.

---

## El segundo problema: no quería programar un sistema por juego

Mientras resolvía el problema de la alucinación, había otro problema esperando: la especificidad de los sistemas de juego.

D&D 5e tiene Fuerza, Destreza, Constitución, y tira 1d20 contra una Clase de Dificultad. Blades in the Dark tiene Position y Effect y tira un pool de d6. City of Mist no tiene stats numéricos — tiene Tags y Mystery. Vampire: The Masquerade tiene Atributos, Habilidades y pools de d10.

Cada sistema tiene su propia lógica para resolver acciones. Programar esa lógica manualmente para cada juego que quisiera soportar era inviable — y cerrado. Quería que el sistema pudiera aprender sistemas nuevos sin que yo tuviera que reescribir código.

La solución fue la **ingesta de documentos**.

En lugar de codificar las reglas, el sistema lee los PDFs o textos de los manuales, extrae las mecánicas relevantes, y las almacena como conocimiento consultable. Cuando necesita resolver una acción bajo un sistema determinado, recupera las reglas pertinentes del índice vectorial y las aplica.

Eso también significa que puedes crear un sistema completamente nuevo — inventado, propio — escribirlo como texto, y el sistema lo aprende. No hay límite en los juegos que puede soportar.

<!-- [VOZ PROPIA]: ¿Hubo algún sistema que fue especialmente difícil de ingestar? ¿Alguna mecánica que el sistema no entendió bien al principio? -->

---

## Dónde dejó esto el sistema

Al final de estas tres fases, MONITOR tenía:

- Un grafo canónico en Neo4j con modelo ontológico completo
- Un patrón de escritura segura (ProposedChange → CanonKeeper)
- Una capa de búsqueda semántica para recuperar reglas de juego
- Los primeros agentes especializados

Lo que no tenía todavía era la arquitectura que orquestara todo eso de forma coherente. Eso vino después — y lo cuento en el siguiente post.

*Siguiente: las tres capas, los cinco sistemas de datos, y por qué los agentes no pueden hablar directamente con la base de datos.*
