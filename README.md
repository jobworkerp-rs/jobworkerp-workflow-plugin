# jobworkerp-workflow

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) plugin that helps create and edit workflow YAML files for the [jobworkerp-rs](https://github.com/jobworkerp-rs/jobworkerp-rs) workflow DSL, which is based on Open Workflow DSL v1.0.0 with jobworkerp extensions.

## Features

- Workflow YAML creation and editing with schema-aware guidance
- Built-in runner support: COMMAND, LLM, HTTP_REQUEST, GRPC, DOCKER, PYTHON_COMMAND, WORKFLOW, SANDBOX
- Process tasks: `run.shell`, `run.container`, `run.script`, `run.workflow` (with `await` / `return`)
- Service calls: `call: http` / `call: grpc` with `use.authentications` and `use.secrets`
- MCP server integration patterns
- Plugin runner usage guidance
- Flow control: forTask, forkTask, switchTask, tryTask, doTask, setTask, raiseTask, waitTask, named timeouts
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
| `references/workflow-schema.yaml` | Human-readable JSON Schema (Draft 2020-12) — mirrored from jobworkerp-rs `runner/schema/workflow.yaml` |
| `references/workflow-validation-schema.json` | Schema used by the jobworkerp-rs runtime validator — mirrored from `runner/schema/workflow_minimal_fix.json` |

## Development

Requires [`check-jsonschema`](https://github.com/python-jsonschema/check-jsonschema) and Python 3.

```bash
# Validate every complete workflow example in the skill docs and the test fixtures
# (tests/fixtures/valid must pass, tests/fixtures/invalid must be rejected).
# With a jobworkerp-rs checkout path, also verify the bundled schemas are up to date.
scripts/test.sh [<jobworkerp-rs-root>]

# Refresh the bundled schemas from a jobworkerp-rs checkout
scripts/sync-schema.sh <jobworkerp-rs-root>
```

YAML blocks in the docs that are intentionally partial are skipped automatically (no `document:` and not a `- Task:` list, or containing `...`); mark any other illustrative block with `<!-- validate:skip -->` on the line before the fence.

## Related Projects

- [jobworkerp-rs](https://github.com/jobworkerp-rs/jobworkerp-rs) - The scalable job worker system this plugin targets
- [Open Workflow Specification](https://github.com/open-workflow-specification/specification/blob/v1.0.0/dsl.md) - The base DSL specification (v1.0.0)

## License

MIT
