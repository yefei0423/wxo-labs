**Author:** Markus van Kempen | mvk@ca.ibm.com
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
*No bug too small, no syntax too weird.*

---

# Code Architecture

This document explains how the dashboard code is structured at the file and function level.

For a semantics-oriented explanation of how traces, chats, spans, entities, and tools relate, see [TRACE_MODEL.md](/Users/markusvankempen/projects/wxo-projetcs/WxO-ToolBox/vsc/test_tools/wxo_observability_dashboard/docs/TRACE_MODEL.md).

## High-Level Flow

The dashboard works in four layers:

1. environment discovery and IAM token management on the backend
2. trace summary search against the observability API
3. client-side enrichment of weak trace summaries using full span exports
4. UI rendering for list, overview, error aggregation, and trace inspection

## File Map

### [server.js](/Users/markusvankempen/projects/wxo-projetcs/WxO-ToolBox/vsc/test_tools/wxo_observability_dashboard/server.js)

Backend responsibilities:

- parse environment configuration from the parent `.env`
- construct the environment list shown in the UI
- fetch and cache IAM tokens
- proxy trace search requests
- proxy trace span export requests
- host the static dashboard frontend

Important functions and sections:

- environment bootstrap: builds `envMap` and `localEnvMap`
- `getDefaultEnvironment()`: selects the first available system
- `resolveEnvironment()`: normalizes a requested environment to a valid one
- `getAuthToken()`: obtains and caches an IAM token
- `/api/traces`: summary search endpoint
- `/api/traces/:traceId/spans`: detailed span export endpoint

### [public/index.html](/Users/markusvankempen/projects/wxo-projetcs/WxO-ToolBox/vsc/test_tools/wxo_observability_dashboard/public/index.html)

Frontend structure:

- sidebar for system selection and future navigation
- top bar for filters and time range controls
- workspace summary strip for current scope and active filters
- overview strip for top-level trace metrics
- Error Explorer panel for grouped exception analysis
- trace list panel
- inspector panel
- export modal and systems modal

### [public/style.css](/Users/markusvankempen/projects/wxo-projetcs/WxO-ToolBox/vsc/test_tools/wxo_observability_dashboard/public/style.css)

Styling responsibilities:

- glass layout and overall dashboard shell
- trace list cards and badges
- overview cards and workspace summary cards
- Error Explorer tables and grouped exception cards
- inspector layout, hierarchy, timeline, and selection states
- responsive behavior

### [public/app.js](/Users/markusvankempen/projects/wxo-projetcs/WxO-ToolBox/vsc/test_tools/wxo_observability_dashboard/public/app.js)

This is the main application controller. It contains:

- OTLP decoding helpers
- summary metadata extraction
- span-based enrichment logic
- filter computation
- error aggregation
- trace list rendering
- inspector rendering
- UI event wiring

## Data Flow In Detail

### 1. Initial Load

Entry point:

- `DOMContentLoaded` handler at the top of [public/app.js](/Users/markusvankempen/projects/wxo-projetcs/WxO-ToolBox/vsc/test_tools/wxo_observability_dashboard/public/app.js)

Startup sequence:

1. cache DOM references
2. initialize the default time range
3. call `loadEnvironments()`
4. once systems are loaded, call `loadTraces()`

### 2. Trace Summary Load

Main function:

- `loadTraces()`

Responsibilities:

- build a start and end time range
- request trace summaries from `/api/traces`
- initialize `_uiMeta` for every summary using `buildTraceUiMeta()`
- clear error insight caches when the time window changes
- call `filterAndRender()`
- optionally start summary enrichment for cases where labels are weak

### 3. Summary Metadata Construction

Main function:

- `buildTraceUiMeta(trace)`

Responsibilities:

- build the first visible trace name
- choose an initial agent label and its source
- choose an initial entity label and its source
- build the normalized search blob used by filtering
- initialize coarse booleans such as `hasConversation`, `hasErrors`, and `isInfrastructure`

This function uses summary fields only. It does not inspect span payloads.

### 4. Span-Based Enrichment

Main functions:

- `collectSpanMeta(spanData)`
- `enrichMissingTraceMetadata(forceAnalyzeAll)`

Responsibilities:

