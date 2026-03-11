# Workflow Pattern Examples

Examples demonstrating common workflow patterns using built-in runners,
pre-configured workers (via runWorker/runFunction), and MCP servers.

## 1. Simple Command Execution

Basic runRunner with COMMAND runner:

```yaml
document:
  dsl: "0.0.1"
  namespace: default
  name: echo-test
  title: Simple Echo Test
  version: "0.1.0"
input: {}
do:
  - EchoWorker:
      run:
        runner:
          name: COMMAND
          arguments:
            command: echo
            args: ["Hello, World!"]
          options:
            channel: workflow
            useStatic: true
            storeSuccess: true
            storeFailure: true
  - DateWorker:
      run:
        runner:
          name: COMMAND
          arguments:
            command: date
            args: ["-R"]
          options:
            channel: workflow
```

## 2. Parallel For Loop with runFunction

forTask with inParallel and runFunction:

```yaml
do:
  - Iteration:
      for:
        each: idx
        in: ${.}           # Input is an array like [0, 1]
        at: index
      inParallel: true     # Execute iterations concurrently
      do:
        - SleepCommand:
            run:
              function:
                runnerName: COMMAND
                arguments:
                  command: sleep
                  args:
                    - ${$idx | tostring}
                options:
                  useStatic: false
                  storeSuccess: true
            then: continue
```

Key patterns:
- **runFunction**: Use `runnerName` to reference a built-in runner by name
- **inParallel**: Runs all iterations concurrently
- **jq in args**: `${$idx | tostring}` converts loop variable to string

## 3. LLM Chat with using: chat (Recommended Pattern)

Modern LLM unified runner with Liquid template for long text handling:

```yaml
- SummarizeArticle:
    if: '${.content // "" | length > 0}'
    run:
      runner:
        name: LLM
        using: chat
        settings:
          ollama:
            baseUrl: http://localhost:11434
            model: llama3
            pullModel: false
        arguments:
          messages:
            - role: system
              content:
                text: |
                  You are an expert AI assistant specialized in summarizing articles.
                  Write the summary in Japanese.
            - role: user
              content:
                text: |-
                  $${
                  {%- assign title = workflow.input.title -%}
                  {%- assign content = workflow.input.content -%}
                  Title: {{ title }}
                  {%- assign len = content | size -%}
                  {%- if len > 100000 -%}
                  {{ content | slice: 0, 50000 }}
                  ...(truncated)...
                  {%- assign tail_start = len | minus: 50000 -%}
                  {{ content | slice: tail_start, 50000 }}
                  {%- else -%}
                  {{ content }}
                  {%- endif -%}
                  }
          options:
            maxTokens: 131072
            temperature: 0.3
            topP: 0.9
            repeatPenalty: 1.1
            seed: 103
            extractReasoningContent: true
        options:
          channel: llm
          broadcastResults: true
          storeFailure: true
    output:
      as:
        title: ${$input.title}
        link: ${$input.url}
        summary: |
          ${.content.text}
        reasoning: |
          ${.reasoningContent}
```

Key patterns:
- **`if` guard**: `${.content // "" | length > 0}` - null-safe check with `//` (jq alternative operator)
- **Liquid for long text**: Truncation with `size`, `slice`, conditional rendering
- **`$input` in output.as**: Preserves input fields while adding new output fields
- **GenAI alternative**: Replace `ollama` with `genai: { model: "gpt-4o" }` (requires API key env var)

## 4. Advanced setTask with jq Computation

Complex variable computation using jq expressions:

```yaml
- ComputeTimeSlot:
    set:
      period: >-
        ${
          now | strftime("%H") | ltrimstr("0") | tonumber | . / 6 | floor
          | if . == 0 then "00-05"
            elif . == 1 then "06-11"
            elif . == 2 then "12-17"
            else "18-23"
            end
        }
      currentDate: >-
        ${now | strftime("%Y-%m-%d")}
      currentDatePath: >-
        ${now | strftime("%Y/%m/%d")}
```

