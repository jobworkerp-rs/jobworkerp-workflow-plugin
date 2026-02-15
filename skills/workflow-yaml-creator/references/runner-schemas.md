# Runner Settings & Arguments Reference

Each runner's `settings` and `arguments` in workflow YAML correspond to JSON representations of their protobuf definitions. Field names use camelCase in JSON.

**Note on runtime expressions in settings/arguments:** Each value must be entirely a runtime expression (`${...}` or `$${...}`) or entirely a plain literal. You cannot mix plain text with expressions in a single value (e.g., `"Bearer ${env.TOKEN}"` is **invalid**). Use Liquid `$${Bearer {{ env.TOKEN }}}` or jq `${"Bearer " + env.TOKEN}` instead. See [Schema Reference](schema-reference.md#runtime-expressions) for details.

## Querying Runner Schemas at Runtime

The schemas documented below are the built-in defaults. For the **latest** settings/arguments schema of any runner (including MCP servers and plugins), query the gRPC services:

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
  description: optional string          # Human-readable method description
  output_type: StreamingOutputType      # NON_STREAMING | STREAMING | BOTH
}
```

- **Single-method runners** (COMMAND, HTTP_REQUEST, etc.): `method_proto_map` has one entry with key `"run"`
- **Multi-method runners** (LLM, WORKFLOW): entries keyed by method name (e.g., `"chat"`, `"completion"`)
- **MCP servers**: entries keyed by tool name (e.g., `"fetch"`, `"fetch_html"`)
- **Plugins**: entries keyed by the plugin's registered method names

### FunctionService (proto: `jobworkerp.function.service.FunctionService`)

Use `FindByName` or `FindList` to get `FunctionSpecs` with **JSON Schema** (converted from protobuf):

```
FunctionSpecs {
  name: string                          # Function name
  settings_schema: string               # JSON Schema for settings
  methods: MethodSchemaMap {
    schemas: map<string, MethodSchema>  # Key: method name
  }
}

MethodSchema (function layer) {
  arguments_schema: string              # JSON Schema for arguments
  result_schema: optional string        # JSON Schema for result
  description: optional string          # Method description
  output_type: StreamingOutputType
}
```

### CLI Examples

```bash
# List all runners with their schemas
grpcurl -plaintext localhost:9000 jobworkerp.service.RunnerService/FindListBy

# Get specific runner by name
grpcurl -plaintext -d '{"name":"LLM"}' localhost:9000 jobworkerp.service.RunnerService/FindByName

# Get MCP server runner schema
grpcurl -plaintext -d '{"name":"mcp-fetch"}' localhost:9000 jobworkerp.service.RunnerService/FindByName

# Get function specs with JSON Schema (more convenient for workflow authoring)
grpcurl -plaintext -d '{"runner_name":"COMMAND"}' \
  localhost:9000 jobworkerp.function.service.FunctionService/FindByName
```

The `runner_settings_proto` and `MethodSchema.args_proto` fields contain protobuf message definitions as strings. The FunctionService provides the same information pre-converted to JSON Schema via `settings_schema` and `arguments_schema`.

---

## COMMAND Runner

No settings required.

### Arguments (CommandArgs)

```yaml
arguments:
  command: "echo"                    # REQUIRED - Shell command name
  args: ["Hello", "World"]           # Optional - List of arguments
  with_memory_monitoring: false      # Optional - Monitor memory usage
  treat_nonzero_as_error: false      # Optional - Treat non-zero exit as error
  success_exit_codes: [0]            # Optional - Exit codes treated as success
  working_dir: "/tmp"                # Optional - Working directory
