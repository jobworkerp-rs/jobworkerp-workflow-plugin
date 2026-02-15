---
name: jobworkerp-workflow
description: >-
  Create and edit workflow YAML compliant with jobworkerp-rs Custom Serverless Workflow DSL v1.0.0.
  Use when the user requests creating workflow definitions, modifying existing workflows, or understanding workflow structure.
  Supports task execution with runners (COMMAND, LLM, HTTP_REQUEST, GRPC_UNARY, DOCKER, PYTHON_COMMAND, WORKFLOW, MCP servers, Plugins),
  for loops, fork parallel execution, switch conditional branching, try-catch error handling,
  and jq/Liquid variable expansion.
---

# Workflow YAML Creator

Skill for creating and editing workflow YAML compliant with jobworkerp-rs Custom Serverless Workflow DSL v1.0.0.

## Reference Files

- **[Schema Reference](references/schema-reference.md)**: Full workflow schema structure, all task types, runtime expression syntax
- **[Runner Schemas](references/runner-schemas.md)**: Settings/arguments JSON for each runner (COMMAND, LLM, HTTP_REQUEST, etc.)
- **[Examples](references/examples.md)**: Real workflow patterns from the project

## Workflow Basics

### Top-Level Structure

Every workflow YAML requires three top-level keys:

```yaml
document:              # Metadata
  dsl: "0.0.1"         # DSL version
  namespace: default    # Namespace
  name: my-workflow     # Workflow name
  version: "0.0.1"     # Version
input:                 # Input configuration
  schema:              # Optional validation schema
    document:
      type: object
      properties: ...
do:                    # Task list (ordered)
  - TaskName:
      ...
output:                # Optional output transformation
  as: "${...}"
```

### Task Types Overview

| Task | Purpose | Key Properties |
|------|---------|---------------|
| **runTask** | Execute runners/workers/scripts | `run.runner`, `run.worker`, `run.function`, `run.script` |
| **forTask** | Iterate over collection | `for.each`, `for.in`, `do`, `inParallel` |
| **forkTask** | Concurrent execution | `fork.branches`, `fork.compete` |
| **doTask** | Sequential subtask group | `do` (nested task list) |
| **switchTask** | Conditional branching | `switch[].when`, `switch[].then` |
| **tryTask** | Error handling | `try`, `catch.retry`, `catch.do` |
| **setTask** | Set context variables | `set` (key/value pairs) |
| **raiseTask** | Raise error | `raise.error` (type, status) |
| **waitTask** | Pause execution | `wait` (duration) |

### Common Task Properties (taskBase)

All tasks support these optional properties:

```yaml
- AnyTask:
    if: "${condition}"      # Conditional execution
    input:
      from: "${transform}"  # Transform input
    output:
      as:                   # Transform output (string or object)
        key: "${.value}"
    export:
      as:                   # Export to context variables
        varName: "${.data}"
    timeout:
      after: { seconds: 30 }
    then: continue          # Flow directive: continue|exit|end|wait|"TaskName"
    checkpoint: false       # Save state for checkpoint/restart
```

## runTask - The Most Common Task

### runRunner (Primary Method)

```yaml
- MyTask:
    run:
      runner:
        name: COMMAND              # Runner name (REQUIRED)
        using: "chat"              # Method for multi-method runners (optional)
        settings: {}               # Runner initialization settings
        arguments: {}              # Job arguments (REQUIRED)
        options:                   # Worker options
          channel: workflow
          useStatic: false
          storeSuccess: true
          storeFailure: true
          broadcastResults: false
          queueType: NORMAL        # NORMAL|WITH_BACKUP|DB_ONLY
          responseType: DIRECT     # DIRECT|NO_RESULT
      return: stdout               # stdout|stderr|code|all|none
    useStreaming: false             # Enable streaming execution
```

### runFunction (Alternative)

```yaml
run:
  function:
    runnerName: COMMAND      # Use runner by name
    # OR
    workerName: "MyWorker"   # Use pre-configured worker
    arguments: {}            # REQUIRED
```