Key patterns:
- **Complex jq in setTask**: Date arithmetic, chained transformations, conditional branching
- **`now`**: Built-in jq function returning current Unix timestamp

## 5. For Iteration with Static Array

Iterate over a fixed list of categories:

```yaml
- ProcessCategories:
    for:
      each: category
      in: '${["news", "tech", "science", "sports"]}'
      at: categoryIndex
    onError: continue     # Continue even if one category fails
    do:
      - SetCategoryLabel:
          set:
            categoryLabel: >-
              ${
                if $category == "news" then "News"
                elif $category == "tech" then "Technology"
                elif $category == "science" then "Science"
                else "Sports"
                end
              }
      - FetchCategoryData:
          run:
            runner:
              name: HTTP_REQUEST
              settings:
                baseUrl: "https://api.example.com"
              arguments:
                method: GET
                path: |-
                  $${/api/v1/articles?category={{ category }}}
          output:
            as:
              articles: ${.content | fromjson | .items}
              category: ${$category}
              label: ${$categoryLabel}
```

Key patterns:
- **Literal array in `for.in`**: `${["a", "b", "c"]}` to iterate over static values
- **`onError: continue`**: Resilient iteration that doesn't stop on failures
- **Conditional label mapping**: Using jq `if/elif/else/end` in setTask

## 6. If Guard with Complex Conditions

Null-safe empty string check with whitespace trimming:

```yaml
- ProcessIfNotEmpty:
    if: '${.prompt // "" | gsub("^\\s+|\\s+$"; "") | length > 0}'
```

Pattern breakdown:
- `.prompt // ""` - jq alternative: if null/false, use empty string
- `gsub("^\\s+|\\s+$"; "")` - Trim whitespace
- `length > 0` - Check non-empty

Another common pattern for non-null/non-empty checks:

```yaml
if: '${.content != null and .content != "" and (.content | ltrimstr("\n") | ltrimstr(" ")) != ""}'
```

## 7. Output Validation with jq Regex

Validate and normalize LLM output using jq regex matching:

```yaml
output:
  as:
    genre: >-
      ${
        (.content.text // "" | gsub("^\\s+|\\s+$"; "")) as $raw |
        if ($raw | test("^(news|tech|science|sports)$")) then $raw
        elif ($raw | test("tech")) then "tech"
        elif ($raw | test("science")) then "science"
        else "other"
        end
      }
```

Pattern: Robust output classification with fuzzy fallback matching.

## 8. $input Context Preservation Chain

Multi-step data threading using `$input`:

```yaml
# Step 1: LLM summarize
- SummarizeWorker:
    run: ...        # Produces {content: {text: "summary"}}
    output:
      as:
        title: ${$input.title}           # Preserve from input
        url: ${$input.url}              # Preserve from input
        summary: ${.content.text}        # New: LLM output

# Step 2: LLM classify (receives output from Step 1)
- ClassifyWorker:
    run: ...        # Produces {content: {text: "tech"}}
    output:
      as:
        title: ${$input.title}           # Passed through from Step 1
        url: ${$input.url}              # Passed through from Step 1
        genre: ${.content.text}          # New: classification result
        summary: ${$input.summary}       # Passed through from Step 1

# Step 3: Post result (receives output from Step 2)
- PostResultWorker:
    run: ...
    output:
      as:
        title: ${$input.title}           # Still available
        genre: ${$input.genre}           # Still available
        summary: ${$input.summary}       # Still available
```

Key pattern: Each step uses `$input.field` to preserve previous step data while adding new fields from task output.

## 9. MCP Server Integration

Using MCP servers configured in `mcp-settings.toml`:

```yaml
- FetchWebContent:
    run:
      runner:
        name: mcp-fetch          # MCP server name from mcp-settings.toml
        arguments:
          argJson: |
            $${{"url":"{{ url }}", "max_length": {{ max_length | default: 5000 }}}}
          toolName: fetch          # Which tool to use on this MCP server
        options:
          channel: workflow
    output:
      as:
        content: |
          ${.content[0].text.text}
        link: ${$input.url}
```

