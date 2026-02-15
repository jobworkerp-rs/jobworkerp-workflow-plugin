# Workflow Schema Quick Reference

Custom Serverless Workflow DSL v1.0.0 for jobworkerp-rs.

## Top-Level Structure

```yaml
document:        # REQUIRED - Workflow metadata
  dsl: "0.0.1"   # REQUIRED - DSL version (semver)
  namespace: default  # REQUIRED - Namespace (alphanumeric+hyphens)
  name: my-workflow   # REQUIRED - Workflow name (alphanumeric+hyphens)
  version: "0.0.1"   # REQUIRED - Workflow version (semver)
  title: "..."        # Optional - Human-readable title
  summary: "..."      # Optional - Markdown summary
  tags: {}            # Optional - Key/value tags
  metadata: {}        # Optional - Additional metadata
input:           # REQUIRED - Input configuration
  schema: ...    # Optional - Input validation schema
  from: ...      # Optional - Runtime expression to transform input
do:              # REQUIRED - Task list to execute
  - TaskName:
      ...
output:          # Optional - Output configuration
  schema: ...
  as: ...        # Runtime expression to transform output
checkpointing:   # Optional - Checkpoint configuration
  enabled: false
  storage: "memory"  # "memory" or "redis"
```

## Task Types

Each task item in `do` is a single-key object: `- TaskName: { taskDefinition }`.

### runTask - Execute external processes

```yaml
- MyTask:
    run:
      await: true          # Wait for completion (default: true)
      return: stdout       # stdout|stderr|code|all|none (default: stdout)
      runner: ...          # Option 1: runRunner
      worker: ...          # Option 2: runWorker
      function: ...        # Option 3: runFunction
      script: ...          # Option 4: runScript
    useStreaming: false     # Enable streaming execution
```

### forTask - Iterate over collection

```yaml
- MyLoop:
    for:
      each: item       # Variable name for current item (default: item)
      in: "${.array}"  # Runtime expression returning collection
      at: index        # Variable name for current index (default: index)
    while: "${...}"    # Optional continuation condition
    inParallel: false  # Execute iterations in parallel
    onError: break     # "continue" or "break" (default: break)
    do:
      - ...            # Tasks to execute per iteration
```

### forkTask - Concurrent execution

```yaml
- MyConcurrent:
    fork:
      branches:
        - Branch1:
            ...
        - Branch2:
            ...
      compete: false   # First completed wins (default: false)
```

### doTask - Sequential subtasks

```yaml
- MyGroup:
    do:
      - SubTask1: ...
      - SubTask2: ...
```

### switchTask - Conditional branching

```yaml
- MySwitch:
    switch:
      - case1:
          when: "${.value == 1}"   # Runtime expression condition
          then: continue           # Flow directive
      - case2:
          when: "${.value == 2}"
          then: exit
      - default:
          then: continue           # No 'when' = default case
```

### tryTask - Error handling

```yaml
- MyTry:
    try:
      - RiskyTask: ...
    catch:
      errors:
        with:
          type: "https://..."    # Filter by error type URI
          status: 500            # Filter by status code
      as: error                  # Variable name for caught error (default: error)
      when: "${...}"             # Condition to enable catching
      exceptWhen: "${...}"       # Condition to disable catching
      retry:                     # Retry policy
        delay: { seconds: 5 }
        backoff:
          exponential: {}        # constant|exponential|linear
        limit:
          attempt:
            count: 3
            duration: { minutes: 5 }
      do:
        - FallbackTask: ...      # Fallback tasks
```

### setTask - Set context variables

```yaml
- MySet:
    set:
      myVar: "${.someValue}"
      computed: "${.a + .b}"
```

Variables set here are accessible as `$myVar` in jq or `{{ myVar }}` in Liquid.

### raiseTask - Raise an error

```yaml
- MyError:
    raise:
      error:
        type: "https://example.com/errors/not-found"
        status: 404
        title: "Not Found"
        detail: "Resource not found"
```

### waitTask - Pause execution

```yaml
- MyWait:
    wait:
      seconds: 30
      # Or ISO 8601: "PT30S"
      # Or: { days: 1, hours: 2, minutes: 30, seconds: 0, milliseconds: 0 }
```

## taskBase - Common Properties (all task types)

```yaml
- AnyTask:
    if: "${...}"        # Condition to execute this task
    input:
      from: "${...}"    # Transform input data
      schema: ...       # Validate input
    output:
      as: "${...}"      # Transform output data (string or object)
      schema: ...       # Validate output
    export:
      as: "${...}"      # Export to workflow context variables
      schema: ...       # Validate exported data
    timeout:
      after: { seconds: 30 }  # Timeout duration
    then: continue      # Flow directive after completion
    checkpoint: false   # Save state for checkpoint/restart
    metadata: {}        # Additional metadata
```

## runTask Execution Methods

### 1. runRunner (most common)

```yaml
run:
  runner:
    name: COMMAND           # REQUIRED - Runner name
    using: "chat"           # Optional - Method selection for multi-method runners
    settings: {}            # Optional - Runner initialization settings (JSON)
    arguments: {}           # REQUIRED - Job arguments (JSON)
    options:                # Optional - Worker options
      channel: workflow
      useStatic: false
```

### 2. runWorker (pre-configured worker)

```yaml
run:
  worker:
    name: "MyWorker"        # REQUIRED - Worker name
    using: "run"            # Optional - Method selection
    arguments: {}           # REQUIRED - Job arguments
```

