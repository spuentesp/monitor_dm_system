

  

*Primera parte de una serie sobre MONITOR, un sistema de inteligencia narrativa para juegos de rol.*

  
  
  

Llevo un tiempo, aproximadamente casi medio año, construyendo algo que después de no tener nombre, pasó a llamarse (en honor a cierto personaje de DC comics)  **MONITOR**: un sistema capaz de dirigir una campaña de rol de mesa completa con memoria persistente, narración coherente y reglas que se aplican de verdad, sin necesitar un ser humano al otro lado de la mesa. No sólo narra, sino que además puede hacer ingestión de libros, textos, y aprender “al vuelo” el juego que quiera.

  

No está terminado. Pero está funcionando, con tests que lo demuestran. En estos posts pretendo documentar el proceso: las decisiones técnicas, los problemas que encontré, y por qué construí esto desde cero en lugar de usar cualquiera de las cosas que ya existen (y por que no me gustaron).

  

Empecemos.

  
  

## Veinte años jugando rol

  

Empecé en el colegio. D&D primero, después Vampiro: La Mascarada, y desde ahí me aventuré a mas cosas: Mundo de Oscuridad, Hombre Lobo, Cyberpunk, el sistema 2d20, juegos narrativos como PbtA, City of Mist, Fiasco, 2d20, y mas.

  

Siempre me gustó probar sistemas nuevos. Hay gente que se queda en D&D toda la vida y está completamente bien (no, creo que no está bien, pero eso es para otro post). yo era de los que cuando salía algo distinto, quería probarlo. “ah, magos en modernidad con un sistema propio”. “ah, un sistema especifico de ‘combate socia’”. “ah, un sistema de gestion de recursos”. etcetera.

  

El hilo que conecta todos esos juegos no es un género ni un sistema. Es la idea de la **simulación**: La creación de reglas para poder imaginar y “simular” los problemas y obstáculos que enfrentan estos personajes, con las herramientas específicas que tienen. No solo ser alguien “diferente” sino tener capacidades de resolver problemas de forma distinta (Mago la ascensión es un juego que me fascina por esto: El sistema te obliga a justificar tu “magia” bajo un sistema de creencias).

  

Con los años, hemos tenido muchas campañas exitosas con amigos. También se cumple el meme: la vida adulta nos permite juntarnos una vez cada seis meses en año bisiesto siempre y cuando hayamos hecho los sacrificios correspondientes. No es fácil. Y eso ha provocado que esté jugando menos.

Asi que empecé a buscar en mi PC la posibilidad de saciar esas ganas de rol.

  

---

  

## El problema con ChatGPT

  

Cuando los LLMs se volvieron lo suficientemente buenos como para impresionar, lo primero que hice fue tratar de usarlos para jugar. La experiencia fue interesante, pero duró poco.

  

El problema es estructural. Cuando usas ChatGPT, Gemini, o cualquier interfaz de chat, el agente hace una cosa en cada turno: **releer toda la conversación desde el principio**. Texto plano, de corrido, desde el mensaje uno hasta el último. Con eso genera la siguiente respuesta.

  

Al principio funciona. Pero el contexto (la “memoria”)  se llena. Y cuando se llena, el modelo empieza a alucinar, a "olvidar" lo que pasó al inicio, a rellenar con cosas que no corresponden. No es un bug — es la naturaleza del sistema.

  