Key patterns:
- **`name`**: MCP server name as configured in `mcp-settings.toml`
- **`argJson`**: JSON string with Liquid template for argument construction
- **`toolName`**: Specify which tool to use (required for multi-tool servers)
- **Result access**: `${.content[0].text.text}` for first text content

MCP filesystem operations:

```yaml
- CreateDirectory:
    run:
      runner:
        name: filesystem           # MCP filesystem server
        arguments:
          toolName: "create_directory"
          argJson: |
            $${{"path": "{{ workflow.input.output_dir }}"}}
        options:
          channel: workflow

- WriteFile:
    run:
      runner:
        name: filesystem
        arguments:
          toolName: write_file
          argJson: |
            $${{"path": "{{ workflow.input.output_dir }}/result.md", "content": "{{ content | json_encode }}"}}
        options:
          channel: workflow
```

Note: MCP servers use input-driven paths (from `$workflow.input`) rather than hardcoded paths.

## 10. Liquid Template for Dynamic Strings

Complex string construction with date arithmetic and zero-padding:

```yaml
# Dynamic path with date computation
arguments:
  path: |-
    $${
    {%- assign year = 'now' | date: '%Y' -%}
    {%- assign month = 'now' | date: '%m' -%}
    {%- assign week = 'now' | date: '%U' | minus: 1 -%}
    {{ year }}/{{ month | prepend: '00' | slice: -2, 2 }}/w{{ week | prepend: '00' | slice: -2, 2 }}}
```

Key patterns:
- **`{%- -%}`**: Whitespace-stripping tags
- **Date filters**: `'now' | date: '%Y'` for current date
- **Arithmetic**: `| minus: 1`, `| plus: 0`
- **Zero-padding**: `| prepend: '00' | slice: -2, 2`

Conditional content based on time:

```yaml
arguments:
  category: |-
    $${
    {%- assign h = "now" | date: "%H" | plus: 0 -%}
    {%- assign slot = h | divided_by: 6 -%}
    {%- if slot == 0 -%}morning
    {%- elsif slot == 1 -%}midday
    {%- elsif slot == 2 -%}afternoon
    {%- else -%}evening
    {%- endif -%}}
```

## 11. Export + Context Variables

Set and accumulate variables across workflow steps:

```yaml
# Initialize and export context variables
- InitializeState:
    set:
      iteration_count: 0
      current_queries: []
      all_results: []
      score: 0.0
    export:
      as:
        iteration_count: ${.iteration_count}
        score: ${.score}
        all_results: ${.all_results}

# Later: update exported variables
- UpdateState:
    set:
      iteration_count: ${$iteration_count + 1}
    export:
      as:
        all_results: ${$all_results + $new_results}
```

Key pattern: `export.as` makes variables available as `$variableName` in subsequent tasks.

## 12. Slack Post with Thread Management

```yaml
- PostToSlack:
    if: '${.summary != null and .summary != ""}'
    run:
      runner:
        name: SLACK_POST_MESSAGE
        settings:
          botToken: ${env.SLACK_BOT_TOKEN}
        arguments:
          channel: ${$workflow.input.slack_channel}
          threadTs: ${.threadTs}
          attachments:
            - title: |-
                $${[{{ categoryLabel }}] {{ currentDate }}}
              text: |
                ${.summary}
              mrkdwnIn:
                - text
              color: "#36a64f"
    output:
      as:
        threadTs: ${.ts // $input.threadTs}
```

Key patterns:
- **`${env.SLACK_BOT_TOKEN}`**: Access environment variables for secrets
- **`$workflow.input.slack_channel`**: Channel from workflow input (not hardcoded)
- **Thread management**: `${.ts // $input.threadTs}` - first post creates thread, replies use it
- **Fallback with `//`**: Use new value or keep existing

## 13. Pre-configured Worker via runWorker

Use a worker that was created separately (via gRPC API, CLI, or WORKFLOW `using: create`):