```

### Result (CommandResult)

Output fields (accessible in output.as): `exit_code`, `stdout`, `stderr`, `execution_time_ms`, `started_at`, `max_memory_usage_kb`

With `run.return: stdout` (default), output is the stdout string directly.

---

## LLM Runner (Unified, Multi-Method)

The `LLM` runner supports two methods via `using`:
- `using: completion` - Text completion
- `using: chat` - Chat with messages (recommended)

### Settings (LLMRunnerSettings)

```yaml
settings:
  # Option 1: Ollama (local/self-hosted)
  ollama:
    baseUrl: "http://localhost:11434"  # Optional (default shown)
    model: "llama3"                    # REQUIRED - Model name
    systemPrompt: "You are..."         # Optional - System prompt
    pullModel: false                   # Optional - Pull model on init

  # Option 2: GenAI (cloud providers)
  # Requires env vars: OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, etc.
  genai:
    model: "gpt-4o"                    # REQUIRED - Model name (determines API)
    systemPrompt: "You are..."         # Optional - System prompt
    baseUrl: "https://..."             # Optional - Custom base URL
```

### Arguments for `using: chat` (LLMChatArgs) - Recommended

```yaml
using: chat
arguments:
  model: "override-model"     # Optional - Override settings model
  messages:                    # REQUIRED - Chat messages
    - role: system             # SYSTEM | USER | ASSISTANT | TOOL
      content:
        text: "System prompt"
    - role: user
      content:
        text: "User message"
        # OR image: { contentType: "image/png", source: { url: "...", base64: "..." } }
        # OR toolCalls: { calls: [{ callId: "...", fnName: "...", fnArguments: "..." }] }
  options:                     # Optional - Generation options
    maxTokens: 131072
    temperature: 0.3
    topP: 0.9
    repeatPenalty: 1.1
    repeatLastN: 5
    seed: 42
    extractReasoningContent: true  # Extract think/reasoning content
  functionOptions:             # Optional - Tool/function calling
    useFunctionCalling: true
    functionSetName: "my-set"  # Named function set
    useRunnersAsFunction: true # Use runners as tools
    useWorkersAsFunction: true # Use workers as tools
    isAutoCalling: true        # Auto-execute tool calls
  jsonSchema: '{"type":"object","properties":...}'  # Optional - Structured output
```

### Arguments for `using: completion` (LLMCompletionArgs)

```yaml
using: completion
arguments:
  model: "override-model"     # Optional
  systemPrompt: "..."         # Optional - Override system prompt
  prompt: "Generate text..."   # REQUIRED - Prompt text
  options:                     # Same as chat options
    maxTokens: 200000
    temperature: 0.4
    topP: 0.9
    # ... same fields as LLMOptions above
  functionOptions: ...         # Same as chat
  jsonSchema: "..."            # Optional
```

### Result

Chat result fields: `content.text`, `reasoningContent`, `done`, `usage`
Completion result fields: `content.text`, `reasoningContent`, `done`, `context`, `usage`

---

## HTTP_REQUEST Runner

### Settings (HttpRequestRunnerSettings)

```yaml
settings:
  baseUrl: "https://api.example.com"  # REQUIRED - Base URL
```

### Arguments (HttpRequestArgs)

```yaml
arguments:
  method: "POST"                      # REQUIRED - HTTP method
  path: "/api/v1/data"                # REQUIRED - Request path
  headers:                            # Optional - HTTP headers
    - key: "Content-Type"
      value: "application/json"
    - key: "Authorization"
      value: "Bearer token"
  body: '{"key": "value"}'            # Optional - Request body
  queries:                            # Optional - Query parameters
    - key: "page"
      value: "1"
```

### Result (HttpResponseResult)

Output fields: `statusCode`, `headers`, `content` (string body)

---

## GRPC_UNARY Runner

### Settings (GrpcUnaryRunnerSettings)

```yaml
settings:
  host: "grpc.example.com"           # REQUIRED - Host
  port: 50051                         # REQUIRED - Port
  tls: true                           # Optional - Use TLS
  timeoutMs: 5000                     # Optional - Timeout (ms)
  maxMessageSize: 4194304             # Optional - Max message size (bytes)
  authToken: "token"                  # Optional - Auth token
  useReflection: true                 # Optional - Use gRPC reflection
  tlsConfig:                          # Optional - TLS config
    caCertPath: "/path/ca.pem"
    clientCertPath: "/path/client.pem"
    clientKeyPath: "/path/client-key.pem"
    serverNameOverride: "hostname"