## Runner Quick Reference

### COMMAND
```yaml
name: COMMAND
arguments:
  command: "echo"
  args: ["Hello"]
  treatNonzeroAsError: true
```

### LLM (using: chat - Recommended)
```yaml
name: LLM
using: chat
settings:
  ollama: { baseUrl: "http://...", model: "model-name", pullModel: false }
  # OR genai: { model: "gpt-4o" }  # Requires API key env var
arguments:
  messages:
    - role: system
      content: { text: "System prompt" }
    - role: user
      content: { text: "User message" }
  options: { maxTokens: 131072, temperature: 0.3, extractReasoningContent: true }
```

### HTTP_REQUEST
```yaml
name: HTTP_REQUEST
settings: { baseUrl: "https://api.example.com" }
arguments: { method: "GET", path: "/data", headers: [{ key: "Auth", value: "Bearer ..." }] }
```

### MCP Servers
```yaml
name: mcp-fetch           # Server name from mcp-settings.toml
using: fetch_html          # Tool name (for multi-tool servers)
arguments:
  argJson: '{"url": "https://example.com"}'
```

### WORKFLOW (Nested)
```yaml
name: WORKFLOW
using: run
settings: { workflowUrl: "./sub-workflow.yaml" }
arguments: { input: '{"key": "value"}' }
```

See [Runner Schemas](references/runner-schemas.md) for complete settings/arguments for all runners.

## Runtime Expressions

**IMPORTANT**: A value must be **entirely** a runtime expression or entirely plain text. You cannot mix plain text with `${...}` or `$${...}`. To combine static text with dynamic values, use Liquid `$${...}` (text interpolation) or jq `${"static " + .dynamic}` (string concatenation).

### jq syntax: `${...}`

Best for JSON data manipulation and computation.

```yaml
"${.field}"                     # Access current data field
"${$contextVar}"                # Access context variable (set by setTask/export)
"${$workflow.input.key}"        # Access workflow input
"${$input.field}"               # Access task input (in output.as)
"${$task.output}"               # Access task output
"${env.ENV_VAR}"                # Access environment variable
"${now | strftime(\"%Y-%m-%d\")}"  # Date formatting
"${.items | map(.name)}"       # Array operations
"${if .x then .y else .z end}" # Conditional
"${.text // \"default\"}"      # Null coalescing (alternative operator)
"${.text | gsub(\"old\"; \"new\")}"  # String operations
```

### Liquid syntax: `$${...}`

Best for string templating and mixed text+data.

```yaml
"$${{{ variable }}}"                           # Variable interpolation
"$${% if condition %}yes{% else %}no{% endif %}"  # Conditional
"$${{{ 'now' | date: '%Y-%m-%d' }}}"           # Date
"$${{{ text | url_encode }}}"                  # URL encode
"$${{{ data | json_encode }}}"                 # JSON encode
```

### When to Use Which

- **jq `${}`**: JSON transformation, arithmetic, filtering, complex data manipulation
- **Liquid `$${}**`: String construction with embedded variables, conditional text blocks, date formatting in paths
- **Key rule**: jq for data, Liquid for text/templates

## Data Flow Pattern

```
input.from → [Task Execution] → output.as → export.as → next task
```

### Preserving Data Through Steps with $input

Inside `output.as`, `$input` refers to the task's input (data before execution):

```yaml
- Step1:
    run: ...        # Produces {content: {text: "summary"}}
    output:
      as:
        title: ${$input.result.title}    # Preserve from input
        summary: ${.content.text}        # New from this task's output
- Step2:
    run: ...        # Receives {title: "...", summary: "..."}
    output:
      as:
        title: ${$input.title}           # Pass through
        genre: ${.content.text}          # New from this task
        summary: ${$input.summary}       # Pass through
```

### Context Variables with setTask + export