```yaml
- CallMyWorker:
    run:
      worker:
        name: "my-data-processor"    # Pre-configured worker name
        using: "process"             # Optional: method for multi-method workers
        arguments:
          input: ${.data | tojson}
```

Key pattern: `runWorker` references workers by name without needing to specify runner settings or options (already configured).

## 14. switchTask - Conditional Branching

```yaml
- RouteByType:
    switch:
      - isTypeA:
          when: '${.type == "A"}'
          then: continue        # Proceed to next task
      - isTypeB:
          when: '${.type == "B"}'
          then: "SpecificTask"  # Jump to named task
      - default:
          then: exit            # Exit current scope (no 'when' = default case)
```

## 15. tryTask with Retry and Fallback

```yaml
- SafeApiCall:
    try:
      - CallExternalApi:
          run:
            runner:
              name: HTTP_REQUEST
              settings:
                baseUrl: "https://api.example.com"
              arguments:
                method: GET
                path: "/data"
    catch:
      errors:
        with:
          status: 500
      as: apiError             # Variable name for caught error
      retry:
        delay:
          seconds: 5
        backoff:
          exponential: {}      # constant | exponential | linear
        limit:
          attempt:
            count: 3
      do:
        - FallbackAction:
            set:
              result: "API unavailable, using cached data"
              errorDetail: ${$apiError.detail}
```

## 16. forkTask for Concurrent Execution

```yaml
- ParallelFetch:
    fork:
      branches:
        - FetchSourceA:
            run:
              runner:
                name: HTTP_REQUEST
                settings:
                  baseUrl: "https://api-a.example.com"
                arguments:
                  method: GET
                  path: "/data"
        - FetchSourceB:
            run:
              runner:
                name: HTTP_REQUEST
                settings:
                  baseUrl: "https://api-b.example.com"
                arguments:
                  method: GET
                  path: "/data"
      compete: false    # Wait for all branches (true = first completed wins)
```

## 17. DOCKER Runner - Container Execution

Run tasks inside Docker containers. Useful for sandboxed execution, CI-like tasks, or running tools
that require specific environments. Input parameters should come from workflow input, not hardcoded.

Basic container execution:

```yaml
- RunInContainer:
    run:
      runner:
        name: DOCKER
        settings:
          fromImage: "python:3.11-slim"   # Image to pull (settings = worker-level config)
        arguments:
          image: "python:3.11-slim"       # Image for this job (arguments = job-level)
          entrypoint: ["/bin/sh", "-c"]
          cmd: ["python -c 'print(\"Hello from Docker\")'"]
          workingDir: "/app"
          env: ["PYTHONPATH=/app"]
          timeoutSec: 300
          treatNonzeroAsError: true
        options:
          channel: workflow
          storeFailure: true
    export:
      as:
        container_output: "${.stdout // \"\"}"
```

Advanced pattern - dynamic volumes and image from workflow input (from a real code review workflow):

```yaml
document:
  dsl: "1.0.0"
  namespace: default
  name: docker-agent-workflow
  title: Run Agent in Docker Container
  version: "1.0.0"
input:
  schema:
    document:
      type: object
      properties:
        agent_image:
          type: string
          description: "Docker image for the agent"
        agent_cmd:
          type: string
          description: "Command to run inside the container"
        workspace_path:
          type: string
          description: "Host path to mount as /workspace"
        config_volumes:
          type: array
          items:
            type: string
          description: "Additional volume mounts (host:container format)"
      required: [agent_image, agent_cmd, workspace_path]
do:
  - initVars:
      set:
        agent_output: ""

  - runAgentWithErrorHandling:
      try:
        # Run agent in Docker with dynamic volumes
        - runAgent:
            run:
              runner:
                name: DOCKER
                arguments:
                  image: "${$workflow.input.agent_image}"
                  volumes: >-
                    ${
                      ($workflow.input.config_volumes // [])
                      + [$workflow.input.workspace_path + ":/workspace"]
                    }
                  workingDir: "/workspace"
                  entrypoint: ["/bin/sh", "-c"]
                  cmd: "${[$workflow.input.agent_cmd]}"
                  timeoutSec: 1800
                  treatNonzeroAsError: true
              options:
                channel: workflow
            timeout:
              after:
                minutes: 30
            export:
              as:
                agent_output: "${.stdout // \"\"}"

      catch:
        as: caught_error
        do:
          - setErrorState:
              set:
                error_message: "${$caught_error.message // \"Container execution failed\"}"

output:
  as:
    status: "${if $error_message then \"failed\" else \"success\" end}"
    output: "${$agent_output}"
    error: "${$error_message // \"\"}"
```