```

### Arguments (GrpcUnaryArgs)

```yaml
arguments:
  method: "service/MethodName"        # REQUIRED - Full method name
  request: '{"field": "value"}'       # REQUIRED - JSON request payload
  metadata:                           # Optional - gRPC metadata
    authorization: "Bearer token"
  timeout: 5000                       # Optional - Timeout (ms)
  asJson: true                        # Optional - Convert response to JSON
```

### Result (GrpcUnaryResult)

Output fields: `metadata`, `body`, `code`, `message`, `jsonBody`

---

## DOCKER Runner

### Settings (DockerRunnerSettings)

```yaml
settings:
  fromImage: "python:3.11-slim"       # Optional - Image to pull
  fromSrc: "..."                      # Optional - Import source URL
  repo: "myrepo"                      # Optional - Repository name
  tag: "latest"                       # Optional - Tag
  platform: "linux/amd64"             # Optional - Target platform
  env: ["VAR=value"]                  # Optional - Environment variables
  volumes: ["/host:/container"]       # Optional - Volume mounts
  workingDir: "/app"                  # Optional - Working directory
  entrypoint: ["python"]              # Optional - Entrypoint
  timeoutSec: 3600                    # Optional - Timeout (seconds)
```

### Arguments (DockerArgs)

```yaml
arguments:
  image: "python:3.11-slim"           # Optional - Image (use_static=false only)
  user: "appuser"                     # Optional - Run as user
  exposedPorts: ["8080/tcp"]          # Optional - Exposed ports
  env: ["KEY=value"]                  # Optional - Environment variables
  cmd: ["python", "script.py"]        # Optional - Command
  volumes: ["/data:/data"]            # Optional - Volumes
  workingDir: "/app"                  # Optional - Working directory
  entrypoint: ["python"]              # Optional - Entrypoint
  timeoutSec: 300                     # Optional - Timeout (seconds)
  treatNonzeroAsError: true           # Optional - Non-zero = error
  successExitCodes: [0]               # Optional - Success exit codes
```

### Result (DockerResult)

Output fields: `exitCode`, `stdout`, `stderr`, `containerId`, `executionTimeMs`, `startedAt`

---

## PYTHON_COMMAND Runner

### Settings (PythonCommandRunnerSettings)

```yaml
settings:
  pythonVersion: "3.11"               # REQUIRED - Python version
  uvPath: "/usr/bin/uv"               # Optional - uv executable path
  # One of:
  packages:
    list: ["pandas", "numpy"]         # Package list to install
  # OR
  requirementsUrl: "https://..."      # URL to requirements.txt
```

### Arguments (PythonCommandArgs)

```yaml
arguments:
  envVars:                            # Optional - Environment variables
    API_KEY: "value"
  # One of (REQUIRED):
  scriptContent: |                    # Inline script
    import sys
    print("Hello")
  # OR
  scriptUrl: "https://..."            # URL to script
  # Optional input data:
  dataBody: '{"key": "value"}'        # Inline data
  # OR
  dataUrl: "https://..."              # URL to data
  withStderr: true                    # Optional - Capture stderr
```

### Result (PythonCommandResult)

Output fields: `exitCode`, `output` (stdout), `outputStderr`

---

## SLACK_POST_MESSAGE Runner

### Settings (SlackRunnerSettings)

```yaml
settings:
  botToken: "xoxb-..."               # REQUIRED - Slack bot token
  botName: "MyBot"                    # Optional - Bot display name
