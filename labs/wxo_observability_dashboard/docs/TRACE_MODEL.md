**Author:** Markus van Kempen | mvk@ca.ibm.com
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
*No bug too small, no syntax too weird.*

---

# Trace Model Guide

This document explains how the dashboard interprets Watsonx Orchestrate trace data.

It focuses on the meaning and relationship of:

- traces
- spans
- chats and message flows
- entities
- agents
- tools and plugin-like activity
- user interaction markers
- error signals

The explanations below are based on the current extraction logic in [public/app.js](/Users/markusvankempen/projects/wxo-projetcs/WxO-ToolBox/vsc/test_tools/wxo_observability_dashboard/public/app.js), not on assumptions about how traces "should" look.

## Mental Model

At the highest level, the dashboard treats a trace as one execution run and the spans inside it as the steps that happened during that run.

A useful way to think about the structure is:

1. one trace = one observed run or request chain
2. spans inside that trace = workflow steps, agent steps, tool calls, LLM calls, and user-facing events
3. span attributes = the real payload that explains what each step did

In practice, the dashboard builds meaning in two passes:

1. summary pass from trace search results
2. enrichment pass from full span payloads

That distinction matters because summary data is often incomplete. A trace may initially show only a generic service/entity like `wxo-server`, and only later resolve to a more useful workflow or agent label once spans are loaded.

## Core Object Relationships

### Trace

A trace is the outer container.

It usually gives you:

- `traceId`
- top-level timestamps
- partial names such as `rootSpanName`, `operationName`, or service names
- weak agent/entity hints from summary attributes

The dashboard uses this data first to render the list quickly.

### Span

A span is one unit of work inside a trace.

Important span properties in this dashboard:

- `spanId`
- `parentSpanId`
- `name`
- `status.code`
- `status.message`
- `attributes`
- `events`
- `links`

Parent-child relationships are reconstructed from `parentSpanId` to build:

- execution hierarchy
- timeline view
- root/workflow/task/tool/LLM grouping

### Agent

The dashboard treats "agent" as the best available label for the orchestrating assistant or agent-like runtime identity.

Agent labels are derived from fields such as:

- `agent.name`
- `traceloop.agent.name`
- `assistant.name`
- `assistant.id`
- trace summary `agentNames`

The selected source is shown in the UI as `Agent from: ...`.

### Entity

The dashboard treats "entity" as the workflow or execution unit running inside the trace.

Entity labels are derived from fields such as:

- `traceloop.workflow.name`
- `workflow.name`
- `skill.name`
- `traceloop.entity.name`
- summary `serviceNames` as a fallback

This means the entity is not always the same thing as the agent.

Common pattern:

- agent = `hello_world_greeter`
- entity = `LangGraph`

Fallback pattern when only summary data is present:

- agent = `hello_world_greeter`
- entity = `wxo-server`

That fallback is useful, but not semantically rich. It typically means the trace still needs span enrichment.

## How Traces Become Conversations

The dashboard does not assume every trace is a chat.

Instead, it looks for conversation evidence inside spans.

Main function:

- `extractConversationArtifacts(spansList)`

Main evidence sources:

- `traceloop.entity.input`
- `traceloop.entity.output`
- `input`
- `output`
- `gen_ai.prompt.*.content`
- `gen_ai.completion.*.content`

These payloads are parsed and searched for:

- messages
- tool calls
- prompts
- completions
- structured input/output blobs

### Message Extraction

The dashboard recursively walks structured input and output objects looking for message-like objects.

Typical message indicators:

- `role`
- `type`
- `kwargs.type`
- `content`
- `kwargs.content`

Recovered message examples may look conceptually like:

```json
{
  "role": "human",
  "content": "can u open a box folder 0 by Markus"
}
```

or:

```json
{
  "role": "ai",
  "content": "...assistant response..."
}
```

### What The UI Calls Conversation Flow

The `Conversation Flow` section is assembled from spans that contain any of the following:

- recovered messages
- tool calls
- prompt text
- completion text
- structured input
- structured output

This means a span can appear in conversation flow even if it is not literally named `chat`.

## How User Interaction Appears In Traces

User interaction usually appears in one or more of these forms:

- a `human` role message in structured input/output
- a span named something like `human.task`
- a user identifier such as `user.id`
- conversation correlation identifiers such as `thread.id` or `session.id`

In the example you provided, the user input appears in a `human.task` span and also inside recovered chat/prompt payloads.

### Correlation Fields That Tie User Activity Together

The dashboard extracts these identifiers to connect spans to a user or thread:

- `agent.id`
- `user.id`
- `session.id`
- `langfuse.session.id`
- `thread.id`
- `traceloop.association.properties.thread_id`
- `global_transaction_id`

These appear in the `Trace Correlation` block of the detail view.

They are especially useful when:

- one user request generates many spans
- an interrupted or resumed flow spans multiple steps
- you need to connect UI activity to backend execution

## How Tools And Plugins Appear

The dashboard currently treats tools and plugin-like actions as related concepts.

