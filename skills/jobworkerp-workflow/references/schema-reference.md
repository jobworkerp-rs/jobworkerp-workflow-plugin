# Workflow Schema Quick Reference

jobworkerp-rs workflow DSL: Open Workflow DSL v1.0.0 flow control plus jobworkerp extensions.

This is the quick reference. For the machine-checkable definition see [`workflow-schema.yaml`](workflow-schema.yaml) (readable) and [`workflow-validation-schema.json`](workflow-validation-schema.json) (what the runtime validator uses).

## Top-Level Structure

<!-- validate:skip -->
```yaml
document:        # REQUIRED
  dsl: "0.0.1"   # REQUIRED - semver
  namespace: default  # REQUIRED - alphanumeric + hyphens
  name: my-workflow   # REQUIRED - alphanumeric + hyphens
  version: "0.0.1"    # REQUIRED - semver
  title: "..."        # Optional
  summary: "..."      # Optional - Markdown
  tags: {}            # Optional
  metadata: {}        # Optional
input:           # Optional - omitted: no validation, no input.from, input passed through
  schema: ...
  from: ...
use:             # Optional - reusable components (see below)
  timeouts: {}
  authentications: {}
  secrets: []
timeout:         # Optional - whole-workflow timeout, inline or a use.timeouts name
  after: { hours: 2 }
do:              # REQUIRED - task list
  - TaskName: ...
output:          # Optional
  schema: ...
  as: ...
checkpointing:   # Optional
  enabled: false
  storage: "memory"  # "memory" | "redis"
```

## Reusable Components (`use`)

| Key | Type | Referenced by |
|-----|------|---------------|
| `timeouts` | map name → `{after: duration}` | `timeout: <name>` on a task or the workflow |
| `authentications` | map name → bearer/basic policy | `authentication: { use: <name> }` in call tasks |
| `secrets` | list of names | `{ use: <name> }` inside a policy, or `$secrets.<name>` in call task expressions |

`use.catalogs`, `use.extensions`, `use.functions`, `use.errors`, and named retry policies are **not** supported.

### Secrets

- Values never appear in YAML. Each declared name is read from `WORKFLOW_SECRET_<UPPER_SNAKE_NAME>` (non-alphanumerics become `_`: `github-token` → `WORKFLOW_SECRET_GITHUB_TOKEN`).
  - bearer: the token string (or `{"token": "..."}` JSON)
  - basic: `{"username": "...", "password": "..."}` JSON
- Three ways to bind a scheme value:
  1. `bearer: { use: github-token }` / `basic: { use: creds }` (preferred)
  2. Expression: `bearer: { token: "${ $secrets.api_token }" }` (`$secrets["github-token"]` for hyphenated names; Liquid: `{{ secrets.api_token }}`)
  3. Literal value (discouraged for credentials)
- Only declared names resolve; an undeclared reference is an error. `$secrets` is available only while evaluating **call** tasks and is never written to the context. `secrets` is reserved: workflow input cannot override it.

## Task Types

Each task item in `do` is a single-key object: `- TaskName: { taskDefinition }`.

### runTask

`run` holds exactly one of `runner`, `function`, `worker`, `script`, `shell`, `container`, `workflow`.

| Form | `await` | `return` | Notes |
|------|:-:|:-:|-------|
| `runner` | yes | no | Runner by name with `settings`, `arguments`, `options`, `using` |
| `function` | yes | no | `runnerName` (+`settings`/`options`) or `workerName` |
| `worker` | yes | no | Pre-configured worker by `name` |
| `workflow` | yes | no | Nested workflow; output is the WORKFLOW runner result |
| `shell` | yes | yes | COMMAND runner; does not fail on non-zero exit by default |
| `container` | yes | yes | DOCKER runner; does not fail on non-zero exit by default |
| `script` | yes | yes | PYTHON_COMMAND runner; non-zero exit always fails; no streaming |