### 3. runFunction (runner or worker by name)

```yaml
run:
  function:
    runnerName: COMMAND     # Use runner by name
    # OR
    workerName: "MyWorker"  # Use worker by name
    using: "..."            # Optional method
    settings: {}            # Optional (runner only)
    options: {}             # Optional (runner only)
    arguments: {}           # REQUIRED
```

### 4. runScript (inline/external scripts)

```yaml
run:
  script:
    language: python        # REQUIRED - Script language
    code: |                 # Inline code (or use 'source' for external)
      print("Hello")
    arguments: {}           # Optional - Script arguments
    environment: {}         # Optional - Environment variables
```

## workerOptions

```yaml
options:
  channel: workflow           # Execution channel (concurrency control)
  queueType: NORMAL           # NORMAL | WITH_BACKUP | DB_ONLY
  responseType: DIRECT        # NO_RESULT | DIRECT
  storeSuccess: true          # Store successful results in DB
  storeFailure: true          # Store failure results in DB
  useStatic: false            # Use static worker (pooled initialization)
  broadcastResults: false     # Broadcast results to listeners
  retry:                      # Retry policy
    delay: { seconds: 5 }
    backoff:
      exponential: {}
    limit:
      attempt:
        count: 3
```

## Runtime Expressions

**IMPORTANT: No mixing of plain text and expressions.**
A value must be **entirely** a runtime expression (`${...}` or `$${...}`) or entirely plain text.
You **cannot** embed an expression inside a plain string like `"Bearer ${env.TOKEN}"`.

- **WRONG**: `"Bearer ${env.API_TOKEN}"` — plain text mixed with jq expression
- **CORRECT**: `"$${Bearer {{ env.API_TOKEN }}}"` — entire value is a Liquid template
- **CORRECT**: `"${\"Bearer \" + env.API_TOKEN}"` — entire value is a jq expression with string concatenation

When you need to combine static text with dynamic values, use **Liquid templates** (`$${...}`) which naturally support text interpolation, or use **jq string concatenation** within a single `${...}` expression.

### jq syntax: `${...}`

Access and transform JSON data using jq expressions.

```yaml
# Direct data access (current task context)
"${.key}"                    # Access field from current data
"${.nested.field}"           # Nested field access
"${.array[0]}"               # Array element

# Context variable access (set by setTask/export)
"${$myVariable}"             # Access context variable
"${$myVariable.field}"       # Access field of context variable

# Special context variables
"${$workflow.input.key}"     # Access workflow input
"${$workflow.id}"            # Workflow execution ID
"${$task.input}"             # Current task input
"${$task.raw_output}"        # Current task raw output
"${$task.output}"            # Current task output
"${$input.field}"            # Shorthand for previous/parent context (in output.as)
"${env.ENV_VAR}"             # Environment variable access

# jq operations
"${.items | length}"         # Array length
"${.a + .b}"                 # Arithmetic
"${.text | gsub(\"old\"; \"new\")}"  # String replacement
"${if .x then .y else .z end}"      # Conditional
"${.items | map(.name)}"    # Map operation
"${now | strftime(\"%Y-%m-%d\")}"   # Date formatting
"${.text | fromjson}"       # Parse JSON string
"${.data | tojson}"         # Serialize to JSON string
```

### Liquid syntax: `$${...}`

Use Liquid templates for string manipulation and control flow.

```yaml
# Variable access (context variables set by setTask/export)
"$${{{ myVariable }}}"
"$${{{ workflow.input.key }}}"

# Conditionals
"$${% if condition %}true{% else %}false{% endif %}"

# Loops
"$${% for item in items %}{{ item }}{% endfor %}"

# Filters
"$${{{ text | upcase }}}"
"$${{{ text | slice: 0, 100 }}}"
"$${{{ array | join: \", \" }}}"
"$${{{ text | url_encode }}}"
"$${{{ data | json_encode }}}"

# Date
"$${{{ 'now' | date: '%Y-%m-%d' }}}"
```

### Key Differences

| Feature | jq `${...}` | Liquid `$${...}` |
|---------|-------------|-----------------|
| JSON manipulation | Strong | Limited |
| String templating | Limited | Strong |
| Control flow | if/then/else/end | if/unless/for/case |
| Data access | `.key`, `$var` | `{{ var }}`, `{{ workflow.input.key }}` |
| Complex computation | Yes (arithmetic, map, select, reduce) | Basic filters only |
| Mixed text + data | Not suitable | Best choice |

## Flow Directives

| Directive | Description |
|-----------|-------------|
| `continue` | Continue to next task (default) |
| `exit` | Exit current task scope |
| `end` | End workflow execution |
| `wait` | Pause workflow (waiting state) |
| `"TaskName"` | Jump to named task (runtime expression) |

## Input/Output/Export Pattern

The data flow through tasks follows this pattern:

1. **input.from** transforms incoming data for the task
2. Task executes with transformed input
3. **output.as** transforms task result into desired shape
4. **export.as** copies selected data into workflow context variables

### Important: `$input` in output.as

Inside `output.as`, `$input` refers to the task's input data (before the task executed). This enables preserving values from previous steps:

```yaml
output:
  as:
    title: ${$input.title}        # Preserve title from input
    summary: ${.content.text}     # Use new output from this task
    link: ${$input.link}          # Preserve link from input
```