Después probé plataformas más especializadas, como [character.ai](http://character.ai), risuAI, SillyTavern. Los *character cards* son básicamente lo mismo pero con un personaje fijo cargado al inicio, no muy diferente a cargar una skill. Lo más avanzado que encontré fue **Dreamgen**[https://dreamgen.com/], que vectoriza el historial para buscar por relevancia — más consistencia, sesiones más largas. Pero sigue siendo un personaje dentro de una historia. No controla el estado de un mundo, no maneja múltiples personajes con historia propia, no verifica que lo que genera sea consistente con lo establecido. Es un agente que finge ser un personaje, y este agente ademas tiene que llevar las respuestas del mundo.

  

El problema real no era solo la memoria. Era **proveniencia** ademas. de donde vino esta info? esto es real? por que una base de datos podria encontrar dos cosas que son tecnicamente correctas…pero en el juego, una ocurrio de verdad, y la otra en una vision.  con eso ya rompemos toda la estructura temporal para contestar.  Y cuando me topé con ese problema, eso me llevó a algo completamente distinto.

  

---

  

## Un ejercicio que no me fue bien

  

Todo esto coincidió con algo que estaba viendo en la universidad, en una clase de arquitectura de software. Estábamos estudiando modelos semánticos: la web semántica, OWL, ontologías. También lo estaba aplicando en el trabajo, donde quería modelar procesos de gestión de proyectos de forma ontológica.

  

En esa clase nos dieron un ejercicio para crear un modelo semántico. No me fue muy bien.

  

Pero fue ese ejercicio el que me abrió la cabeza. Al intentarlo, entendí algo: un modelo semántico no es una base de datos rara. Es **una forma de pensar**.

  

Si A implica B, y B implica C, entonces A implica C. Puedes inferir relaciones que nunca declaraste explícitamente, solo trepando la red. El almacenamiento, la búsqueda en sí se vuelve el “razonamiento”. pensémoslo así. 

Si tienes un personaje A, y este personaje A es miembro de una familia B, por fuerza mayor, al buscar el nodo de B, la entidad “familia”, puedes también a través de B saber quienes son sus hermanos, padres, etcétera, ya que todos están relacionados a la entidad “familia”. Este tipo de navegación por grafos nos permite cargar relaciones complejas entre elementos.

  

---

  

## Yggdrasil

  

<!-- IMAGEN: Yggdrasil — grabado de Friedrich Wilhelm Heine (1886), dominio público

     Fuente: https://commons.wikimedia.org/wiki/File:Yggdrasil.jpg -->

  

Un día estaba viendo artwork de un libro y me salió una ilustración de **Yggdrasil**, el árbol del mundo nórdico. El árbol que conecta los nueve reinos, con raíces que llegan al inframundo y ramas que tocan el cielo.

  

Lo miré, y me acordé de los grafos de la universidad.

  

*Esto es un DAG. Un directed acyclic graph.*

  

graph TD

    PC["Kael Draven\n(Personaje — PC)"]

    NPC["Bartender\n(Personaje — NPC)"]

    LOC["The Rust Nail\n(Lugar)"]

    FACTION["Tripulación perdida\n(Facción)"]

    OBJ["Baliza del Rust Nail\n(Objeto)"]

  

    PC -->|UBICADO_EN| LOC

    NPC -->|UBICADO_EN| LOC

    NPC -->|CONOCE| FACTION

    FACTION -->|POSEÍA| OBJ

    PC -->|INTERACTÚA_CON| NPC

  

    style PC fill:#4a90d9,color:#fff

    style NPC fill:#7b68ee,color:#fff

    style LOC fill:#2ecc71,color:#fff

    style FACTION fill:#e67e22,color:#fff

    style OBJ fill:#e74c3c,color:#fff

  
  
  

Un “mundo” a nivel narrativo es una conexion de entidades. es un universo que contiene reglas y cosas. Entidades, relaciones, jerarquías, dependencias. Si puedo representar un mundo como un grafo, puedo representar las interrelaciones entre sus partes, personajes, lugares, facciones, objetos, conceptos,y cómo se conectan entre ellos. Y puedo inferir cosas que nunca declaré explícitamente.

  

---

  

## La temporalidad como dimensión extra

  

Quedaba un problema: los grafos son estáticos. Un mundo no lo es. ¿Cómo representas que algo *cambió*?

  

La respuesta me llego jugando, al ver como los sprites se montan para cambiar la apariencia del personaje: la temporalidad no es más que **otra dimensión** en la que las interrelaciones van mutando. No necesitas un modelo distinto — necesitas registrar los cambios, y cuándo ocurrieron.

  

![Diagram](./temporal_mutations.png)

     Renderizar en https://mermaid.live antes de subir a Medium -->

  

La mecánica es simple:

1. Guardas una foto del estado del mundo en un momento dado

2. Encima vas apilando mutaciones — qué cambió, y en qué momento

3. Eso construye un árbol de estados a lo largo del tiempo

  

Y la parte más poderosa de esta estructura: puedes **cortar el árbol en cualquier punto y divergirlo**. Los *what-if*, los universos alternativos, las simulaciones son triviales. Es copiar una rama y continuar desde ahí.

  

---

  

## Los dos problemas que decidí resolver

  

Con todo eso sobre la mesa, el espacio del problema quedó claro:

  

**Primero:** Un modelo de datos capaz de expresar un mundo completo:  sus entidades, sus historias, sus interrelaciones, de forma que persista, sea consultable y evolucione en el tiempo sin perder coherencia.

  

**Segundo:** Un sistema narrativo que no alucine. Todo lo que el LLM genere tiene que tener proveniencia: viene de un documento, de una sesión jugada, o fue declarado explícitamente. Si no tiene proveniencia, no entra al canon. Y si intenta contradecir algo que ya es canon, se rechaza antes de guardarse.

  

No necesitaba un modelo con mejor memoria. Necesitaba una **barrera** contra alucinaciones.

  

---

  

## Dónde está hoy

  

El sistema corre. Hay una interfaz web (apenas) funcional y un conjunto de comandos CLI. La base de datos de conocimiento persiste entre sesiones. Los agentes narran, resuelven acciones, tiran dados y guardan el estado.

  

Para probarlo de forma estable, corremos sesiones donde **un segundo LLM hace de jugador** y el sistema actúa como GM, el modelo actúa como PC, y vemos si la sesión se sostiene. El log más reciente fue una sesión de 13 entradas en el mundo Millhaven, `player_mode: llm`, 0 fallbacks, 0 preguntas de clarificación del GM.

  

Esto es lo que genera el sistema en el opening de esa sesión, antes de que el jugador haya declarado nada:

  

> *The lantern's glow wavers as the mist curls in from the marshlands — thick, gray, and laced with something that smells of copper and old sorrow. You stand at the edge of Millhaven's market square where cobblestones gleam wet and the last stragglers hurry home with collars drawn high. A bell tolls somewhere distant. Then another. The lamplighter climbs his ladder with mechanical patience, his face hidden beneath a wide-brimmed hat, and the flame catches just as the murk swallows his silhouette.*

>

> *Old Tomas has been lighting these lamps for forty years. He has watched the mist take his neighbors and keeps to his rounds regardless. No one asks him why. In Millhaven, certain questions calcify in the throat before they reach the tongue.*

  

Y esto es cómo se ve la capa mecánica debajo de cada turno:

  

```json

{

  "type": "scene_turn",

  "resolution_type": "trivial",

  "intent_type": "dialogue",

  "success_level": "success",

  "roll_breakdown": "trivial — no roll needed",

  "effects": ["fiction_advances"],

  "narrative_pressure": "steady"

}

```

  

<!-- FUENTE: tests/e2e/logs/live_gameplay_llm_run01_20260621T165920Z.md (master)

     Opening + Turn 4 son los mejores para screenshot -->

  

No es perfecto. Hay cosas que fallan, flujos a medio terminar, casos bordes sin manejar. Pero la sesión no se cae, la narración tiene coherencia, y el estado del mundo se actualiza al final de cada escena.

  

En el siguiente post cuento cómo fue creciendo el sistema desde un modelo ontológico básico hasta lo que es hoy — y qué decisiones técnicas concretas tomé en el camino.

  

*Siguiente: de un CRUD sobre Neo4j a un sistema de agentes — cómo MONITOR fue creciendo.*

  
**