Key patterns:
- **Dynamic image**: `image: "${$workflow.input.agent_image}"` - image name from input, not hardcoded
- **Dynamic volumes**: Concatenate config volumes with workspace mount using jq array addition
- **`entrypoint` + `cmd`**: Use `["/bin/sh", "-c"]` entrypoint with command string in `cmd`
- **`timeoutSec`**: Container-level timeout (in DockerArgs); combine with task-level `timeout.after`
- **`treatNonzeroAsError: true`**: Treat non-zero exit codes as failures
- **tryTask wrapping**: Always wrap DOCKER tasks in tryTask for cleanup on failure
- **Result access**: `stdout`, `stderr`, `exitCode` available in output (same as COMMAND)
- **`settings.fromImage`** vs **`arguments.image`**: settings is for worker initialization (image pull), arguments is per-job (only effective when `useStatic: false`)

## 18. GRPC_UNARY Runner - gRPC API Calls

Call gRPC services from a workflow. Useful for microservice communication.

```yaml
- CallGrpcService:
    run:
      runner:
        name: GRPC_UNARY
        settings:
          host: "${$workflow.input.grpc_host}"
          port: 50051
          tls: false
          timeoutMs: 10000
          useReflection: true        # Use gRPC reflection for dynamic message construction
        arguments:
          method: "mypackage.MyService/GetData"
          request: |
            $${{"id": "{{ item_id }}", "include_details": true}}
          metadata:
            authorization: "$${Bearer {{ env.API_TOKEN }}}"
          timeout: 5000
          asJson: true               # Convert protobuf response to JSON
      options:
        channel: workflow
    output:
      as:
        data: ${.jsonBody | fromjson}
        status_code: ${.code}
```

Key patterns:
- **`useReflection: true`**: Enables dynamic message construction from JSON (otherwise `request` must be base64-encoded protobuf)
- **`asJson: true`**: Converts protobuf response to JSON in `jsonBody` field
- **`method` format**: `"package.Service/Method"` - full gRPC method path
- **Result fields**: `code` (gRPC status, 0=OK), `jsonBody` (if asJson), `body` (raw bytes), `metadata`, `message`

## 19. PYTHON_COMMAND Runner - Python Script Execution

Run Python scripts with automatic dependency management via `uv`:

```yaml
- AnalyzeData:
    run:
      runner:
        name: PYTHON_COMMAND
        settings:
          pythonVersion: "3.11"
          packages:
            list: ["pandas", "numpy"]
        arguments:
          scriptContent: |
            import pandas as pd
            import numpy as np
            import json, sys

            data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}
            values = data.get("values", [1, 2, 3, 4, 5])
            result = {
                "mean": float(np.mean(values)),
                "std": float(np.std(values)),
                "count": len(values)
            }
            print(json.dumps(result))
          dataBody: |
            ${.data | tojson}
          withStderr: true
      options:
        channel: workflow
    output:
      as:
        analysis: ${.output | fromjson}
```

With external script and requirements:

```yaml
- RunExternalScript:
    run:
      runner:
        name: PYTHON_COMMAND
        settings:
          pythonVersion: "3.11"
          requirementsUrl: "${$workflow.input.requirements_url}"
        arguments:
          scriptUrl: "${$workflow.input.script_url}"
          envVars:
            OUTPUT_FORMAT: "json"
            API_KEY: "${env.API_KEY}"
          dataBody: "${.input_data | tojson}"
          withStderr: true
      options:
        channel: workflow
        storeFailure: true
```

