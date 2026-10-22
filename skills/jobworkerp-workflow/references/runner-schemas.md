# Runner Settings & Arguments Reference

Each runner's `settings` and `arguments` in workflow YAML are JSON representations of its protobuf messages (jobworkerp-rs `runner/protobuf/jobworkerp/runner/`).

**Field naming and parsing**
- Input (`settings` / `arguments`): camelCase (`baseUrl`) is conventional; the original snake_case (`base_url`) is accepted as well. Enum values are case-insensitive (`role: user`).
- **Unknown fields are silently dropped** — a misspelled field does not raise an error, it is just ignored. Check names against this file or the runtime schema.
- Output (runner results seen in `output.as`): camelCase keys. 64-bit integers (`uint64`/`int64`) are JSON strings.

**For the workflow DSL itself** (task types, taskBase properties) see [Schema Reference](schema-reference.md) and the bundled schemas.

**Runtime expressions:** a value must be entirely `${...}` / `$${...}` or entirely plain text — `"Bearer ${env.TOKEN}"` is invalid; use `${"Bearer " + env.TOKEN}`. Liquid cannot read environment variables. See [Schema Reference](schema-reference.md#runtime-expressions).

## Querying Runner Schemas at Runtime

The schemas below are the built-in defaults. For the **latest** schema of any runner (including MCP servers and plugins), query the gRPC services.

### RunnerService (proto: `jobworkerp.service.RunnerService`)

Use `FindByName` or `FindListBy` to get `RunnerData`:

```
RunnerData {
  name: string                          # Runner name (e.g., "COMMAND", "mcp-fetch")
  runner_settings_proto: string         # Protobuf definition for settings
  method_proto_map: MethodProtoMap {    # Per-method schemas
    schemas: map<string, MethodSchema>  # Key: method name (e.g., "run", "fetch_html")
  }
}

MethodSchema {
  args_proto: string                    # Protobuf definition for method arguments
  result_proto: string                  # Protobuf definition for method result
  description: optional string
  output_type: StreamingOutputType      # NON_STREAMING | STREAMING | BOTH
  require_client_stream: bool           # Method needs a client stream (not usable from workflows)
}
```

- **Single-method runners** (COMMAND, HTTP_REQUEST, DOCKER, PYTHON_COMMAND): one entry keyed `"run"`
- **Multi-method runners**: LLM (`chat`, `completion`, `embedding`, `token_count`), GRPC (`unary`, `streaming`), WORKFLOW (`run`, `create`), SANDBOX (`run`, `run_with_client`)
- **MCP servers**: entries keyed by tool name (e.g., `"fetch"`)
- **Plugins**: entries keyed by the plugin's method names

### FunctionService (proto: `jobworkerp.function.service.FunctionService`)

Use `FindByName` or `FindList` to get `FunctionSpecs` with **JSON Schema** (converted from protobuf):

```
FunctionSpecs {
  name: string
  settings_schema: string               # JSON Schema for settings
  methods: MethodSchemaMap {
    schemas: map<string, MethodSchema>  # Key: method name
  }
}

MethodSchema (function layer) {
  arguments_schema: string              # JSON Schema for arguments
  result_schema: optional string
  description: optional string
  output_type: StreamingOutputType
}
```

### CLI Examples

```bash
grpcurl -plaintext localhost:9000 jobworkerp.service.RunnerService/FindListBy
grpcurl -plaintext -d '{"name":"LLM"}' localhost:9000 jobworkerp.service.RunnerService/FindByName
grpcurl -plaintext -d '{"name":"mcp-fetch"}' localhost:9000 jobworkerp.service.RunnerService/FindByName
grpcurl -plaintext -d '{"runner_name":"COMMAND"}' \
  localhost:9000 jobworkerp.function.service.FunctionService/FindByName
```

---

## COMMAND Runner

No settings. Also used by the `run.shell` task form.

### Arguments (CommandArgs)

```yaml
arguments:
  command: "echo"                    # REQUIRED - command (when args is empty, split POSIX-style: "echo 'hi'")
  args: ["Hello", "World"]
  withMemoryMonitoring: false
  treatNonzeroAsError: false         # Non-zero exit => task error (unless in successExitCodes)
  successExitCodes: [0]
  workingDir: "/tmp"
  stdin: "text piped to the process" # Empty: inherit the worker's stdin
```

### Result (CommandResult)

`exitCode`, `stdout`, `stderr`, `executionTimeMs`, `startedAt`, `maxMemoryUsageKb` (the last three are 64-bit → strings).

Note: `return` is not available on `run.runner`; use `output.as: ${.stdout}`, or the `run.shell` form with `return`.

---

## LLM Runner (Unified, Multi-Method)

`using` is **required** (no default):
- `chat` — chat with messages (recommended)
- `completion` — text completion
- `embedding` — embedding vectors
- `token_count` — count tokens of text or of a rendered chat/completion request

### Settings (LLMRunnerSettings)

```yaml
settings:
  # One of:
  ollama:
    baseUrl: "http://localhost:11434"  # Optional
    model: "llama3"                    # REQUIRED
    systemPrompt: "You are..."
    pullModel: false
  # OR
  genai:                               # Cloud / OpenAI-compatible providers
    model: "gpt-4o"                    # REQUIRED - model name selects the provider
    systemPrompt: "You are..."
    baseUrl: "http://localhost:8080/v1/"   # Passed through as-is: include /v1/ for OpenAI-compatible servers
  # API keys come from env vars: OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, COHERE_API_KEY, GROQ_API_KEY, XAI_API_KEY, DEEPSEEK_API_KEY, ...

  embeddingChunking:                   # Optional - default chunking for `using: embedding`
    maxChunkTokens: 512
    minChunkTokens: 64
    tokenEstimation: TIKTOKEN          # CHARACTER_ESTIMATION | TIKTOKEN | HF_TOKENIZER
    tiktokenEncoding: "cl100k_base"    # or tokenizerHfRepo / tokenizerFilePath
```

### Arguments for `using: chat` (LLMChatArgs)

```yaml
using: chat
arguments:
  model: "override-model"      # Optional
  messages:                    # REQUIRED
    - role: system             # SYSTEM | USER | ASSISTANT | TOOL
      content:
        text: "System prompt"
    - role: user
      content:
        text: "User message"
        # OR image: { contentType: "image/png", source: { url: "..." } }   # or source.base64
        # OR toolCalls: { calls: [{ callId, fnName, fnArguments }] }
        # OR toolExecutionRequests: { requests: [{ callId, fnName, fnArguments }] }
        # OR toolResults: { results: [{ callId, fnName, content, isError }] }
  options:
    maxTokens: 8192
    temperature: 0.3
    topP: 0.9
    repeatPenalty: 1.1
    repeatLastN: 64
    seed: 42
    extractReasoningContent: true   # false (with reasoningEffort unset) requests "no thinking"
    reasoningEffort: "medium"       # none|minimal|low|medium|high|xhigh|max or a token budget ("2048"); overrides extractReasoningContent
    chatTemplateKwargs: '{"enable_thinking": false}'  # JSON object string for OpenAI-compatible local servers; ignored by Ollama
  functionOptions:
    useFunctionCalling: true
    functionSetName: "my-set"       # exclusive with useRunnersAsFunction / useWorkersAsFunction
    useRunnersAsFunction: true
    useWorkersAsFunction: true
    isAutoCalling: true             # default false: tool calls are returned for approval
    autoSelectFunctionSet: false    # LLM picks a FunctionSet (ignored when functionSetName is set)
    clientToolsJson: '[...]'        # OpenAI `tools` array; client-driven mode, exclusive with the server-side knobs
    toolChoice: "auto"              # auto | none | required | {"type":"function","function":{"name":"..."}}
    parallelToolCalls: true
  jsonSchema: '{"type":"object","properties":{}}'  # Structured output
```

### Arguments for `using: completion` (LLMCompletionArgs)

```yaml
using: completion
arguments:
  model: "override-model"
  systemPrompt: "..."
  prompt: "Generate text..."   # REQUIRED
  options: {}                  # Same fields as chat options
  functionOptions:             # Only these four fields
    useFunctionCalling: true
    functionSetName: "my-set"
    useRunnersAsFunction: false
    useWorkersAsFunction: false
  context:                     # Optional - Ollama generation context from a previous result
    ollamaContext: { data: [1, 2, 3] }
  jsonSchema: "..."
```

### Arguments for `using: embedding` (LLMEmbeddingArgs)

```yaml
using: embedding
arguments:
  model: "nomic-embed-text"    # Optional override
  inputs:
    - text: "first document"
    # OR image: { contentType, source: { url | base64 } } / media: { contentType, source }
  options:
    dimensions: 768
    truncate: "END"
    embeddingType: "..."
    encodingFormat: "float"
    user: "..."
  chunking: { maxChunkTokens: 512 }   # Overrides settings.embeddingChunking
```

### Arguments for `using: token_count` (TokenCountArgs)

```yaml
using: token_count
arguments:
  text: { texts: ["hello", "world"] }
  # OR completion: { prompt: "..." }          # LLMCompletionArgs
  # OR chat: { request: { messages: [...] } } # LLMChatArgs
```

### Results

- chat: `content.text` (or `content.toolCalls`), `reasoningContent`, `done`, `usage`, `pendingToolCalls`, `requiresToolExecution`, `toolExecutionResults`, `toolExecutionStarted`
- completion: `content.text`, `reasoningContent`, `done`, `context`, `usage`
- embedding: `embeddings[]` (`vector`, `inputIndex`, `beginPosition`, `endPosition`, `content`, `dimensions`), `usage`
- token_count: one of `textSuccess` (`counts`, `totalTokens`), `renderedRequestSuccess` (`renderedInputTokens`, ...), `error` (`code`, `detail`)

---

## HTTP_REQUEST Runner

For simple REST calls, the `call: http` task (with secret-based auth) is usually more convenient.

### Settings (HttpRequestRunnerSettings)

```yaml
settings:
  baseUrl: "https://api.example.com"  # REQUIRED
```

### Arguments (HttpRequestArgs)

```yaml
arguments:
  method: "POST"                      # REQUIRED
  path: "/api/v1/data"                # REQUIRED
  headers:
    - key: "Content-Type"
      value: "application/json"
  body: '{"key": "value"}'
  queries:
    - key: "page"
      value: "1"
```

### Result (HttpResponseResult)

`statusCode`, `headers`, `content` (string body). Streaming execution yields `chunk` items.

---

## GRPC Runner (Unified, Multi-Method)

- `using: unary` (default) — unary call
- `using: streaming` — server-streaming call

The `call: grpc` task is a simpler alternative for unary calls with reflection.

### Settings (GrpcRunnerSettings)

```yaml
settings:
  host: "grpc.example.com"           # REQUIRED
  port: 50051                         # REQUIRED
  tls: true
  connectionTimeout: 5000             # ms
  maxMessageSize: 4194304
  authToken: "token"
  useReflection: true
  tlsConfig:
    caCertPath: "/path/ca.pem"
    clientCertPath: "/path/client.pem"
    clientKeyPath: "/path/client-key.pem"
    serverNameOverride: "hostname"
  proto:                              # Descriptor source instead of reflection
    source: "https://example.com/service.proto"   # https://, http://, file://, or inline proto text
    fetchHeaders: { Authorization: "Bearer ..." }
    allowInsecureHttp: false
  # The following OVERRIDE the same fields in arguments when set:
  method: "package.Service/Method"
  metadata: { x-tenant: "a" }         # settings keys win over argument keys
  timeout: 5000                       # ms
  asJson: true
```

### Arguments (GrpcArgs)

```yaml
using: unary
arguments:
  method: "package.Service/Method"    # Ignored when settings.method is set
  jsonBody: '{"field": "value"}'      # Reflection / proto-descriptor mode
  # OR body: "<base64>"               # Raw protobuf bytes, base64 in JSON
  metadata: { authorization: "Bearer token" }
  timeout: 5000
  asJson: true                        # Convert the response to JSON
  proto: { source: "file:///protos/service.proto" }  # Used when settings.proto is unset
```

### Result

- unary: `metadata`, `body`, `code`, `message`, `jsonBody`
- streaming: `metadata`, `code`, `message`, and `jsonBody` or `bodies.items`

---

## DOCKER Runner

Also used by the `run.container` task form.

### Settings (DockerRunnerSettings)

```yaml
settings:
  fromImage: "python:3.11-slim"       # Image to pull
  fromSrc: "..."
  repo: "myrepo"
  tag: "latest"
  platform: "linux/amd64"
  env: ["VAR=value"]
  volumes: ["/host:/container"]
  workingDir: "/app"
  entrypoint: ["python"]
  timeoutSec: 3600                    # Used when useStatic: true (default 3600)
```

### Arguments (DockerArgs)

```yaml
arguments:
  image: "python:3.11-slim"           # useStatic: false only
  user: "appuser"
  exposedPorts: ["8080/tcp"]
  env: ["KEY=value"]
  cmd: ["python", "script.py"]
  argsEscaped: false
  volumes: ["/data:/data"]
  workingDir: "/app"
  entrypoint: ["python"]
  networkDisabled: false
  shell: ["/bin/sh", "-c"]
  timeoutSec: 300                     # useStatic: false only
  treatNonzeroAsError: true
  successExitCodes: [0]
```

### Result (DockerResult)

`exitCode`, `stdout`, `stderr`, `containerId`, `executionTimeMs`, `startedAt`

---

## PYTHON_COMMAND Runner

Also used by the `run.script` task form (`language: python`).

### Settings (PythonCommandRunnerSettings)

```yaml
settings:
  pythonVersion: "3.11"               # REQUIRED
  uvPath: "/usr/bin/uv"
  # One of:
  packages:
    list: ["pandas", "numpy"]
  # OR
  requirementsUrl: "https://..."
```

### Arguments (PythonCommandArgs)

```yaml
arguments:
  envVars:
    API_KEY: "value"
  # One of (REQUIRED):
  scriptContent: |
    print("Hello")
  # OR scriptUrl: "https://..."
  # Optional input data (one of):
  dataBody: '{"key": "value"}'
  # OR dataUrl: "https://..."
  withStderr: true
```

### Result (PythonCommandResult)

`exitCode`, `output` (stdout), `outputStderr`

---

## SANDBOX Runner (Multi-Method, streaming only)

Runs a command in an isolated micro-VM. Every method is streaming-only, so a workflow task must set `useStreaming: true`. `run_with_client` needs a client stream and cannot be used from workflows. Details: jobworkerp-rs `manual/ja/src/runners/sandbox.md`.

```yaml
- RunInSandbox:
    useStreaming: true
    run:
      runner:
        name: SANDBOX
        settings:
          allowedImages: ["alpine:3.20"]
          defaultExecTimeoutMs: 60000
        arguments:
          command: "sh"                # REQUIRED
          args: ["-c", "echo hello"]
          workingDir: "/work"
          env: { KEY: value }
          timeoutMs: 30000
          treatNonzeroAsError: true
          vm: { image: "alpine:3.20", cpus: 1, memoryMib: 512 }
          network: { enabled: false }
```

Other settings: `vm`, `network` (rules/profiles), `allowedHostMounts`. Other args: `user`, `successExitCodes`, `stdin` (bytes), `tty`. Result stream items are `output` (`stream`, `data`) followed by `exit` (`exitCode`, `executionTimeMs`, `sandboxId`).

---

## WORKFLOW Runner (Multi-Method)

For plain nesting prefer the `run.workflow` task form. Use the runner directly for `using: create`, or when you need `workflowContext` / checkpoints.

### Settings (WorkflowRunnerSettings)

```yaml
settings:
  # One of (optional for 'run'):
  workflowUrl: "./path/to/workflow.yaml"
  # OR workflowData: "<inline YAML/JSON>"
  workflowContext: '{"api_url": "https://..."}'  # Optional; merged with args.workflowContext (settings keys win on conflict)
```

### Arguments for `using: run` (default) - WorkflowRunArgs

```yaml
using: run
arguments:
  workflowUrl: "./another.yaml"      # Optional override (or workflowData)
  input: '{"key": "value"}'          # Workflow input (JSON or plain string)
  workflowContext: '{"key": "val"}'  # Context variables (JSON object string)
  executionId: "uuid-v7"
  fromCheckpoint:
    position: "/do/2"
    data:
      workflow: { name: "...", input: "...", contextVariables: "..." }
      task: { input: "...", output: "...", contextVariables: "...", flowDirective: "..." }
```

### Arguments for `using: create` - CreateWorkflowArgs

```yaml
using: create
arguments:
  workflowUrl: "./workflow.yaml"     # One of (REQUIRED), or workflowData
  name: "new-workflow-worker"        # REQUIRED - worker name
  workflowContext: '{"key": "val"}'  # Optional - stored with the worker
  workerOptions:
    retryPolicy: { type: "EXPONENTIAL", interval: 1000, maxRetry: 3 }
    channel: "workflow"
    queueType: "NORMAL"              # NORMAL | WITH_BACKUP | DB_ONLY
    responseType: "DIRECT"
    storeSuccess: true
    storeFailure: true
    useStatic: false
    broadcastResults: false
```

### Result

- run: `id`, `output` (string), `position`, `status`, `errorMessage`
- create: `workerId.value`

---

## MCP Server Runners

MCP servers configured in `mcp-settings.toml` are registered as runners by server name. Each tool is a method: select it with `using` (required when the server exposes several tools, optional for single-tool servers). Arguments are the **tool's own input fields**, written directly — their schema is generated from the tool's inputSchema (query RunnerService/FunctionService to see it).

```yaml
run:
  runner:
    name: mcp-fetch              # MCP server name
    using: fetch                 # Tool name
    arguments:
      url: "https://example.com"
      max_length: 5000
    options:
      channel: workflow
```

The legacy `toolName` / `argJson` wrapper is not supported in workflows.

### Result (McpServerResult)

`content[]` items are one of `text.text`, `image` (`data`, `mimeType`), `audio` (`data`, `mimeType`), `resource` (`text` or `blob` with `uri`), plus `isError` (true when the tool reported an error).

First text result: `${.content[0].text.text}`

---

## Plugin Runners

Plugin runners loaded from `PLUGINS_RUNNER_DIR` are used like built-in runners:

```yaml
run:
  runner:
    name: MyPluginRunner
    arguments:
      key: "value"
    options:
      channel: workflow
```

Fields are defined by each plugin; query RunnerService for its schema. Example plugin: `plugins/hello_runner/`.

---

`FUNCTION_SET_SELECTOR` is an internal runner used by LLM `autoSelectFunctionSet`; it is not normally called from workflows.