There is not a single universal "plugin" field in the current parser. Instead, plugin behavior typically shows up in one of two ways.

### 1. Structured Tool Calls

The dashboard extracts tool calls recursively from structured input/output using fields like:

- `tool_calls`
- `kwargs.tool_calls`
- nested function call objects

Recovered tool calls are normalized to:

- tool id
- tool name
- tool arguments

These appear in:

- `Tools Invoked`
- `Conversation Flow`
- trace-level `hasTools`

### 2. Tool-Like Execution Spans

Even if a tool call is not explicitly present as `tool_calls`, the dashboard may still classify a span as tool-like based on:

- span kind naming
- span name containing `tool`
- attributes containing `tool` or `function`

This classification is used mainly for hierarchy and coloring.

### Plugin-Like HTTP Activity

Some plugin or integration behavior may appear only as HTTP client spans rather than explicit tool calls.

Those spans often look like infrastructure if they only contain fields such as:

- `http.method`
- `http.url`
- `span.kind=client`

If they do not also carry agent/conversation/tool signals, the dashboard may classify them as infrastructure-only traffic.

That means:

- not every external call is shown as a tool
- some plugin activity is visible only in the raw spans or timeline

## How Error Detection Works

The dashboard detects errors from span payloads, not only from trace summaries.

Main signals:

- `status.code = 2`
- `status.code = "STATUS_CODE_ERROR"`
- `status.code = "ERROR"`
- `exception.message`
- `error.message`
- `exception.stacktrace`
- `status.message`

### Why An Error Can Be Visible In Trace Details But Missing In The List At First

This has been a real behavior in the dashboard.

Reason:

1. trace summaries can miss error markers
2. the full span payload may still contain an error span such as `human.task ERROR`
3. only after span hydration does the dashboard promote that trace into the error state

This is why the current Error Explorer now analyzes visible traces and not just traces that were pre-flagged as errors.

## What Error Explorer Actually Groups

Error Explorer uses `extractErrorInsights(trace, spanData)`.

Each detected error is normalized to roughly:

- `traceId`
- `spanId`
- `spanName`
- `agentName`
- `message`
- `detail`

Grouping is primarily by normalized error message.

This is why two traces with the same top-level failure text are grouped together even if they happened in different runs.

## Relationship Between Timeline, Span Tree, And Conversation Flow

These three views use the same trace, but show different slices of meaning.

### Timeline

Best for:

- duration
- ordering
- overlap
- quickly spotting short failing spans

### Execution Hierarchy

Best for:

- parent-child structure
- identifying which workflow/task owns another span
- seeing where a failure occurred in the call tree

### Conversation Flow

Best for:

- understanding user input and assistant output
- seeing which span carried prompt or completion text
- seeing where tools were invoked in the interaction

These are complementary views of the same execution.

## Recommended Reading Pattern For A Trace

When a trace looks confusing, this order works well:

1. start with the trace list label pair: `Agent` and `Entity`
2. open the trace and check `Exceptions Detected`
3. look at `Trace Correlation` to understand user/session/thread context
4. inspect `Execution Timeline` for the short failing span or long-running bottleneck
5. inspect `Execution Hierarchy` to see where the failing span sits in the tree
6. inspect `Conversation Flow` and `True LLM Generative Texts` to understand the user-visible interaction
7. inspect raw attributes or raw JSON only when the higher-level views are insufficient

## Common Patterns You Will See

### Agent Task + Human Task

Typical sequence:

- root request span
- workflow span such as `LangGraph.workflow`
- agent span such as `agent.task`
- human/user-facing span such as `human.task`

If `human.task` fails, the actual user-facing issue may be located there even when the parent `agent.task` is still marked OK.

### LLM Prompt/Completion Inside A Deeper Span

The actual LLM content may appear only in a client or LLM span such as:

- `WatsonxChatModel.chat`

This means:

- the agent span explains orchestration
- the chat/client span explains model input/output

### Generic Entity Values

If you see values like `wxo-server`, that usually means the list is still relying on summary-level fallbacks.

Look for better values in the span-enriched views:

- `traceloop.workflow.name`
- `skill.name`
- `traceloop.entity.name`

## Limits Of The Current Model

The current dashboard is best-effort, not schema-perfect.

Known constraints:

- summary payloads are sometimes too weak to classify traces correctly without span hydration
- plugin activity may look like generic HTTP spans rather than explicit tool calls
- message extraction is recursive and heuristic, so unusual payload shapes may be missed
- some traces expose agent/entity information only on deeper spans

## Where To Extend The Model In Code

If you need to change how the dashboard interprets traces, these are the main functions to modify:

- `buildTraceUiMeta()` for summary-level labels
- `extractConversationArtifacts()` for chats, user interaction, tools, and correlation ids
- `detectTraceSignals()` for conversation/tool/error classification
- `collectSpanMeta()` for enriched `agent` and `entity` labels
- `extractErrorInsights()` for what Error Explorer groups and shows
- `renderInspector()` for how trace detail explains failures