- `await` (default `true`): `false` enqueues fire-and-forget and passes the task input through. Not allowed with `useStreaming: true`.
- `return` (default `stdout`): `stdout` / `stderr` (raw strings, not parsed as JSON), `code`, `all` (`{code, stdout, stderr}`), `none`.
- `useStreaming` (sibling of `run`, default `false`): streams intermediate results via ListenStream and collects the final result.

#### run.runner

<!-- validate:skip -->
```yaml
run:
  runner:
    name: COMMAND           # REQUIRED
    using: "chat"           # Method for multi-method runners
    settings: {}            # Runner initialization settings
    arguments: {}           # REQUIRED
    options:                # workerOptions (below)
      channel: workflow
```

#### run.function

<!-- validate:skip -->
```yaml
run:
  function:
    runnerName: COMMAND     # Either runnerName ...
    # workerName: MyWorker  # ... or workerName
    using: "..."            # Optional method
    settings: {}            # runnerName only
    options: {}             # runnerName only
    arguments: {}           # REQUIRED
```

#### run.worker

<!-- validate:skip -->
```yaml
run:
  worker:
    name: "MyWorker"        # REQUIRED
    using: "run"            # Optional
    arguments: {}           # REQUIRED
```

#### run.shell

<!-- validate:skip -->
```yaml
run:
  shell:                    # or a plain string: `shell: "echo hello"`
    command: ls             # REQUIRED
    args: ["-la"]
    workingDir: /tmp
    withMemoryMonitoring: false   # jobworkerp extension
    treatNonzeroAsError: true     # jobworkerp extension
    successExitCodes: [1]         # jobworkerp extension
  return: all
```

#### run.container

<!-- validate:skip -->
```yaml
run:
  container:
    image: alpine:3.20      # REQUIRED
    command: ["echo", "hi"]
    entrypoint: []
    env: { KEY: value }
    user: "1000"
    workingDir: /work
    timeoutSec: 300               # jobworkerp extension
    treatNonzeroAsError: true     # jobworkerp extension
    successExitCodes: []          # jobworkerp extension
  return: stdout
```

#### run.script

<!-- validate:skip -->
```yaml
run:
  script:
    language: python        # REQUIRED
    code: |                 # inline, or `source:` for an external resource
      print("Hello")
    arguments: {}
    environment: {}
  return: stdout
```

#### run.workflow

<!-- validate:skip -->
```yaml
run:
  workflow:
    workflowUrl: ./child.yaml     # or workflowData: <inline YAML/JSON string>
    input: { value: 1 }           # non-string values are serialized as JSON
    executionId: "..."            # Optional
```

The parent `workflow_context` is inherited implicitly (`workflowContext` is not a DSL field). The output is the WORKFLOW runner result (`id`, `output` as a string, `status`, ...).

### callTask

#### call: http

<!-- validate:skip -->
```yaml
- CallApi:
    call: http
    with:
      method: post                 # REQUIRED
      endpoint:                    # REQUIRED - URI string or object
        uri: https://api.example.com/items
        authentication:            # inline policy or { use: <name> }
          bearer: { use: api-token }
      headers: { Accept: application/json }   # values converted to strings
      query: { page: 1 }
      body: { name: "x" }          # non-string bodies are sent as JSON
      output: content              # content (default) | response
```

- `output: content` → response body (JSON-parsed when the content type is JSON).
- `output: response` → `{ statusCode, headers, body }`.
- Supported auth: bearer and basic. Not supported: digest / oauth2 / oidc / certificate, `output: raw`. `redirect` is accepted but ignored.

#### call: grpc

<!-- validate:skip -->
```yaml
- GetUser:
    call: grpc
    with:
      service:                     # REQUIRED
        name: example.UserService  # REQUIRED - fully qualified
        host: localhost            # REQUIRED
        port: 50051
        authentication:            # bearer only (basic is rejected)
          use: grpc-auth
      method: GetUser              # REQUIRED
      arguments: { id: "${.userId}" }
```