- inspect full OTLP span exports for traces with weak labels
- derive better `agentName`, `entityName`, `spanName`, and signal booleans
- update `_uiMeta` in place
- re-render filters and the trace list when better metadata arrives

This is why the list can improve a few seconds after the initial search completes.

### 5. Filtering

Main functions:

- `getActiveFilterLabels()`
- `getFilteredTraces()`
- `filterAndRender()`

Filtering is fully client-side after summary load. The result set is controlled by:

- text query
- conversation-only toggle
- tools-only toggle
- errors-only toggle
- infra exclusion toggle

`filterAndRender()` is the central refresh path for:

- workspace summary
- overview strip
- Error Explorer
- trace list

## Key Function Map

### OTLP And Attribute Helpers

- `decodeOtlpValue(value)`
- `normalizeAttributePairs(rawAttrs)`
- `getAttrValueByKey(attrs, keyRegex)`
- `getSpanAttrMap(span)`
- `getSpanAttributes(span)`
- `getSpanEvents(span)`
- `getSpanLinks(span)`

These normalize OTLP values so downstream logic does not need to understand protobuf-style value wrappers.

### Conversation And Tool Extraction

- `collectMessages(value)`
- `collectToolCalls(value)`
- `extractConversationArtifacts(spansList)`

These functions inspect `traceloop.entity.input`, `traceloop.entity.output`, and GenAI attributes to recover:

- message flows
- tool invocations
- agent and thread correlation identifiers
- entity names

### Signal Detection

- `detectTraceSignals(spansList, artifacts)`
- `isErrorStatusCode(code)`

These decide whether a trace should be treated as:

- conversation-like
- tool-active
- errored
- interrupted
- infrastructure-only

### Visual Trace Structure

- `buildSpanTree(spansForExplorer)`
- `getSpanVisualType(row)`
- `getSpanToneColor(row)`
- `setupInspectorInteractions()`

These drive hierarchy and timeline rendering and keep the different inspector views synchronized.

### Error Aggregation

- `extractErrorInsights(trace, spanData)`
- `hydrateErrorInsights(traces)`
- `renderErrorExplorer(traces)`

This layer fetches span payloads only for currently visible error traces and builds:

- grouped exception messages
- top failing agents
- top failing spans

### Rendering

- `renderWorkspaceSummary()`
- `renderOverview(traces)`
- `renderTraceList(traces)`
- `renderInspector(summary, spanData)`

Each renderer is responsible for one visible section of the UI.

## Labeling Strategy

The dashboard intentionally separates two concepts in the trace list.

### Agent

Best effort label for the orchestrating agent.

Typical sources:

- `agent.name`
- `traceloop.agent.name`
- summary `agentNames`
- `assistant.name`

### Entity

Best effort label for the workflow, skill, or unit of execution within the trace.

Typical sources:

- `traceloop.workflow.name`
- `workflow.name`
- `skill.name`
- `traceloop.entity.name`

The trace list also shows `Agent from` and `Entity from` so users can understand how those labels were chosen.

## Extension Points

The easiest places to extend the dashboard are:

- `buildTraceUiMeta()` for summary-level label heuristics
- `collectSpanMeta()` for span-level label heuristics
- `detectTraceSignals()` for new boolean classifications
- `renderOverview()` for new top-level metrics
- `renderErrorExplorer()` for new grouped failure views
- `renderInspector()` for new trace drilldowns

## Safe Debugging Workflow

When a label or classification looks wrong:

1. inspect the trace in the UI
2. check the `Agent from` and `Entity from` hints
3. inspect `Trace Correlation` and `Conversation Flow`
4. check `Raw Trace JSON`
5. if needed, use [dump_keys.js](/Users/markusvankempen/projects/wxo-projetcs/WxO-ToolBox/vsc/test_tools/wxo_observability_dashboard/dump_keys.js) to inspect recent trace attributes

## Notes On `dump_keys.js`

[dump_keys.js](/Users/markusvankempen/projects/wxo-projetcs/WxO-ToolBox/vsc/test_tools/wxo_observability_dashboard/dump_keys.js) is a local debugging utility. It is not part of the production dashboard path.

Use it to:

- verify which keys appear on live traces
- inspect agent, workflow, and entity-related attribute patterns
- validate future extractor changes against real payloads
