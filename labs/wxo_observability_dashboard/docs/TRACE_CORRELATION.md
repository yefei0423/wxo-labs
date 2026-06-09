**Author:** Markus van Kempen | mvk@ca.ibm.com
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
*No bug too small, no syntax too weird.*

---

# Trace Correlation And Signal Extraction

This document explains how the dashboard turns raw OpenTelemetry trace payloads into useful debugging views.

## Why This Exists

Watsonx Orchestrate trace summaries are often not enough on their own.

Common problems in the summary response:

- agent name missing or incomplete
- trace name too generic
- no direct indication of tool activity
- no obvious conversation payload markers

Because of that, the dashboard uses full span payloads to recover semantics.

## Source Payload Shape

The dashboard expects OTLP-style data shaped roughly like this:

```json
{
  "traceData": {
    "resourceSpans": [
      {
        "scopeSpans": [
          {
            "spans": []
          }
        ]
      }
    ]
  }
}
```

Span extraction is built around traversing:

```text
traceData.resourceSpans[].scopeSpans[].spans[]
```

## Primary Correlation Fields

The dashboard looks for these identifiers first.

### Agent Identity

- `agent.name`
- `traceloop.agent.name`
- `agent.id`

Use:

- display an agent label in the trace list
- show correlation values in the inspector
- improve filtering and issue rollups

### User And Session Identity

- `user.id`
- `session.id`
- `langfuse.session.id`
- `thread.id`
- `traceloop.association.properties.thread_id`
- `global_transaction_id`

Use:

- show trace correlation data
- infer whether multiple spans belong to the same conversation thread

## Conversation Detection

The dashboard identifies likely conversation traces by inspecting both structured entity payloads and GenAI prompt/completion attributes.

### Structured Inputs And Outputs

Primary fields:

- `traceloop.entity.input`
- `traceloop.entity.output`
- fallback keys: `input`, `output`

These values are parsed as JSON when possible. The dashboard then recursively walks those objects to find:

- messages
- roles
- content
- tool call structures

### Message Normalization

The extraction logic looks for fields such as:

- `role`
- `type`
- `content`
- `name`
- nested `kwargs`

Messages are normalized into a simplified structure containing:

- role
- name
- content
- tool calls attached to the message

### Prompt And Completion Content

The dashboard also treats these as conversation evidence:

- `gen_ai.prompt.*.content`
- `gen_ai.completion.*.content`
- `gen_ai.system`

Use:

- render prompt/completion panels
- show hidden system prompt content when present
- infer likely LLM interaction even when no structured message payload exists

## Tool Detection

Tool invocations are extracted from several places.

### Structured Tool Calls

The extractor recursively searches for:

- `tool_calls`
- `kwargs.tool_calls`

It normalizes the call into:

- `id`
- `name`
- `args`

Accepted name/args sources include:

- `name`
- `function.name`
- `tool_name`
- `args`
- `arguments`
- `function.arguments`
- `kwargs`

### Tool Signals In Span Metadata

Even if structured tool payloads are weak, the UI can still classify spans as tool-like when:

- `traceloop.span.kind` suggests tool behavior
- attribute keys contain `tool` or `function`
- the span name contains `tool`

Use:

- set the `Tools` badge in the trace list
- populate the `Tools Invoked` inspector section
- apply tool coloring in hierarchy and timeline views

## Error Detection

The dashboard marks a trace as errored when any span satisfies one of these conditions:

- `span.status.code === 2`
- `exception.message` exists
- `error.message` exists
- `exception.stacktrace` exists

Use:

- set the `Error` badge in the trace list
- color error-related UI state
- raise the agent hotspot score in the overview strip

## Interrupt Detection

Interrupts are detected through:

- `traceloop.association.properties.is_interrupt == true`

Use:

- set the `Interrupt` badge in the trace list

## Trace Naming Strategy

The dashboard first tries to name a trace from the summary payload. If that fails, it extracts labels from span data.

Typical candidates include:

- `rootSpanName`
- `rootSpan.name`
- `spanName`
- `operationName`
- `transactionName`
- attribute keys resembling span or operation names
- `agentNames`
- `serviceNames`

Fallback result:

```text
Trace <first-8-chars-of-traceId>
```

## Agent Naming Strategy

The agent label is assembled from progressively weaker candidates:

- summary agent fields such as `agentName`, `agentNames`, `agent.name`
- nested summary agent structures
- resource and span attributes matching agent-like keys
- workflow or skill names when no explicit agent name exists

Fallback result:

```text
Unknown Agent
```

## Why Filtering Improves After Initial Load

The first trace list render uses only summary-derived metadata. A background enrichment step then fetches span payloads for traces with weak labels and recalculates:

- span name
- agent name
- conversation signal
- tool signal
- error signal
- interrupt signal

This means:

- the agent filter can become more accurate a moment after the list first appears
- `Conversation only` and `Only traces with tools` may improve after enrichment

## Execution Hierarchy Construction

The tree view is built purely from span relationships:

- each span is indexed by `spanId`
- children are attached using `parentSpanId`
- spans without a known parent become roots

This produces the `Execution Hierarchy` section.

## Span Type Classification

The dashboard uses a heuristic span type classifier for coloring and legend display.

Inputs:

- `traceloop.span.kind`
- `span.kind`
- span name
- presence of tool-related attribute keys
- whether the span has a parent

Resulting classes:

- root
- workflow
- task
- tool
- llm

This classification is visual only. It is useful for scanning but should not be treated as canonical telemetry semantics.

## Raw JSON Remains Authoritative

All higher-level views are heuristic transformations over the payload. When the dashboard interpretation looks wrong, the `Raw Trace JSON` section is the source of truth.

## Practical Reading Order For A Difficult Trace

When a trace is hard to understand, the fastest workflow is usually:

1. check badges and overview cards
2. open `Trace Correlation`
3. scan `Tools Invoked`
4. scan `Conversation Flow`
5. inspect `Execution Hierarchy`
6. use `Span Explorer` for suspicious spans
7. fall back to `Raw Trace JSON`