- Unary only, through the GRPC runner with server reflection. `proto` is accepted by the schema but rejected at run time.
- Output: `{ code, body, metadata, message? }` where `body` is the JSON-parsed response.

### forTask

<!-- validate:skip -->
```yaml
- MyLoop:
    for:
      each: item       # default: item
      in: "${.array}"  # REQUIRED
      at: index        # default: index
    while: "${...}"
    inParallel: false
    onError: break     # break (default) | continue
    do:
      - ...
```

With `inParallel: true` and `onError: break`, a failing item cancels the other items' child jobs.

### forkTask

<!-- validate:skip -->
```yaml
- MyConcurrent:
    fork:
      branches:
        - Branch1: ...
        - Branch2: ...
      compete: false   # true: first completed branch wins, losers' child jobs are cancelled
```

### doTask

<!-- validate:skip -->
```yaml
- MyGroup:
    do:
      - SubTask1: ...
      - SubTask2: ...
```

### switchTask

```yaml
- MySwitch:
    switch:
      - case1:
          when: "${.value == 1}"
          then: continue
      - case2:
          when: "${.value == 2}"
          then: exit
      - default:
          then: end        # no `when` = default case
```

### tryTask

<!-- validate:skip -->
```yaml
- MyTry:
    try:
      - RiskyTask: ...
    catch:
      errors:
        with:
          type: "https://..."    # static filters: type, status, instance, title, details
          status: 500
      as: error                  # default: error
      when: "${...}"
      exceptWhen: "${...}"
      retry:                     # inline policy only (string references are not implemented)
        delay: { seconds: 5 }
        backoff:
          exponential: {}        # constant | exponential | linear
        limit:
          attempt:
            count: 3
            duration: { minutes: 5 }
      do:
        - FallbackTask: ...
```

A caught error has `type`, `status`, `instance`, `title`, `detail` (there is no `message` field).

### setTask

```yaml
- MySet:
    set:
      myVar: "${.someValue}"
      computed: "${.a + .b}"
```

The values become context variables (`$myVar` / `{{ myVar }}`) **and** replace the current data passed to the next task.

### raiseTask

```yaml
- NotFound:
    raise:
      error:
        type: https://example.com/errors/not-found   # REQUIRED - absolute URI
        status: 404                                  # REQUIRED
        title: "Not Found"                           # runtime expressions allowed
        detail: '${ "id=" + .id }'                   # runtime expressions allowed
```

`raise.error` may also be a runtime-expression string. A string result becomes the `detail` of a default runtime error (status 500); an Error object result is raised unchanged, which rethrows a caught error:

<!-- validate:skip -->
```yaml
catch:
  as: error
  do:
    - rethrow:
        raise:
          error: "${ $error }"
```

### waitTask

```yaml
- MyWait:
    wait:
      seconds: 30      # or ISO 8601 "PT30S", or {days, hours, minutes, seconds, milliseconds}
```

## taskBase - Common Properties

<!-- validate:skip -->
```yaml
- AnyTask:
    if: "${...}"
    input:  { from: "${...}", schema: ... }
    output: { as: "${...}", schema: ... }
    export: { as: "${...}", schema: ... }
    timeout: { after: { seconds: 30 } }   # or the name of a use.timeouts entry
    then: continue
    checkpoint: false
    metadata: {}
```

### `if: false` skips the whole task (including `export.as`)

The body, `output.as`, and `export.as` are bypassed and the raw input passes through. Seed variables up front and resolve them with an unconditional `set` (see SKILL.md "Pitfall").

## Timeouts and Child Job Cancellation