```

Note: Use `${env.SLACK_BOT_TOKEN}` to reference environment variables.

### Arguments (SlackChatPostMessageArgs)

```yaml
arguments:
  channel: "C12345678"               # REQUIRED - Channel ID or name
  text: "Hello!"                      # Optional - Message text
  threadTs: "1234567890.123456"       # Optional - Thread to reply to
  attachments:                        # Optional - Rich attachments
    - title: "Title"
      text: "Attachment text"
      color: "#36a64f"
      mrkdwnIn: ["text"]
  blocks: []                          # Optional - Block Kit blocks (JSON strings)
  iconEmoji: ":robot:"               # Optional - Message icon emoji
  linkNames: true                     # Optional - Link @mentions
  mrkdwn: true                        # Optional - Parse markdown
  replyBroadcast: false               # Optional - Broadcast thread reply
  unfurlLinks: true                   # Optional - Show link previews
```

### Result (SlackChatPostMessageResult)

Output fields: `channel`, `ts` (message timestamp), `message`

---

## WORKFLOW Runner (Multi-Method)

### Settings (WorkflowRunnerSettings)

```yaml
settings:
  # One of (optional for 'run' method):
  workflowUrl: "./path/to/workflow.yaml"  # Path/URL to workflow file
  # OR
  workflowData: |                         # Inline workflow YAML/JSON
    document: ...
```

### Arguments for `using: run` (default) - WorkflowRunArgs

```yaml
using: run  # Optional (default)
arguments:
  # Optional override of workflow source:
  workflowUrl: "./another.yaml"
  # OR
  workflowData: "..."
  input: '{"key": "value"}'          # REQUIRED - Workflow input (JSON or string)
  workflowContext: '{"key": "val"}'  # Optional - Additional context
  executionId: "uuid-v7"             # Optional - Execution ID
  fromCheckpoint:                    # Optional - Resume from checkpoint
    position: "/do/2"
    data:
      workflow: { name: "...", input: "...", contextVariables: "..." }
      task: { input: "...", output: "...", contextVariables: "...", flowDirective: "..." }
```

### Arguments for `using: create` - CreateWorkflowArgs

```yaml
using: create
arguments:
  workflowUrl: "./workflow.yaml"     # One of (REQUIRED)
  # OR
  workflowData: "..."
  name: "new-workflow-worker"        # REQUIRED - Worker name
  workerOptions:                     # Optional
    retryPolicy: { type: "EXPONENTIAL", interval: 1000, maxRetry: 3 }
    channel: "workflow"
    queueType: "NORMAL"
    responseType: "DIRECT"
    storeSuccess: true
    storeFailure: true
    useStatic: false
    broadcastResults: false
```

### Result

Run result: `id`, `output`, `position`, `status`, `errorMessage`
Create result: `workerId.value`

---

## MCP Server Runners

MCP servers configured in `mcp-settings.toml` are registered as runners by their server name.

### Settings

No settings in workflow YAML - configured via `mcp-settings.toml`.

### Arguments

```yaml
run:
  runner:
    name: mcp-fetch              # MCP server name from config
    using: fetch_html            # Optional - Tool name (required for multi-tool servers)
    arguments:
      argJson: |                 # REQUIRED - Tool arguments as JSON string
        {"url": "https://example.com", "max_length": 5000}
      toolName: fetch            # Alternative way to specify tool name
    options:
      channel: workflow
```

### Result (McpServerResult)

Output is an array of content items: `content[].text.text`, `content[].image.data`, etc.

Access first text result: `${.content[0].text.text}`

---

## Plugin Runners

Custom plugin runners can be loaded from `PLUGINS_RUNNER_DIR` as `.so` files. They implement the `Runner` trait and are used just like built-in runners:

```yaml
run:
  runner:
    name: MyPluginRunner         # Plugin's registered name
    arguments:                   # Plugin-specific arguments
      key: "value"
    options:
      channel: workflow
```

Plugin settings/arguments are defined by each plugin's implementation. Refer to the plugin's own documentation for available fields. An example plugin is provided at `plugins/hello_runner/`.
