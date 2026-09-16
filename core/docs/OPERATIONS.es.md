# Guía de uso de Cleanroom

[English](OPERATIONS.en.md) · [日本語](OPERATIONS.ja.md) · [简体中文](OPERATIONS.zh-Hans.md) · [한국어](OPERATIONS.ko.md) · [Español](OPERATIONS.es.md) · [README](../../README.md)

Cleanroom es un espacio de desarrollo colaborativo basado en Vera Kernel. Aunque la IA realice gran parte de la implementación, conservas el propósito, las decisiones, los métodos de verificación, los fallos y la comprensión técnica del proyecto.

## 01 / Empezar en tu equipo

Crea un entorno nuevo con Python 3.11+ en cada equipo. La ruta Linux no certifica todas las distribuciones. En Windows usa WSL2, no Windows nativo. Después de activar el entorno, entra en tu propio proyecto.

```sh
git clone https://github.com/Ag3497120/cleanroom.git cleanroom
cd cleanroom
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./core
verantyx setup accounts
verantyx
```

```sh
source /absolute/path/to/cleanroom/.venv/bin/activate
cd /absolute/path/to/your-project
verantyx
```

## 02 / Agent a la izquierda, Owner a la derecha

Escribe una petición normal en el campo Agent, abajo a la izquierda. No hace falta aprender un nuevo lenguaje de comandos.

| Español | Key |
|---|---|
| Pedir trabajo | Agent: Enter |
| Nota local | Empty Enter → MEMO |
| Búsqueda local | Empty Enter → SEARCH |
| Referenciar | 2+ characters → ↑/↓ → Tab |
| Acciones | F2 |
| Desplazarse | F3 |
| Comprensión | F4 |
| Vista dividida | Alt+0 |
| Nueva línea | Ctrl+J / Esc then Enter |
| Cerrar | Ctrl+D |

Pulsa Enter con el campo vacío: Agent → nota Owner amarilla → búsqueda Owner verde → Agent.

Escribe al menos los dos primeros caracteres de un elemento Owner, elige con las flechas y pulsa Tab para insertar la referencia. Con sugerencias abiertas, Enter selecciona; no envía la petición.

La división horizontal requiere 140 columnas y 24 filas. Con 90 columnas y 36 filas se apilan; en pantallas menores se muestra el lado activo. En Mac puede hacer falta Fn y configurar Option para enviar Escape. También puedes usar el menú F2.

```sh
VERANTYX_REDUCE_MOTION=1 verantyx
NO_COLOR=1 verantyx
verantyx --plain
verantyx watch
```

Ctrl+C: clear the current draft / cancel the current question; with no draft, request closure. It is not a guarantee of forcibly stopping an external program. Esc closes a menu or suggestion without accepting it.

## 03 / Commands

Los menús de configuración se basan en inglés. Esta traducción no implica que cada mensaje de la CLI esté traducido. El catálogo real es `verantyx --help` y `verantyx commands NAME`.

| Command | Español / scope |
|---|---|
| `verantyx` | Open workspace / 作業を始める / 开始工作 / 작업 시작 / Abrir espacio |
| `verantyx commands` | List actual registered commands / 実装済みコマンド一覧 / 命令列表 / 명령 목록 / Catálogo de comandos |
| `verantyx commands setup --json` | Read command details / 詳細 / 详情 / 상세 / Detalles |
| `verantyx setup accounts` | ChatGPT/Codex, Claude Code, API, local |
| `verantyx setup models` | Work / reflection |
| `verantyx setup roles` | Parent / child model roles |
| `verantyx setup language` | en / ja / zh-Hans / ko / es |
| `verantyx setup profile` | Voluntary experience / 任意の経験 / 自愿填写经验 / 자율 경험 기록 / Experiencia voluntaria |
| `verantyx setup pace` | Suggestion load / 提案の負荷 / 建议量 / 제안량 / Carga de sugerencias |
| `verantyx my-skills` | Your choices / 本人の選択 / 本人选择 / 나의 선택 / Tus elecciones |
| `verantyx my-learning` | Notes captured during work / 実装中の記録 / 实现时记录 / 구현 중 기록 / Notas durante el trabajo |
| `verantyx my-journal` | Journal / 日記 / 日记 / 일지 / Diario |
| `verantyx web --no-open` | Local Atlas URL / ローカルAtlas / 本地Atlas / 로컬 Atlas / Atlas local |
| `verantyx setup notebook` | Obsidian / MCP / skill imports |
| `verantyx setup harness` | External work adapter |
| `verantyx setup sandbox` | OSS isolation adapter |
| `verantyx toolbox status` | MCP tools |
| `verantyx watch` | Read-only / 閲覧専用 / 只读 / 읽기 전용 / Solo lectura |