```yaml
- InitVars:
    set:
      counter: 0
      items: []
    export:
      as:
        counter: ${.counter}   # Now accessible as ${$counter}
        items: ${.items}       # Now accessible as ${$items}
- LaterStep:
    set:
      counter: ${$counter + 1}
      items: ${$items + ["new"]}
```

## Common Patterns

### Null-safe Guard Condition
```yaml
if: '${.content // "" | gsub("^\\s+|\\s+$"; "") | length > 0}'
```

### For Loop with Static Array
```yaml
for:
  each: genre
  in: '${["ai_ml", "technology", "science"]}'
```

### Thread Management (Slack)
```yaml
output:
  as:
    threadTs: ${.ts // $input.threadTs}  # First post creates thread, replies use it
```

### Dynamic Strings with Liquid
```yaml
path: |-
  $${
  {%- assign year = 'now' | date: '%Y' -%}
  {%- assign month = 'now' | date: '%m' -%}
  {{ year }}/{{ month | prepend: '00' | slice: -2, 2 }}/{{ 'now' | date: '%d' }}}
```

### Error-Resilient Iteration
```yaml
for:
  each: item
  in: ${.items}
onError: continue    # Skip failures, process remaining items
```

See [Examples](references/examples.md) for more comprehensive patterns with full context.

## Discovering Runner Schemas

For any runner (built-in, MCP server, or plugin), query the gRPC services to get the latest settings/arguments schema:

- **RunnerService** (`FindByName`/`FindListBy`): Returns `RunnerData` with `runner_settings_proto` and `method_proto_map` (per-method `args_proto`, `result_proto`)
- **FunctionService** (`FindByName`/`FindList`): Returns `FunctionSpecs` with JSON Schema versions (`settings_schema`, per-method `arguments_schema`, `result_schema`)

```bash
# Get runner schema by name (works for built-in, MCP, and plugin runners)
grpcurl -plaintext -d '{"name":"LLM"}' localhost:9000 jobworkerp.service.RunnerService/FindByName

# Get JSON Schema version (more convenient for workflow authoring)
grpcurl -plaintext -d '{"runner_name":"COMMAND"}' localhost:9000 jobworkerp.function.service.FunctionService/FindByName
```

See [Runner Schemas](references/runner-schemas.md) for full details on the query APIs and built-in runner schemas.

## Important Notes

1. **Runner names are case-sensitive**: `COMMAND`, `LLM`, `HTTP_REQUEST`, `GRPC_UNARY`, `DOCKER`, `PYTHON_COMMAND`, `SLACK_POST_MESSAGE`, `WORKFLOW`
2. **MCP server names**: Match the name in `mcp-settings.toml` (e.g., `mcp-fetch`, `filesystem`)
3. **Plugin/MCP runner schemas**: Query via RunnerService or FunctionService gRPC APIs to get the latest settings/arguments definitions
4. **`using` parameter**: Required for multi-method runners (LLM: `chat`/`completion`, WORKFLOW: `run`/`create`) and multi-tool MCP servers
5. **Deprecated runners**: Do NOT use `LLM_COMPLETION`, `LLM_CHAT`, `INLINE_WORKFLOW`, `REUSABLE_WORKFLOW`, `CREATE_WORKFLOW`. Use `LLM` or `WORKFLOW` with `using` instead.
6. **Settings field names**: Use camelCase in YAML (matching JSON protobuf serialization), e.g., `baseUrl`, `pullModel`, `maxTokens`
7. **Streaming**: Set `useStreaming: true` on runTask for LLM or long-running tasks that benefit from progress monitoring
8. **Schema validation**: Full JSON Schema validation is disabled by default. Enable with `WORKFLOW_ENABLE_FULL_SCHEMA_VALIDATION=true` env var.
9. **Schema file**: The authoritative schema is at `runner/schema/workflow.yaml` (932 lines)
10. **Workflow docs**: See `WORKFLOW.md` (English) or `WORKFLOW_ja.md` (Japanese) for usage documentation