Key patterns:
- **`settings.packages.list`** or **`settings.requirementsUrl`**: Dependency specification (mutually exclusive)
- **`scriptContent`** vs **`scriptUrl`**: Inline script or external URL (mutually exclusive)
- **`dataBody`** vs **`dataUrl`**: Pass input data inline or via URL (mutually exclusive)
- **Result fields**: `output` (stdout), `outputStderr` (if `withStderr: true`), `exitCode`
- **Data passing**: Use `dataBody` to pass JSON; read via `sys.stdin` in script

## 20. WORKFLOW Runner - Nested Workflow Execution

Execute sub-workflows from a parent workflow using the unified `WORKFLOW` runner:

Inline sub-workflow execution:

```yaml
- RunSubWorkflow:
    run:
      runner:
        name: WORKFLOW
        using: run
        settings:
          workflowUrl: "${$workflow.input.sub_workflow_path}"
        arguments:
          input: "${.data | tojson}"
      options:
        channel: workflow
    output:
      as:
        sub_result: ${.output | fromjson}
```

Create a reusable workflow worker dynamically:

```yaml
- CreateWorkerFromWorkflow:
    run:
      runner:
        name: WORKFLOW
        using: create
        arguments:
          workflowUrl: "${$workflow.input.workflow_definition_url}"
          name: "dynamic-processor"
          workerOptions:
            channel: "workflow"
            responseType: "DIRECT"
            storeSuccess: true
            storeFailure: true
      options:
        channel: workflow
    export:
      as:
        created_worker_id: ${.workerId.value}
```

Then use the created worker via `runWorker`:

```yaml
- ExecuteCreatedWorker:
    run:
      worker:
        name: "dynamic-processor"
        arguments:
          input: "${.payload | tojson}"
```

Key patterns:
- **`using: run`** (default): Execute a workflow definition
- **`using: create`**: Register a workflow as a reusable worker
- **`settings.workflowUrl`** or **`settings.workflowData`**: Pre-configure workflow source (optional for `run`)
- **`arguments.input`**: Input data for the sub-workflow (JSON string or plain string)
- **Run result fields**: `id`, `output`, `position`, `status`, `errorMessage`
- **Create result fields**: `workerId.value` - ID of the created worker
- After `using: create`, the worker can be referenced by name via `runWorker`

## 21. Complete Multi-Step Workflow

A full example combining multiple patterns:

```yaml
document:
  dsl: "0.0.1"
  namespace: default
  name: fetch-and-summarize
  title: Fetch URL and Summarize
  version: "0.1.0"
input:
  schema:
    document:
      type: object
      properties:
        url:
          type: string
          description: URL to fetch and summarize
        model:
          type: string
          description: LLM model to use
          default: llama3
do:
  # Step 1: Fetch content
  - FetchContent:
      run:
        runner:
          name: HTTP_REQUEST
          settings:
            baseUrl: ${$workflow.input.url}
          arguments:
            method: GET
            path: "/"
      output:
        as:
          content: ${.content}
          url: ${$workflow.input.url}

  # Step 2: Guard - skip if empty
  - CheckContent:
      if: '${.content // "" | length > 100}'
      set:
        contentReady: true

  # Step 3: Summarize with LLM
  - Summarize:
      if: '${$contentReady == true}'
      run:
        runner:
          name: LLM
          using: chat
          settings:
            ollama:
              baseUrl: http://localhost:11434
              model: ${$workflow.input.model}
          arguments:
            messages:
              - role: system
                content:
                  text: "Summarize the following content in 5 bullet points."
              - role: user
                content:
                  text: ${.content}
            options:
              maxTokens: 4096
              temperature: 0.3
          options:
            channel: llm
      output:
        as:
          url: ${$input.url}
          summary: ${.content.text}

output:
  as:
    url: ${.url}
    summary: ${.summary}
```
