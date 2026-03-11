# jobworkerp-workflow

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) plugin that helps create and edit workflow YAML files compliant with [jobworkerp-rs](https://github.com/jobworkerp-rs/jobworkerp-rs) Custom Serverless Workflow DSL v1.0.0.

## Features

- Workflow YAML creation and editing with schema-aware guidance
- Built-in runner support: COMMAND, LLM, HTTP_REQUEST, GRPC_UNARY, DOCKER, PYTHON_COMMAND, WORKFLOW, SLACK_POST_MESSAGE
- MCP server integration patterns
- Plugin runner usage guidance
- Flow control: forTask, forkTask, switchTask, tryTask, doTask, setTask, raiseTask, waitTask
- Runtime expression syntax: jq (`${...}`) and Liquid (`$${...}`)
- Data flow patterns: input/output/export, `$input` context preservation

## Installation

```bash
# Step 1: Add the marketplace
/plugin marketplace add jobworkerp-rs/jobworkerp-workflow-plugin

# Step 2: Install the plugin
/plugin install jobworkerp-workflow@jobworkerp-workflow-plugin
```

Or add to your project's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "jobworkerp-workflow-plugin": {
      "source": {
        "source": "github",
        "repo": "jobworkerp-rs/jobworkerp-workflow-plugin"
      }
    }
  },
  "enabledPlugins": {
    "jobworkerp-workflow@jobworkerp-workflow-plugin": true
  }
}
```

## Usage

Once installed, the skill is automatically triggered when you ask Claude Code to:

- Create a new workflow YAML
- Edit or modify an existing workflow
- Understand workflow structure or runner configuration

Example prompts:

- "Create a workflow that fetches a URL and summarizes the content with LLM"
- "Add error handling with retry to this workflow"
- "Create a parallel for loop that processes items concurrently"

## Included References

| File | Description |
|------|-------------|
| `SKILL.md` | Main skill definition with workflow basics and runner quick reference |
| `references/schema-reference.md` | Full schema structure, all task types, runtime expression syntax |
| `references/runner-schemas.md` | Settings/arguments for all built-in runners |
| `references/examples.md` | Pattern examples: LLM chat, for loops, MCP integration, etc. |

## Related Projects

- [jobworkerp-rs](https://github.com/jobworkerp-rs/jobworkerp-rs) - The scalable job worker system this plugin targets
- [Serverless Workflow](https://serverlessworkflow.io/) - The base specification (v1.0.0) with jobworkerp-rs extensions

## License

MIT