## 04 / Models

Usa el inicio de sesión local oficial de Codex o Claude Code. No pegues tokens de suscripción en una web. La API se factura aparte de la suscripción. Los modelos locales necesitan un servidor activo y un modelo disponible. Trabajo y reflexión pueden usar modelos distintos; desactivar la reflexión no elimina el resultado.

```sh
verantyx setup accounts
verantyx setup codex
verantyx setup claude
verantyx setup models
verantyx setup roles
verantyx settings --show
```

## 05 / My profile · My pace · My skills

F2 > My profile permite describir brevemente tu experiencia o saltar este paso. My pace ajusta el volumen y el esfuerzo de las sugerencias. My skills separa borradores de procedimientos, temas que eliges explorar y tus propias explicaciones o ejemplos. No hace falta completar todo. Pedir a la IA que haga push no demuestra desconocimiento de Git.

El resultado del trabajo y la reflexión de la IA son independientes. Los modelos pueden ofrecer interpretaciones distintas sin borrar las anteriores. Un procedimiento de IA no certifica una habilidad humana. Delegar, omitir o pedir ayuda no implica falta de capacidad.

```sh
verantyx setup profile
verantyx setup pace
verantyx my-skills
verantyx my-skills quiet --scope TODAY
verantyx my-journal
verantyx my-learning
```

## 06 / Owner · Privacy

Las notas Owner son locales por defecto. Solo la referencia que eliges se inserta en la petición; el alcance de envío se confirma por separado. Las notas, referencias y preferencias de aprendizaje no conceden permisos de ejecución.

Las notas y búsquedas Owner no llaman a la IA. Las referencias que insertas expresamente forman parte del contenido a enviar. No publiques registros privados del proyecto ni personales en GitHub.

## 07 / My Atlas

`verantyx web` abre My Atlas de forma privada en loopback. Mantén el terminal abierto. Muestra experiencia registrada, no notas ni carencias. Los registros del mismo usuario del sistema pueden usarse entre proyectos, pero no se sincronizan automáticamente entre Mac.

```sh
verantyx web
verantyx web --no-open
verantyx --lang es web
```

The actual view follows its supported language catalogue; untranslated items may fall back. These guides do not claim complete five-language runtime localization.

## 08 / Work · Reflection

No eludas los límites de rutas. Usa un alcance autorizado o un proyecto distinto. Si falla la reflexión, conserva el trabajo y ejecuta después `verantyx organize RUN_ID`. Consulta las interpretaciones anteriores con `verantyx perspectives RUN_ID`.

## 09 / Obsidian · MCP · Harness

F2 > Notebook bridge conecta un vault de Obsidian elegido expresamente. Los skills importados siguen siendo borradores con procedencia, no certificados de aprendizaje ni permisos. MCP y los harness externos requieren configuración explícita. Configurar un sandbox no certifica su aislamiento.

[Connections](NOTEBOOK_CONNECTIONS.en.md) · [日本語](NOTEBOOK_CONNECTIONS.ja.md) · [Sandbox boundary](SANDBOX_BACKENDS.en.md)

## 10 / Web preview

Pages y el GIF usan datos preparados: no llaman a la IA, no modifican proyectos, no autentican suscripciones ni certifican comprobaciones. El gateway opcional es un servicio aparte que requiere configuración y aprobación. No debe exponer privilegios privados de ejecución de Codex al público.

> Vista previa del código fuente, no certificación de un MVP completo. El GIF usa datos preparados en el renderizador real de la CLI; no es una prueba exitosa de un modelo. La demo web funciona en memoria y no es un shell remoto.

[Publication & privacy](../../docs/PUBLICATION.md) · [Recording recipe](../../docs/DEMO_RECORDING.md) · [Origins](origins/README.md)

## Active-pane scrolling / AI beta

[Independent scrolling and terminal limitations](../../docs/SCROLLING.md)

Wheel / PageUp / PageDown operate on the currently selected pane. Empty Enter changes the input and scroll destination together. The other pane keeps its viewport. This does not control the terminal emulator's native history scrollbar.

The Pages beta additionally offers **Copy handoff**, **Direct API** (OpenAI-compatible / Ollama), and **Import answer**. Direct API is explicit, may be blocked by browser networking rules, and does not run tools or change files. Keys are kept only in tab memory and cleared from the field at send time or on dialog close. AI answers remain unverified proposals, not successful execution receipts. Use the local CLI for subscription-based development.