- `timeout` is optional everywhere; without it a task has no deadline.
- `WORKFLOW_TASK_DEFAULT_TIMEOUT_SEC`, when set, applies only to **run/call** tasks without `timeout` — never to do/try/for/fork, so outer tasks need no longer timeout than their children.
- The workflow-level `timeout` covers the whole run only; it is not a default for inner tasks.
- Expiry raises type `https://open-workflow-specification.org/spec/1.0.0/errors/timeout`, status `408` — catch it with `catch.errors.with.type`.
- In-flight child jobs (from run/call tasks) are cancelled when:
  - the workflow job is cancelled or hits its job timeout
  - a task times out (only child jobs inside that task)
  - an `inParallel` for with `onError: break` stops after a failure
  - a `compete: true` fork has a winner (losing branches)
- A stream consumer disconnecting does **not** cancel child jobs.

## workerOptions

<!-- validate:skip -->
```yaml
options:
  channel: workflow           # concurrency channel
  queueType: NORMAL           # NORMAL | WITH_BACKUP | DB_ONLY
  responseType: DIRECT        # DIRECT | NO_RESULT
  storeSuccess: true
  storeFailure: true
  useStatic: false            # pooled, persisted worker
  broadcastResults: false
  retry:
    delay: { seconds: 5 }
    backoff: { exponential: {} }
    limit: { attempt: { count: 3 } }
```

Valid inside `run.runner` and `run.function` (with `runnerName`) only.

## Runtime Expressions

**No mixing of plain text and expressions.** A value is either entirely `${...}` / `$${...}` or entirely plain text.

- **WRONG**: `"Bearer ${env.API_TOKEN}"`
- **CORRECT**: `"${\"Bearer \" + env.API_TOKEN}"` — jq concatenation
- **CORRECT**: `"$${Bearer {{ token }}}"` — Liquid with a context variable
- **WRONG**: `"$${Bearer {{ env.API_TOKEN }}}"` — Liquid cannot read environment variables

### jq: `${...}`

<!-- validate:skip -->
```yaml
"${.key}"  "${.nested.field}"  "${.array[0]}"
"${$myVariable}"               # context variable
"${$workflow.input.key}"       # workflow input
"${$workflow.id}"
"${$task.input}"  "${$task.raw_output}"  "${$task.output}"
"${$input.field}"              # task input (in output.as)
"${env.ENV_VAR}"               # environment variable (jq only)
"${.items | length}"  "${.a + .b}"  "${.items | map(.name)}"
"${if .x then .y else .z end}"
"${now | strftime(\"%Y-%m-%d\")}"
"${.text | fromjson}"          # strip ```json fences first
"${.data | tojson}"
```

### Liquid: `$${...}`

<!-- validate:skip -->
```yaml
"$${{{ myVariable }}}"
"$${{{ workflow.input.key }}}"
"$${% if condition %}true{% else %}false{% endif %}"
"$${% for item in items %}{{ item }}{% endfor %}"
"$${{{ text | slice: 0, 100 }}}"
"$${{{ text | url_encode }}}"
"$${{{ data | json_encode }}}"
"$${{{ 'now' | date: '%Y-%m-%d' }}}"
```

### Key Differences

| Feature | jq `${...}` | Liquid `$${...}` |
|---------|-------------|-----------------|
| JSON manipulation | Strong | Limited |
| String templating | Limited | Strong |
| Environment variables | `env.NAME` | Not available |
| Data access | `.key`, `$var` | `{{ var }}`, `{{ workflow.input.key }}` |

## Flow Directives

| Directive | Description |
|-----------|-------------|
| `continue` | Continue to the next task (default) |
| `exit` | Exit the current task scope |
| `end` | End workflow execution |
| `wait` | Pause the workflow (waiting state) |
| `"TaskName"` | Jump to a named task |

## Input/Output/Export Pattern

1. `input.from` transforms the incoming data
2. The task executes
3. `output.as` shapes the result (`$input` = the task input)
4. `export.as` writes context variables

<!-- validate:skip -->
```yaml
output:
  as:
    title: ${$input.title}
    summary: ${.content.text}
```
