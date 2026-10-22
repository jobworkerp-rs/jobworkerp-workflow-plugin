---
name: jobworkerp-workflow
description: >-
  Create and edit workflow YAML for the jobworkerp-rs workflow DSL (based on Open Workflow DSL v1.0.0 with jobworkerp extensions).
  Use when the user requests creating workflow definitions, modifying existing workflows, or understanding workflow structure.
  Supports runner/worker/function execution (COMMAND, LLM, HTTP_REQUEST, GRPC, DOCKER, PYTHON_COMMAND, WORKFLOW, SANDBOX, MCP servers, Plugins),
  run.shell/run.container/run.script/run.workflow process tasks, call http/grpc tasks with secret-based authentication,
  for loops, fork parallel execution, switch branching, try-catch error handling, timeouts,
  and jq/Liquid variable expansion.
---

# jobworkerp Workflow YAML Creator

Skill for creating and editing workflow YAML for jobworkerp-rs. The DSL adopts the flow-control and logic parts of [Open Workflow DSL v1.0.0](https://github.com/open-workflow-specification/specification/blob/v1.0.0/dsl.md) and extends them for the jobworkerp job platform.

## Reference Files

- **[Schema Reference](references/schema-reference.md)**: All task types, `use` (timeouts / authentications / secrets), run/call variants, timeouts, error handling, runtime expressions
- **[Runner Schemas](references/runner-schemas.md)**: Settings/arguments/results for each runner (COMMAND, LLM, HTTP_REQUEST, GRPC, ...)
- **[Examples](references/examples.md)**: Workflow patterns
- **[workflow-schema.yaml](references/workflow-schema.yaml)**: Human-readable JSON Schema (Draft 2020-12) mirrored from jobworkerp-rs `runner/schema/workflow.yaml`
- **[workflow-validation-schema.json](references/workflow-validation-schema.json)**: The schema the jobworkerp-rs runtime validator actually uses (`runner/schema/workflow_minimal_fix.json`). Validate a workflow with `check-jsonschema --schemafile references/workflow-validation-schema.json my-workflow.yaml`

## Workflow Basics

### Top-Level Structure

Only `document` and `do` are required.

```yaml
document:              # REQUIRED - metadata
  dsl: "0.0.1"
  namespace: default
  name: my-workflow
  version: "0.0.1"
input:                 # Optional - input schema / input.from transform
  schema:
    document:
      type: object
      properties: {}
use:                   # Optional - reusable components
  timeouts: {}         #   named timeouts, referenced as `timeout: <name>`
  authentications: {}  #   named bearer/basic policies for call tasks
  secrets: []          #   declared secret names (values come from env)
timeout:               # Optional - whole-workflow timeout (no default)
  after: { hours: 1 }
do:                    # REQUIRED - ordered task list
  - TaskName:
      ...
output:                # Optional - output transformation
  as: "${...}"
```

When `input` is omitted the runtime input is passed to the tasks unchanged.

### Task Types Overview

| Task | Purpose | Key Properties |
|------|---------|---------------|
| **runTask** | Execute a job | `run.runner` / `run.function` / `run.worker` / `run.script` / `run.shell` / `run.container` / `run.workflow` |
| **callTask** | Call an HTTP or gRPC service | `call: http\|grpc`, `with` |
| **forTask** | Iterate over a collection | `for.each`, `for.in`, `do`, `inParallel`, `onError` |
| **forkTask** | Concurrent branches | `fork.branches`, `fork.compete` |
| **doTask** | Sequential subtask group | `do` |
| **switchTask** | Conditional branching | `switch[].when`, `switch[].then` |
| **tryTask** | Error handling | `try`, `catch.errors`, `catch.retry`, `catch.do` |
| **setTask** | Set context variables | `set` |
| **raiseTask** | Raise (or rethrow) an error | `raise.error` |
| **waitTask** | Pause execution | `wait` (duration) |

### Common Task Properties (taskBase)

<!-- validate:skip -->
```yaml
- AnyTask:
    if: "${condition}"      # Skip the whole task (incl. output/export) when false
    input:
      from: "${transform}"
    output:
      as:                   # string or object
        key: "${.value}"
    export:
      as:                   # write context variables
        varName: "${.data}"
    timeout:                # Optional; inline or the name of a use.timeouts entry
      after: { seconds: 30 }
    then: continue          # continue|exit|end|wait|"TaskName"
    checkpoint: false
```

## runTask

Each `run` holds exactly one execution form. `await` (default `true`) can be set on every form; `return` only on the process forms.

| Form | Executes | `await` | `return` |
|------|----------|:-:|:-:|
| `run.runner` | Any runner by name, with settings/options | yes | no |
| `run.function` | `runnerName` (+settings/options) or `workerName` | yes | no |
| `run.worker` | Pre-configured worker | yes | no |
| `run.workflow` | Nested workflow (`workflowUrl` / `workflowData`) | yes | no |
| `run.shell` | Command (COMMAND runner) | yes | yes |
| `run.container` | Container (DOCKER runner) | yes | yes |
| `run.script` | Inline/external script (PYTHON_COMMAND runner) | yes | yes |

- `await: false` enqueues fire-and-forget and passes the task input through as output. Rejected together with `useStreaming: true`.
- `return` for process forms: `stdout` (default, raw string — never auto-parsed as JSON), `stderr`, `code`, `all` (`{code, stdout, stderr}`), `none`.

### run.runner (most flexible)

```yaml
- MyTask:
    run:
      runner:
        name: COMMAND              # REQUIRED
        settings: {}               # Runner initialization settings
        arguments:                 # REQUIRED
          command: echo
          args: ["Hello"]
        options:                   # Worker options (inside `runner`, not under `run`)
          channel: workflow
          useStatic: false
          storeSuccess: true
          storeFailure: true
          queueType: NORMAL        # NORMAL|WITH_BACKUP|DB_ONLY
          responseType: DIRECT     # DIRECT|NO_RESULT
    useStreaming: false            # Stream intermediate results (LLM etc.)
```

Add `using: <method>` inside `runner` for multi-method runners (LLM, GRPC, WORKFLOW, SANDBOX, multi-tool MCP servers).

### Process forms (shell / container / workflow)

```yaml
- ListDir:
    run:
      shell:
        command: ls
        args: ["-la", "${.dir}"]
      return: all                  # {code, stdout, stderr}
- InContainer:
    run:
      container:
        image: alpine:3.20
        command: ["echo", "hello"]
- Child:
    run:
      workflow:
        workflowUrl: ./child.yaml
        input: { value: 1 }
```

- `run.shell` / `run.container` do **not** fail on a non-zero exit by default; set `treatNonzeroAsError: true` (optionally with `successExitCodes`).
- `run.script` always fails on a non-zero exit and does not support `useStreaming: true`.

See [Schema Reference](references/schema-reference.md#runtask) for all fields.

## callTask

```yaml
- GetRepo:
    call: http
    with:
      method: get
      endpoint:
        uri: https://api.github.com/repos/jobworkerp-rs/jobworkerp-rs
        authentication:
          use: github              # policy declared under use.authentications
      output: response             # content (default) | response
```

`call: grpc` takes `service` (name/host/port), `method`, `arguments` (requires server reflection). Secret values are never written in YAML: declare names under `use.secrets` and supply `WORKFLOW_SECRET_<UPPER_SNAKE_NAME>` env vars. See [Schema Reference](references/schema-reference.md#calltask).

## Runner Quick Reference

### COMMAND
```yaml
name: COMMAND
arguments:
  command: "echo"
  args: ["Hello"]
  treatNonzeroAsError: true
```

### LLM (`using` is REQUIRED: `chat` | `completion` | `embedding` | `token_count`)
```yaml
name: LLM
using: chat
settings:
  ollama: { baseUrl: "http://localhost:11434", model: "model-name", pullModel: false }
  # OR genai: { model: "gpt-4o" }   # API key via env var; for OpenAI-compatible servers include /v1/ in baseUrl
arguments:
  messages:
    - role: system
      content: { text: "System prompt" }
    - role: user
      content: { text: "User message" }
  options: { maxTokens: 8192, temperature: 0.3, reasoningEffort: "low" }
```

### HTTP_REQUEST
```yaml
name: HTTP_REQUEST
settings: { baseUrl: "https://api.example.com" }
arguments: { method: "GET", path: "/data", headers: [{ key: "Accept", value: "application/json" }] }
```
(Prefer `call: http` for plain REST calls that need authentication.)

### MCP Servers
```yaml
name: mcp-fetch           # Server name from mcp-settings.toml
using: fetch              # Tool name (required when the server has several tools)
arguments:                # The tool's own input fields, written directly
  url: "https://example.com"
  max_length: 5000
```

### GRPC (`using: unary` default, or `streaming`)
```yaml
name: GRPC
using: unary
settings: { host: "grpc.example.com", port: 50051, useReflection: true }
arguments:
  method: "mypackage.MyService/GetData"
  jsonBody: '{"id":"123"}'
  asJson: true
```

### WORKFLOW
Prefer `run.workflow` for nesting. Use the runner form for `using: create` (register a workflow as a worker). See [Runner Schemas](references/runner-schemas.md#workflow-runner-unified-multi-method).

See [Runner Schemas](references/runner-schemas.md) for complete settings/arguments of every runner (including DOCKER, PYTHON_COMMAND, SANDBOX).

## Runtime Expressions

**IMPORTANT**: A value must be **entirely** a runtime expression or entirely plain text. You cannot mix plain text with `${...}` or `$${...}`. To combine static text with dynamic values, use Liquid `$${...}` or jq string concatenation `${"static " + .dynamic}`.

### jq syntax: `${...}`

```yaml
"${.field}"                     # Current data field
"${$contextVar}"                # Context variable (set / export / workflow_context)
"${$workflow.input.key}"        # Workflow input
"${$input.field}"               # Task input (inside output.as)
"${env.ENV_VAR}"                # Environment variable (jq only)
"${now | strftime(\"%Y-%m-%d\")}"
"${.items | map(.name)}"
"${.text // \"default\"}"
```

### Liquid syntax: `$${...}`

```yaml
"$${{{ variable }}}"
"$${% if condition %}yes{% else %}no{% endif %}"
"$${{{ 'now' | date: '%Y-%m-%d' }}}"
"$${{{ data | json_encode }}}"
```

- **jq** for data transformation, **Liquid** for text templating.
- Liquid **cannot** read environment variables — use jq (`${"Bearer " + env.TOKEN}`) or, for call tasks, `use.secrets`.
- `fromjson` fails on Markdown fences (```` ```json ````). Strip fences from LLM output before parsing.

## Data Flow Pattern

```
input.from → [Task Execution] → output.as → export.as → next task
```

Inside `output.as`, `$input` is the task input, so you can carry fields forward:

```yaml
- Step1:
    run: ...        # Produces {content: {text: "summary"}}
    output:
      as:
        title: ${$input.result.title}
        summary: ${.content.text}
```

A `set` task both writes context variables **and** replaces the current data with the set values. Use `export.as` to keep values available as `$name` without relying on the data flow.

## Pitfall: `if: false` Skips the *Entire* Task — Including `export.as`

When a task's `if` evaluates to false the task is skipped: the body, `output.as`, **and `export.as`** are bypassed, and the raw task input passes through unchanged. A variable you expected that task to export stays at its seed value (or is undefined, which makes a later `$var` reference fail).

```yaml
# BROKEN — when the lookup hits, CreateThread is skipped and never exports threadId.
- CreateThread:
    if: ${$existingThreadId == null}
    run: ...
    export:
      as:
        createdThreadId: ${.newId}
```

**Fix**: seed the variables up front and resolve them with an unconditional `set`:

```yaml
- ResolveThreadId:
    set:
      threadId: ${$existingThreadId // $createdThreadId}
    export:
      as:
        threadId: ${.threadId}
```

Canonical patterns in jobworkerp-rs: `workflows/news2/news-summarize-read.yml` (`ResolveThreadId`) and `memories/agent-chat-import/workers/thread-summary/thread-summary-single.yaml` (`resolveMemoryThreadId`).

## Common Patterns

```yaml
# Null-safe guard
if: '${.content // "" | gsub("^\\s+|\\s+$"; "") | length > 0}'

# Static array iteration
for:
  each: genre
  in: '${["ai_ml", "technology", "science"]}'

# Error-resilient iteration
onError: continue
```

See [Examples](references/examples.md) for complete patterns.

## Discovering Runner Schemas

For any runner (built-in, MCP server, or plugin), query the gRPC services for the latest schemas:

```bash
grpcurl -plaintext -d '{"name":"LLM"}' localhost:9000 jobworkerp.service.RunnerService/FindByName
grpcurl -plaintext -d '{"runner_name":"COMMAND"}' localhost:9000 jobworkerp.function.service.FunctionService/FindByName
```

See [Runner Schemas](references/runner-schemas.md#querying-runner-schemas-at-runtime).

## Important Notes

1. **Runner names are case-sensitive**: `COMMAND`, `LLM`, `HTTP_REQUEST`, `GRPC`, `DOCKER`, `PYTHON_COMMAND`, `WORKFLOW`, `SANDBOX`. MCP server names match `mcp-settings.toml`.
2. **`using`**: required for `LLM` and for MCP servers with several tools; optional for `GRPC` (`unary`), `WORKFLOW` (`run`), `SANDBOX` (`run`).
3. **Removed runners**: `GRPC_UNARY`, `LLM_COMPLETION`, `LLM_CHAT`, `INLINE_WORKFLOW`, `REUSABLE_WORKFLOW`, `CREATE_WORKFLOW` — use `GRPC`, `LLM`, `WORKFLOW` with `using`.
4. **Field names in settings/arguments**: camelCase is conventional (`baseUrl`, `maxTokens`); snake_case is accepted too. **Unknown fields are silently ignored**, so double-check spelling against [Runner Schemas](references/runner-schemas.md). Runner results use camelCase keys, and 64-bit integers appear as strings.
5. **Timeouts are opt-in**: a task without `timeout` has no deadline. `WORKFLOW_TASK_DEFAULT_TIMEOUT_SEC` applies only to run/call tasks without `timeout`; the workflow-level `timeout` is not inherited by inner tasks. A timeout raises `https://open-workflow-specification.org/spec/1.0.0/errors/timeout` (status 408), catchable with `try`, and cancels child jobs inside the timed-out task. See [Schema Reference](references/schema-reference.md#timeouts-and-child-job-cancellation).
6. **Schema validation** is enabled by default at runtime (`WORKFLOW_SKIP_SCHEMA_VALIDATION=true` skips it). Plugin runners must still validate their own inputs.
7. **Upstream docs**: `manual/en/src/workflow.md` (and `manual/ja/src/workflow.md`) in jobworkerp-rs.
8. **Schema sync**: the bundled schemas are refreshed with `scripts/sync-schema.sh <jobworkerp-rs-root>` in this plugin repository.
