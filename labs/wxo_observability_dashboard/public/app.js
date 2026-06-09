/**
 * Browser-side controller for the WxO Observability Dashboard.
 *
 * The script is responsible for:
 * - loading environment choices from the backend
 * - fetching trace summaries for the selected time range
 * - enriching weak summaries with full span payloads when needed
 * - deriving conversation, tool, and error signals from OTLP data
 * - rendering the overview, trace list, error explorer, and inspector modal
 */
document.addEventListener('DOMContentLoaded', () => {
    
    const traceList = document.getElementById('trace-list');
    const traceCount = document.getElementById('trace-count');
    const inspectorPanel = document.getElementById('inspector-panel');
    const inspectorModal = document.getElementById('inspector-modal');
    const inspectorModalBody = document.getElementById('inspector-modal-body');
    const inspectorModalTitle = document.getElementById('inspector-modal-title');
    const inspectorModalClose = document.getElementById('inspector-modal-close');
    const refreshBtn = document.getElementById('refresh-btn');
    const exportBtn = document.getElementById('export-btn');
    const timeStartInput = document.getElementById('start-time');
    const timeEndInput = document.getElementById('end-time');
    const agentFilter = document.getElementById('agent-filter');
    const conversationOnlyToggle = document.getElementById('conversation-only-toggle');
    const toolsOnlyToggle = document.getElementById('tools-only-toggle');
    const errorsOnlyToggle = document.getElementById('errors-only-toggle');
    const excludeInfraToggle = document.getElementById('exclude-infra-toggle');
    const envSelector = document.getElementById('env-selector');
    const manageSystemsBtn = document.getElementById('manage-systems-btn');
    const workspaceSummary = document.getElementById('workspace-summary');
    const overviewStrip = document.getElementById('overview-strip');
    const errorExplorerContent = document.getElementById('error-explorer-content');
    const errorExplorerCount = document.getElementById('error-explorer-count');
    const systemsModal = document.getElementById('systems-modal');
    const closeSystemsBtn = document.getElementById('close-systems-btn');
    const systemsList = document.getElementById('systems-list');
    const systemsStatusText = document.getElementById('systems-status-text');
    const systemForm = document.getElementById('system-form');
    const newSystemName = document.getElementById('new-system-name');
    const newSystemUrl = document.getElementById('new-system-url');
    const newSystemKey = document.getElementById('new-system-key');
    const editSystemForm = document.getElementById('edit-system-form');
    const editSystemOriginalName = document.getElementById('edit-system-original-name');
    const editSystemName = document.getElementById('edit-system-name');
    const editSystemUrl = document.getElementById('edit-system-url');
    const editSystemKey = document.getElementById('edit-system-key');
    const cancelEditSystemBtn = document.getElementById('cancel-edit-system-btn');

    let allTraces = [];
    let environmentDetails = [];
    const traceMetadataInflight = new Set();
    const errorInsightsCache = new Map();
    const errorInsightsInflight = new Set();
    const runningFromFileProtocol = window.location.protocol === 'file:';
    let activeTraceLoadController = null;
    let activeTraceLoadKey = '';
    let traceLoadPromise = null;
    let traceSearchCooldownUntil = 0;
    const errorExplorerFocus = {
        agentName: '',
        spanName: '',
        message: ''
    };

    /**
     * Converts a datetime-local input value into a normalized ISO timestamp.
     */
    function toIsoFromLocalInput(value) {
        if (!value) return null;
        const dt = new Date(value);
        if (Number.isNaN(dt.getTime())) return null;
        return dt.toISOString();
    }

    /**
     * Escapes user-visible text before inserting it into HTML templates.
     */
    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /**
     * Returns whether any error-explorer-driven filter is currently active.
     */
    function hasErrorExplorerFocus() {
        return Boolean(errorExplorerFocus.agentName || errorExplorerFocus.spanName || errorExplorerFocus.message);
    }

    /**
     * Applies compact filters driven by the error explorer summaries.
     */
    function setErrorExplorerFocus(nextFocus = {}) {
        errorExplorerFocus.agentName = nextFocus.agentName || '';
        errorExplorerFocus.spanName = nextFocus.spanName || '';
        errorExplorerFocus.message = nextFocus.message || '';
        if (hasErrorExplorerFocus()) {
            errorsOnlyToggle.checked = true;
        }
        filterAndRender();
        if (hasErrorExplorerFocus()) {
            hydrateErrorInsights(allTraces);
        }
    }

    /**
     * Resets error-explorer-specific filters while keeping the main filters.
     */
    function clearErrorExplorerFocus() {
        setErrorExplorerFocus({});
    }

    /**
     * Checks whether a trace matches the active error-explorer focus.
     */
    function matchesErrorExplorerFocus(trace) {
        if (!hasErrorExplorerFocus()) return true;

        if (errorExplorerFocus.agentName && getAgentName(trace) !== errorExplorerFocus.agentName) {
            return false;
        }

        if (!errorExplorerFocus.spanName && !errorExplorerFocus.message) {
            return true;
        }

        const cached = trace?.traceId ? errorInsightsCache.get(trace.traceId) : null;
        if (!cached?.errors?.length) return false;

        return cached.errors.some((error) => {
            const matchesSpan = !errorExplorerFocus.spanName || error.spanName === errorExplorerFocus.spanName;
            const matchesMessage = !errorExplorerFocus.message || error.message === errorExplorerFocus.message;
            return matchesSpan && matchesMessage;
        });
    }

    /**
     * Highlights a trace in the visible list, scrolls it into view, and can
     * optionally open the full inspector for the matching trace.
     */
    function focusTraceById(traceId, { openInspector = true } = {}) {
        if (!traceId) return false;

        const trace = allTraces.find((item) => item.traceId === traceId);
        if (!trace) return false;

        const row = traceList.querySelector(`.trace-item[data-trace-id="${traceId}"]`);
        document.querySelectorAll('.trace-item').forEach((item) => item.classList.remove('active-trace'));

        if (row) {
            row.classList.add('active-trace');
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }

        if (openInspector) inspectTrace(trace);
        return true;
    }

    /**
     * Renders a visible error state in the trace list together with enough
     * request metadata to debug backend or networking problems from the UI.
     */
    function renderTraceLoadError(message, debug = {}) {
        const envName = envSelector.value || 'none';
        const cooldownSeconds = debug.retryAfterMs ? Math.max(1, Math.ceil(debug.retryAfterMs / 1000)) : 0;
        const debugRows = [
            ['Environment', envName],
            ['Start', timeStartInput.value || 'n/a'],
            ['End', timeEndInput.value || 'n/a'],
            ['URL', debug.url || 'n/a'],
            ['Request ID', debug.requestId || 'n/a'],
            ['Status', debug.status || 'n/a'],
            ['Retry After', cooldownSeconds ? `${cooldownSeconds}s` : (debug.retryAfter || 'n/a')]
        ];

        const retryLabel = cooldownSeconds ? `Retry in ${cooldownSeconds}s` : 'Retry';
        const retryDisabledAttr = cooldownSeconds ? 'disabled' : '';

        traceList.innerHTML = `
            <div class="debug-error-card">
                <div class="debug-error-title">⚠️ ${escapeHtml(message)}</div>
                <div class="debug-error-actions">
                    <button id="retry-load-btn" class="btn btn-outline btn-sm" ${retryDisabledAttr}>${retryLabel}</button>
                    <button id="debug-check-btn" class="btn btn-outline btn-sm">Run Debug Check</button>
                </div>
                <details class="debug-error-details" open>
                    <summary>Debug details</summary>
                    <table class="debug-error-table">
                        <tbody>
                            ${debugRows.map(([k, v]) => `<tr><td>${escapeHtml(k)}</td><td>${escapeHtml(String(v))}</td></tr>`).join('')}
                        </tbody>
                    </table>
                    ${debug.details ? `<div class="debug-error-body">${escapeHtml(debug.details)}</div>` : ''}
                </details>
                <div id="debug-check-output" class="debug-check-output"></div>
            </div>
        `;

        const retryBtn = document.getElementById('retry-load-btn');
        if (retryBtn && !cooldownSeconds) retryBtn.addEventListener('click', () => loadTraces());

        const debugBtn = document.getElementById('debug-check-btn');
        if (debugBtn) {
            debugBtn.addEventListener('click', async () => {
                const output = document.getElementById('debug-check-output');
                if (!output) return;
                output.textContent = 'Checking /api/debug/status...';
                try {
                    const env = encodeURIComponent(envSelector.value || '');
                    const r = await fetch(`/api/debug/status?env=${env}`);
                    const txt = await r.text();
                    output.textContent = txt;
                } catch (err) {
                    output.textContent = `Debug check failed: ${err.message}`;
                }
            });
        }
    }

    /**
     * Explains that the dashboard must be served over HTTP instead of opened
     * directly from disk so the browser can reach the Express API.
     */
    function renderLocalFileModeWarning() {
        envSelector.innerHTML = '<option value="">Server required</option>';
        if (workspaceSummary) {
            workspaceSummary.innerHTML = `
                <div class="status-bar">
                    <span class="status-bar-system">Local file mode detected</span>
                    <span class="status-bar-sep">·</span>
                    <span>Open the dashboard through the Node server at http://localhost:3000</span>
                </div>
            `;
        }

        traceList.innerHTML = `
            <div class="debug-error-card">
                <div class="debug-error-title">Open this dashboard through the local server</div>
                <div class="debug-error-body">You opened <strong>index.html</strong> with the <strong>file://</strong> protocol, so browser requests to <strong>/api/environments/details</strong> are treated as cross-origin and blocked before they reach the backend.</div>
                <details class="debug-error-details" open>
                    <summary>How to run it</summary>
                    <table class="debug-error-table">
                        <tbody>
                            <tr><td>Start server</td><td>node server.js</td></tr>
                            <tr><td>Open URL</td><td>http://localhost:3000</td></tr>
                            <tr><td>Do not use</td><td>file://${window.location.pathname}</td></tr>
                        </tbody>
                    </table>
                </details>
            </div>
        `;

        if (errorExplorerContent) {
            errorExplorerContent.innerHTML = `
                <div class="empty-state" style="height:auto; min-height: 180px;">
                    <div class="empty-icon">⚠️</div>
                    <p>The error explorer needs the backend API. Open the dashboard from http://localhost:3000 after starting server.js.</p>
                </div>
            `;
        }
    }

    /**
     * Converts OTLP protobuf-style values into plain JavaScript primitives.
     */
    function decodeOtlpValue(value) {
        if (!value || typeof value !== 'object') return value;
        if (value.stringValue !== undefined) return value.stringValue;
        if (value.intValue !== undefined) return Number(value.intValue);
        if (value.doubleValue !== undefined) return Number(value.doubleValue);
        if (value.boolValue !== undefined) return Boolean(value.boolValue);
        if (value.bytesValue !== undefined) return String(value.bytesValue);

        if (value.arrayValue?.values) {
            return value.arrayValue.values.map((v) => decodeOtlpValue(v));
        }

        if (value.kvlistValue?.values) {
            return value.kvlistValue.values.reduce((acc, pair) => {
                acc[pair.key] = decodeOtlpValue(pair.value);
                return acc;
            }, {});
        }

        return null;
    }

    /**
     * Normalizes attributes into a consistent [{ key, value }] shape so the rest
     * of the code can work with summary payloads and full OTLP spans uniformly.
     */
    function normalizeAttributePairs(rawAttrs) {
        if (!rawAttrs) return [];

        if (Array.isArray(rawAttrs)) {
            return rawAttrs
                .map((attr) => ({ key: String(attr?.key || ''), value: attr?.value }))
                .filter((pair) => pair.key.length > 0);
        }

        if (typeof rawAttrs === 'object') {
            return Object.entries(rawAttrs).map(([key, value]) => ({ key: String(key), value }));
        }

        return [];
    }

    /**
     * Finds the first attribute value whose key matches the provided regex.
     */
    function getAttrValueByKey(attrs, keyRegex) {
        const normalized = normalizeAttributePairs(attrs);
        for (const attr of normalized) {
            const key = String(attr?.key || '');
            if (!keyRegex.test(key)) continue;
            const decoded = decodeOtlpValue(attr?.value);
            if (decoded === undefined || decoded === null) continue;
            const text = typeof decoded === 'string' ? decoded : JSON.stringify(decoded);
            if (text && text.trim()) return text.trim();
        }
        return null;
    }

    /**
     * Returns the first non-empty string found in a list of candidate values.
     */
    function getFirstString(candidates) {
        for (const raw of candidates) {
            if (Array.isArray(raw)) {
                for (const item of raw) {
                    if (typeof item !== 'string') continue;
                    const arrVal = item.trim();
                    if (arrVal) return arrVal;
                }
                continue;
            }
            if (typeof raw !== 'string') continue;
            const val = raw.trim();
            if (val) return val;
        }
        return null;
    }

    /**
     * Like getFirstString, but also preserves which source produced the value.
     */
    function pickFirstLabeledValue(candidates) {
        for (const candidate of candidates) {
            if (!candidate) continue;
            const source = candidate.source || '';
            const raw = candidate.value;

            if (Array.isArray(raw)) {
                for (const item of raw) {
                    if (typeof item !== 'string') continue;
                    const value = item.trim();
                    if (value) return { value, source };
                }
                continue;
            }

            if (typeof raw !== 'string') continue;
            const value = raw.trim();
            if (value) return { value, source };
        }

        return null;
    }

    /**
     * Builds a normalized free-text blob used by client-side filtering.
     */
    function buildSearchBlob(trace, spanName, agentName, entityName = '') {
        return [
            spanName,
            agentName,
            entityName,
            trace.traceId || '',
            trace.operationName || '',
            trace.transactionName || '',
            ...(Array.isArray(trace.serviceNames) ? trace.serviceNames : []),
            ...(Array.isArray(trace.agentNames) ? trace.agentNames : [])
        ].join(' ').toLowerCase().replace(/[_.-]+/g, ' ');
    }

    /**
     * Normalizes filter text so simple wildcards and punctuation differences do
     * not prevent a match.
     */
    function normalizeFilterQuery(query) {
        return String(query || '')
            .toLowerCase()
            .replace(/[*/]+/g, ' ')
            .replace(/[_.-]+/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
    }

    /**
     * Builds the first-pass trace metadata shown in the list before full-span
     * enrichment runs. This intentionally relies on summary payloads only.
     */
    function buildTraceUiMeta(trace) {
        const attrs = [
            ...normalizeAttributePairs(trace.attributes),
            ...normalizeAttributePairs(trace.rootSpanAttributes),
            ...normalizeAttributePairs(trace.resourceAttributes),
            ...normalizeAttributePairs(trace.rootSpan?.attributes)
        ];

        const spanFromAttrs = getAttrValueByKey(attrs, /(root.*span.*name|span.*name|operation.*name|transaction.*name)$/i);
        const agentFromAttrs = getAttrValueByKey(attrs, /(^agent(\.|_|$))|(^agent\.name$)|(agent.*name)|(orchestrate.*agent)|(wxo.*agent)|(assistant.*name)/i);
        const workflowFromAttrs = getAttrValueByKey(attrs, /(traceloop\.workflow\.name|workflow\.name|skill\.name|traceloop\.entity\.name|entity\.name)/i);

        const spanName = getFirstString([
            trace.rootSpanName,
            trace.root_span_name,
            trace.rootSpan?.name,
            trace.spanName,
            trace.span_name,
            trace.operationName,
            trace.operation_name,
            trace.transactionName,
            trace.name,
            spanFromAttrs,
            trace.agentNames,
            trace.serviceNames
        ]) || `Trace ${(trace.traceId || '').slice(0, 8) || 'unknown'}`;

        const agentLabel = pickFirstLabeledValue([
            { value: trace.agentName, source: 'summary.agentName' },
            { value: trace.agent_name, source: 'summary.agent_name' },
            { value: trace['agent.name'], source: 'summary.agent.name' },
            { value: trace.agentNames, source: 'summary.agentNames' },
            { value: trace.agent, source: 'summary.agent' },
            { value: trace.agentId, source: 'summary.agentId' },
            { value: trace.agent_id, source: 'summary.agent_id' },
            { value: trace.agentIds, source: 'summary.agentIds' },
            { value: trace.agent?.name, source: 'summary.agent.name.nested' },
            { value: trace.rootSpan?.agent, source: 'summary.rootSpan.agent' },
            { value: trace.rootSpan?.agentName, source: 'summary.rootSpan.agentName' },
            { value: agentFromAttrs, source: 'attributes.agent-like' }
        ]);

        const entityLabel = pickFirstLabeledValue([
            { value: trace.workflowName, source: 'summary.workflowName' },
            { value: trace.entityName, source: 'summary.entityName' },
            { value: workflowFromAttrs, source: 'attributes.workflow-or-entity' },
            { value: trace.serviceName, source: 'summary.serviceName' },
            { value: trace.serviceNames, source: 'summary.serviceNames' }
        ]);

        const agentName = agentLabel?.value || 'Unknown Agent';
        const entityName = entityLabel?.value || 'Unknown Entity';
        const searchBlob = buildSearchBlob(trace, spanName, agentName, entityName);

        return {
            spanName,
            agentName,
            agentSource: agentLabel?.source || 'fallback.unknown',
            entityName,
            entitySource: entityLabel?.source || 'fallback.unknown',
            searchBlob,
            hasConversation: false,
            hasTools: false,
            hasErrors: false,
            isInterrupt: false,
            isInfrastructure: false,
            analyzed: false
        };
    }

    /**
     * Attempts to parse a JSON-looking string while leaving plain text intact.
     */
    function safeJsonParse(value) {
        if (value === null || value === undefined) return null;
        if (typeof value !== 'string') return value;

        const trimmed = value.trim();
        if (!trimmed) return null;
        if (!(trimmed.startsWith('{') || trimmed.startsWith('[') || trimmed.startsWith('"'))) return value;

        try {
            return JSON.parse(trimmed);
        } catch {
            return value;
        }
    }

    /**
     * Converts structured values into a readable string for rendering and search.
     */
    function valueToText(value) {
        if (value === null || value === undefined) return '';
        if (typeof value === 'string') return value;
        return JSON.stringify(value, null, 2);
    }

    /**
     * Normalizes OTLP status codes and string forms into a single error check.
     */
    function isErrorStatusCode(code) {
        const normalized = String(code ?? '').toUpperCase();
        return code === 2 || code === '2' || normalized === 'STATUS_CODE_ERROR' || normalized === 'ERROR';
    }

    /**
     * Returns a quick key/value lookup map for a span's decoded attributes.
     */
    function getSpanAttrMap(span) {
        return getSpanAttributes(span).reduce((acc, attr) => {
            acc[attr.key] = attr.value;
            return acc;
        }, {});
    }

    /**
     * Recursively extracts chat-like messages from structured entity payloads.
     */
    function collectMessages(value, acc = [], depth = 0) {
        if (value === null || value === undefined || depth > 8 || acc.length > 40) return acc;

        if (Array.isArray(value)) {
            value.forEach((item) => collectMessages(item, acc, depth + 1));
            return acc;
        }

        if (typeof value !== 'object') return acc;

        const role = value.role || value.type || value.kwargs?.type;
        const content = value.content ?? value.kwargs?.content;
        const name = value.name || value.kwargs?.name || value.kwargs?.id?.slice?.(-1)?.[0] || '';
        const toolCalls = value.tool_calls || value.kwargs?.tool_calls || [];
        const normalizedRole = typeof role === 'string' ? role.toLowerCase() : '';

        if ((normalizedRole || typeof content === 'string') && content !== undefined) {
            acc.push({
                role: normalizedRole || 'message',
                name,
                content: valueToText(content),
                toolCalls: Array.isArray(toolCalls) ? toolCalls : []
            });
        }

        Object.values(value).forEach((child) => collectMessages(child, acc, depth + 1));
        return acc;
    }

    /**
     * Recursively extracts tool call records from structured entity payloads.
     */
    function collectToolCalls(value, acc = [], depth = 0) {
        if (value === null || value === undefined || depth > 8 || acc.length > 40) return acc;

        if (Array.isArray(value)) {
            value.forEach((item) => collectToolCalls(item, acc, depth + 1));
            return acc;
        }

        if (typeof value !== 'object') return acc;

        const toolCalls = value.tool_calls || value.kwargs?.tool_calls;
        if (Array.isArray(toolCalls)) {
            toolCalls.forEach((call) => {
                acc.push({
                    id: call.id || call.tool_call_id || '',
                    name: call.name || call.function?.name || call.tool_name || 'unknown_tool',
                    args: call.args || call.arguments || call.function?.arguments || call.kwargs || null
                });
            });
        }

        Object.values(value).forEach((child) => collectToolCalls(child, acc, depth + 1));
        return acc;
    }

    /**
     * Removes duplicate items according to a caller-supplied identity function.
     */
    function uniqueBy(items, getKey) {
        const seen = new Set();
        return items.filter((item) => {
            const key = getKey(item);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    }

    /**
     * Extracts the higher-level artifacts used by the inspector: conversation
     * messages, tool calls, and correlation identifiers such as agent/thread ids.
     */
    function extractConversationArtifacts(spansList) {
        const correlation = {
            agentName: '',
            agentSource: '',
            entityName: '',
            entitySource: '',
            agentId: '',
            userId: '',
            sessionId: '',
            threadId: '',
            globalTransactionId: ''
        };

        const events = [];
        const toolInvocations = [];

        spansList.forEach((span) => {
            const attrs = getSpanAttrMap(span);
            const structuredInput = safeJsonParse(attrs['traceloop.entity.input'] ?? attrs.input);
            const structuredOutput = safeJsonParse(attrs['traceloop.entity.output'] ?? attrs.output);
            const messages = uniqueBy([
                ...collectMessages(structuredInput),
                ...collectMessages(structuredOutput)
            ], (item) => `${item.role}|${item.name}|${item.content}`);
            const toolCalls = uniqueBy([
                ...collectToolCalls(structuredInput),
                ...collectToolCalls(structuredOutput),
                ...messages.flatMap((msg) => (Array.isArray(msg.toolCalls) ? msg.toolCalls : []))
            ].map((call) => ({
                id: call.id || call.tool_call_id || '',
                name: call.name || call.function?.name || call.tool_name || 'unknown_tool',
                args: call.args || call.arguments || call.function?.arguments || call.kwargs || null
            })), (item) => `${item.id}|${item.name}|${valueToText(item.args)}`);

            const prompts = getSpanAttributes(span)
                .filter((attr) => /^gen_ai\.prompt(\.\d+)?\.content$/.test(attr.key))
                .map((attr) => valueToText(attr.value))
                .filter(Boolean);
            const completions = getSpanAttributes(span)
                .filter((attr) => /^gen_ai\.completion(\.\d+)?\.content$/.test(attr.key))
                .map((attr) => valueToText(attr.value))
                .filter(Boolean);

            if (!correlation.agentName && valueToText(attrs['agent.name'])) {
                correlation.agentName = valueToText(attrs['agent.name']);
                correlation.agentSource = 'agent.name';
            }
            if (!correlation.agentName && valueToText(attrs['traceloop.agent.name'])) {
                correlation.agentName = valueToText(attrs['traceloop.agent.name']);
                correlation.agentSource = 'traceloop.agent.name';
            }
            if (!correlation.agentName && valueToText(attrs['assistant.name'])) {
                correlation.agentName = valueToText(attrs['assistant.name']);
                correlation.agentSource = 'assistant.name';
            }
            if (!correlation.agentName && valueToText(attrs['assistant.id'])) {
                correlation.agentName = valueToText(attrs['assistant.id']);
                correlation.agentSource = 'assistant.id';
            }
            if (!correlation.entityName && valueToText(attrs['traceloop.workflow.name'])) {
                correlation.entityName = valueToText(attrs['traceloop.workflow.name']);
                correlation.entitySource = 'traceloop.workflow.name';
            }
            if (!correlation.entityName && valueToText(attrs['workflow.name'])) {
                correlation.entityName = valueToText(attrs['workflow.name']);
                correlation.entitySource = 'workflow.name';
            }
            if (!correlation.entityName && valueToText(attrs['skill.name'])) {
                correlation.entityName = valueToText(attrs['skill.name']);
                correlation.entitySource = 'skill.name';
            }
            if (!correlation.entityName && valueToText(attrs['traceloop.entity.name'])) {
                correlation.entityName = valueToText(attrs['traceloop.entity.name']);
                correlation.entitySource = 'traceloop.entity.name';
            }
            correlation.agentId = correlation.agentId || valueToText(attrs['agent.id']);
            correlation.userId = correlation.userId || valueToText(attrs['user.id']);
            correlation.sessionId = correlation.sessionId || valueToText(attrs['session.id']) || valueToText(attrs['langfuse.session.id']);
            correlation.threadId = correlation.threadId || valueToText(attrs['thread.id']) || valueToText(attrs['traceloop.association.properties.thread_id']);
            correlation.globalTransactionId = correlation.globalTransactionId || valueToText(attrs['global_transaction_id']);

            if (messages.length || toolCalls.length || prompts.length || completions.length || structuredInput || structuredOutput) {
                events.push({
                    spanId: span.spanId || '',
                    spanName: span.name || 'span',
                    spanKind: valueToText(attrs['traceloop.span.kind']) || valueToText(attrs['span.kind']) || span.kind || '',
                    entityName: valueToText(attrs['traceloop.entity.name']) || '',
                    durationMs: formatDurationMs(span.startTimeUnixNano, span.endTimeUnixNano),
                    messages,
                    toolCalls,
                    prompts,
                    completions,
                    structuredInput,
                    structuredOutput
                });
            }

            toolCalls.forEach((call) => {
                toolInvocations.push({
                    spanId: span.spanId || '',
                    spanName: span.name || 'span',
                    entityName: valueToText(attrs['traceloop.entity.name']) || '',
                    durationMs: formatDurationMs(span.startTimeUnixNano, span.endTimeUnixNano),
                    name: call.name,
                    args: call.args
                });
            });
        });

        return {
            correlation,
            events,
            toolInvocations: uniqueBy(toolInvocations, (item) => `${item.spanName}|${item.name}|${normalizeComparableText(item.args)}`)
        };
    }

    /**
     * Detects coarse booleans that drive filters and badges in the UI.
     */
    function detectTraceSignals(spansList, artifacts) {
        const hasConversation = artifacts.events.some((event) => {
            if (event.messages.length || event.prompts.length || event.completions.length) return true;
            const structured = `${valueToText(event.structuredInput)} ${valueToText(event.structuredOutput)}`;
            return /(messages|wxo_thread_id|resume|human|ai|tool_calls)/i.test(structured);
        });

        const hasTools = artifacts.toolInvocations.length > 0;
        const hasErrors = spansList.some((span) => {
            const attrs = getSpanAttrMap(span);
            return isErrorStatusCode(span.status?.code) || attrs['exception.message'] || attrs['error.message'] || attrs['exception.stacktrace'];
        });
        const isInterrupt = spansList.some((span) => {
            const attrs = getSpanAttrMap(span);
            return valueToText(attrs['traceloop.association.properties.is_interrupt']).toLowerCase() === 'true';
        });

        const isInfrastructure = spansList.length > 0 && spansList.every((span) => {
            const attrs = getSpanAttrMap(span);
            const attrKeys = Object.keys(attrs);
            const hasHttpClientShape = Boolean(attrs['http.method'] && attrs['http.url'])
                || valueToText(attrs['span.kind']).toLowerCase() === 'client';
            const hasAutoHttpInstrumentation = /opentelemetry\.instrumentation\.(requests|urllib3|httpx|aiohttp)/i.test(valueToText(attrs['otel.scope.name']));
            const hasAgentOrConversationSignals = attrKeys.some((key) => /^(agent\.|traceloop\.|gen_ai\.|langfuse\.|thread\.id$|session\.id$|user\.id$|global_transaction_id$)/i.test(key));
            return hasHttpClientShape && (hasAutoHttpInstrumentation || valueToText(attrs['internal.span.format']).toLowerCase() === 'otlp') && !hasAgentOrConversationSignals;
        }) && !hasConversation && !hasTools;

        return { hasConversation, hasTools, hasErrors, isInterrupt, isInfrastructure };
    }

    /**
     * Builds a parent/child tree from the flat span list for hierarchy rendering.
     */
    function buildSpanTree(spansForExplorer) {
        const byId = new Map();
        const roots = [];

        spansForExplorer.forEach((row) => {
            byId.set(row.span.spanId, { ...row, children: [] });
        });

        spansForExplorer.forEach((row) => {
            const node = byId.get(row.span.spanId);
            const parentId = row.span.parentSpanId;
            if (parentId && byId.has(parentId)) {
                byId.get(parentId).children.push(node);
            } else {
                roots.push(node);
            }
        });

        return roots;
    }

    /**
     * Buckets spans into visual categories so the hierarchy and timeline can use
     * consistent colors and labels.
     */
    function getSpanVisualType(row) {
        const kind = String(row.spanKind || row.span.kind || '').toLowerCase();
        const name = String(row.span.name || '').toLowerCase();
        const attrs = row.attrs || [];
        const hasToolCall = attrs.some((attr) => /tool|function/.test(attr.key)) || /tool/.test(name);

        if (!row.span.parentSpanId) return 'root';
        if (kind.includes('workflow') || name.includes('workflow') || name.includes('langgraph')) return 'workflow';
        if (kind.includes('task') || name.includes('.task')) return 'task';
        if (kind.includes('llm') || kind.includes('gen_ai') || name.includes('completion') || name.includes('prompt')) return 'llm';
        if (hasToolCall || name.includes('tool')) return 'tool';
        return 'task';
    }

    /**
     * Maps the derived span type or error state to the color used in the UI.
     */
    function getSpanToneColor(row) {
        if (isErrorStatusCode(row.statusCode) || row.span._isError) return 'var(--error)';
        const type = getSpanVisualType(row);
        if (type === 'root') return '#67e8f9';
        if (type === 'workflow') return '#8bf2a3';
        if (type === 'tool') return '#ff9f6e';
        if (type === 'llm') return '#c7a6ff';
        return '#ffd166';
    }

    /**
     * Keeps the timeline, tree, tool cards, and explorer rows synchronized by
     * span id once the inspector modal has been rendered.
     */
    function setupInspectorInteractions() {
        // Interactions now live inside the inspector modal body
        const inspector = document.getElementById('inspector-modal-body');
        if (!inspector) return;

        const clearSelection = () => {
            inspector.querySelectorAll('.selected').forEach((el) => el.classList.remove('selected'));
        };

        const highlightSpan = (spanId) => {
            if (!spanId) return;
            clearSelection();
            const targets = inspector.querySelectorAll(`[data-span-id="${spanId}"]`);
            targets.forEach((el) => el.classList.add('selected'));
            const first = targets[0];
            if (first) first.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        };

        inspector.querySelectorAll('.span-selectable').forEach((el) => {
            el.addEventListener('click', () => {
                highlightSpan(el.getAttribute('data-span-id'));
            });
        });

        const expandBtn = inspector.querySelector('[data-span-tree-action="expand"]');
        const collapseBtn = inspector.querySelector('[data-span-tree-action="collapse"]');
        if (expandBtn) {
            expandBtn.addEventListener('click', () => {
                inspector.querySelectorAll('.span-tree-node').forEach((node) => { node.open = true; });
            });
        }
        if (collapseBtn) {
            collapseBtn.addEventListener('click', () => {
                inspector.querySelectorAll('.span-tree-node').forEach((node) => { node.open = false; });
            });
        }
    }

    /**
     * Recursively renders the span hierarchy view used in the inspector.
     */
    function renderSpanTreeNodes(nodes, depth = 0) {
        if (!nodes.length) return '';

        const renderValue = (val) => {
            if (val === null || val === undefined) return '';
            if (typeof val === 'string') return escapeHtml(val);
            return escapeHtml(JSON.stringify(val));
        };

        return `<div class="span-tree${depth > 0 ? ' span-tree-children' : ''}">
            ${nodes.map((node) => {
                const s = node.span;
                const isError = isErrorStatusCode(node.statusCode) || Boolean(s._isError);
                const statusLabel = isError ? 'ERROR' : ((node.statusCode === 1 || String(node.statusCode).toUpperCase() === 'STATUS_CODE_OK') ? 'OK' : 'UNSET');
                const header = `
                    <summary class="span-tree-summary span-selectable" data-span-id="${escapeHtml(s.spanId || '')}">
                        <div class="span-tree-label">
                            <span class="span-tree-kind span-tone-${getSpanVisualType(node)}">${escapeHtml(node.spanKind || s.kind || 'span')}</span>
                            <span class="span-tree-name">${escapeHtml(s.name || 'span')}</span>
                        </div>
                        <div class="span-tree-meta">${escapeHtml(statusLabel)} · ${escapeHtml(node.durationMs)}</div>
                    </summary>
                `;

                const details = `
                    <div class="span-tree-details">
                        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:8px;">
                            <div>Span ID: <span style="font-family:monospace; color:var(--text-primary);">${escapeHtml(s.spanId || '')}</span></div>
                            <div>Parent ID: <span style="font-family:monospace; color:var(--text-primary);">${escapeHtml(s.parentSpanId || '')}</span></div>
                        </div>
                        ${node.statusMessage ? `<div style="margin-bottom:8px; color:var(--error);">${escapeHtml(node.statusMessage)}</div>` : ''}
                        ${node.attrs.length ? `
                            <details>
                                <summary style="cursor:pointer; color:var(--text-secondary);">Top attributes (${node.attrs.length})</summary>
                                <div style="margin-top:8px; max-height:180px; overflow:auto; border:1px solid var(--border-glass); border-radius:6px;">
                                    <table class="spans-table">
                                        <thead><tr><th>Key</th><th>Value</th></tr></thead>
                                        <tbody>
                                            ${node.attrs.slice(0, 10).map((a) => `<tr><td>${escapeHtml(a.key)}</td><td style="white-space:pre-wrap; word-break:break-word;">${renderValue(a.value)}</td></tr>`).join('')}
                                        </tbody>
                                    </table>
                                </div>
                            </details>
                        ` : ''}
                    </div>
                `;

                return `<details class="span-tree-node${isError ? ' error' : ''}" data-span-id="${escapeHtml(s.spanId || '')}" ${depth < 2 ? 'open' : ''}>${header}${details}${renderSpanTreeNodes(node.children, depth + 1)}</details>`;
            }).join('')}
        </div>`;
    }

    /**
     * Determines whether a trace summary needs full-span enrichment to become
     * useful in the list and filters.
     */
    function isMissingUiLabels(trace) {
        const meta = trace._uiMeta || buildTraceUiMeta(trace);
        const hasGenericTraceName = /^Trace [a-f0-9]{8}$/i.test(meta.spanName || '');
        return meta.agentName === 'Unknown Agent' || hasGenericTraceName;
    }

    /**
     * Derives better user-facing labels and coarse signal flags from the full
     * span export returned by the backend.
     */
    function collectSpanMeta(spanData) {
        const resourceSpans = spanData?.traceData?.resourceSpans || [];
        const spans = [];
        const allAttrs = [];

        resourceSpans.forEach((rs) => {
            allAttrs.push(...normalizeAttributePairs(rs.attributes));
            (rs.scopeSpans || []).forEach((ss) => {
                (ss.spans || []).forEach((span) => {
                    spans.push(span);
                    allAttrs.push(...normalizeAttributePairs(span.attributes));
                });
            });
        });

        const rootSpan = spans.find((span) => !span.parentSpanId) || spans[0] || null;
        const artifacts = extractConversationArtifacts(spans);
        const likelyEntityName = artifacts.events.find((event) => {
            if (!event.entityName) return false;
            return !/tool|function|http|request/i.test(event.entityName);
        })?.entityName;
        const spanName = getFirstString([
            rootSpan?.name,
            getAttrValueByKey(allAttrs, /(root.*span.*name|span.*name|operation.*name|transaction.*name)$/i)
        ]);

        const agentLabel = pickFirstLabeledValue([
            { value: artifacts.correlation.agentName, source: artifacts.correlation.agentSource || 'correlation.agent' },
            { value: getAttrValueByKey(allAttrs, /(^agent(\.|_|$))|(^agent\.name$)|(agent.*name)|(orchestrate.*agent)|(wxo.*agent)|(assistant.*name)/i), source: 'attributes.agent-like' },
            { value: getAttrValueByKey(allAttrs, /(assistant\.id|assistant\.name)/i), source: 'attributes.assistant-like' }
        ]);

        const entityLabel = pickFirstLabeledValue([
            { value: artifacts.correlation.entityName, source: artifacts.correlation.entitySource || 'correlation.entity' },
            { value: getAttrValueByKey(allAttrs, /(traceloop\.workflow\.name|workflow\.name|skill\.name)/i), source: 'attributes.workflow-name' },
            { value: likelyEntityName, source: 'conversation.entityName' },
            { value: getAttrValueByKey(allAttrs, /(traceloop\.entity\.name|entity\.name)/i), source: 'attributes.entity-name' }
        ]);

        const signals = detectTraceSignals(spans, artifacts);

        return {
            spanName,
            agentName: agentLabel?.value || '',
            agentSource: agentLabel?.source || '',
            entityName: entityLabel?.value || '',
            entitySource: entityLabel?.source || '',
            ...signals
        };
    }

    /**
     * Background enrichment pass that upgrades weak summaries with data pulled
     * from full span exports. This is intentionally capped to protect the API.
     */
    async function enrichMissingTraceMetadata(forceAnalyzeAll = false) {
        const missing = allTraces
            .filter((trace) => {
                if (!trace.traceId || traceMetadataInflight.has(trace.traceId)) return false;
                if (forceAnalyzeAll && !trace._uiMeta?.analyzed) return true;
                return isMissingUiLabels(trace);
            })
            .slice(0, forceAnalyzeAll ? 24 : 12);

        if (missing.length === 0) return;

        missing.forEach((trace) => traceMetadataInflight.add(trace.traceId));

        const env = encodeURIComponent(envSelector.value || '');
        const updates = await Promise.all(missing.map(async (trace) => {
            try {
                const res = await fetch(`/api/traces/${encodeURIComponent(trace.traceId)}/spans?env=${env}`);
                if (!res.ok) return null;

                const spanData = await res.json();
                const extracted = collectSpanMeta(spanData);
                if (!extracted.spanName && !extracted.agentName && !extracted.hasConversation && !extracted.hasTools && !extracted.hasErrors && !extracted.isInterrupt) return null;

                return { traceId: trace.traceId, extracted };
            } catch {
                return null;
            } finally {
                traceMetadataInflight.delete(trace.traceId);
            }
        }));

        let changed = false;
        updates.filter(Boolean).forEach(({ traceId, extracted }) => {
            const trace = allTraces.find((item) => item.traceId === traceId);
            if (!trace) return;

            const current = trace._uiMeta || buildTraceUiMeta(trace);
            const nextSpanName = extracted.spanName || current.spanName;
            const nextAgentName = extracted.agentName || current.agentName;
            const nextEntityName = extracted.entityName || current.entityName;
            const nextSearchBlob = buildSearchBlob(trace, nextSpanName, nextAgentName, nextEntityName);

            if (
                nextSpanName !== current.spanName ||
                nextAgentName !== current.agentName ||
                nextEntityName !== current.entityName ||
                nextSearchBlob !== current.searchBlob ||
                extracted.hasConversation !== current.hasConversation ||
                extracted.hasTools !== current.hasTools ||
                extracted.hasErrors !== current.hasErrors ||
                extracted.isInterrupt !== current.isInterrupt ||
                extracted.isInfrastructure !== current.isInfrastructure ||
                !current.analyzed
            ) {
                trace._uiMeta = {
                    spanName: nextSpanName,
                    agentName: nextAgentName,
                    agentSource: extracted.agentSource || current.agentSource,
                    entityName: nextEntityName,
                    entitySource: extracted.entitySource || current.entitySource,
                    searchBlob: nextSearchBlob,
                    hasConversation: extracted.hasConversation,
                    hasTools: extracted.hasTools,
                    hasErrors: extracted.hasErrors,
                    isInterrupt: extracted.isInterrupt,
                    isInfrastructure: extracted.isInfrastructure,
                    analyzed: true
                };
                changed = true;
            }
        });

        if (changed) filterAndRender();
    }

    /**
     * Formats span duration from OTLP nanoseconds into milliseconds.
     */
    function formatDurationMs(startNano, endNano) {
        if (!startNano || !endNano) return 'n/a';
        const dur = (BigInt(endNano) - BigInt(startNano)) / 1000000n;
        return `${dur}ms`;
    }

    /**
     * Returns a span's decoded attributes in a render-friendly format.
     */
    function getSpanAttributes(span) {
        return (span.attributes || []).map((attr) => ({
            key: attr.key || '',
            value: decodeOtlpValue(attr.value)
        }));
    }

    /**
     * Returns decoded OTLP events for a span.
     */
    function getSpanEvents(span) {
        return (span.events || []).map((ev) => ({
            name: ev.name || 'event',
            timestamp: ev.timeUnixNano || '',
            attrs: (ev.attributes || []).map((a) => ({ key: a.key || '', value: decodeOtlpValue(a.value) }))
        }));
    }

    /**
     * Returns decoded OTLP links for a span.
     */
    function getSpanLinks(span) {
        return (span.links || []).map((lnk) => ({
            traceId: lnk.traceId || '',
            spanId: lnk.spanId || '',
            attrs: (lnk.attributes || []).map((a) => ({ key: a.key || '', value: decodeOtlpValue(a.value) }))
        }));
    }
    
    /**
     * Returns the best current agent label for a trace.
     */
    function getAgentName(trace) {
        if (trace._uiMeta?.agentName) return trace._uiMeta.agentName;
        return (
            trace.agentName ||
            trace.agent ||
            trace.agent_id ||
            trace.agentId ||
            trace.rootSpanName ||
            'Unknown Agent'
        );
    }

    /**
     * Returns the best current human-readable trace name.
     */
    function getTraceName(trace) {
        if (trace._uiMeta?.spanName) return trace._uiMeta.spanName;
        return trace.rootSpanName || trace.name || `Trace ${(trace.traceId || '').slice(0, 8) || 'unknown'}`;
    }

    /**
     * Collapses formatting differences so duplicate payloads compare reliably.
     */
    function normalizeComparableText(value) {
        return valueToText(value).replace(/\s+/g, ' ').trim();
    }

    /**
     * Hides source tags that only repeat generic summary-derived metadata.
     */
    function isDerivedSummarySource(source) {
        return !source || source === 'fallback.unknown' || source.startsWith('summary.') || source.startsWith('fallback.');
    }

    /**
     * Checks both summary metadata and hydrated error details for errors.
     */
    function traceHasErrors(trace) {
        const cached = trace?.traceId ? errorInsightsCache.get(trace.traceId) : null;
        return Boolean(trace?._uiMeta?.hasErrors || cached?.errors?.length);
    }

    /**
     * Builds the human-readable filter labels shown in the workspace summary.
     */
    function getActiveFilterLabels() {
        const labels = [];
        const textQuery = agentFilter.value.trim();
        if (textQuery) labels.push(`Query: ${textQuery}`);
        if (conversationOnlyToggle.checked) labels.push('Conversation only');
        if (toolsOnlyToggle.checked) labels.push('Only traces with tools');
        if (errorsOnlyToggle.checked) labels.push('Only error traces');
        if (excludeInfraToggle.checked) labels.push('Hide infra HTTP');
        if (errorExplorerFocus.agentName) labels.push(`Error agent: ${errorExplorerFocus.agentName}`);
        if (errorExplorerFocus.spanName) labels.push(`Error span: ${errorExplorerFocus.spanName}`);
        if (errorExplorerFocus.message) labels.push(`Exception: ${errorExplorerFocus.message}`);
        return labels;
    }

    /**
     * Returns a short, local-time label for the active date range.
     */
    function formatCurrentTimeRange() {
        const start = toIsoFromLocalInput(timeStartInput.value);
        const end = toIsoFromLocalInput(timeEndInput.value);
        if (!start || !end) return 'Custom range';

        const startText = new Date(start).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        const endText = new Date(end).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        return `${startText} → ${endText}`;
    }

    /**
     * Renders the compact status bar showing the selected system, time range,
     * and currently active filters.
     */
    function renderWorkspaceSummary() {
        if (!workspaceSummary) return;

        const filters = getActiveFilterLabels();
        const timeStr = escapeHtml(formatCurrentTimeRange());
        const systemStr = escapeHtml(envSelector.value || 'No system selected');
        const filterChips = filters.length
            ? `<span class="status-bar-sep">·</span><span class="status-bar-filters">${filters.map((label) => `<span class="workspace-chip">${escapeHtml(label)}</span>`).join('')}</span>`
            : '';

        workspaceSummary.innerHTML = `
            <div class="status-bar">
                <span class="status-bar-system">📡 ${systemStr}</span>
                <span class="status-bar-sep">·</span>
                <span>⏱ ${timeStr}</span>
                ${filterChips}
            </div>
        `;
    }

    /**
     * Centralized filtering so the overview cards, list, and error explorer all
     * operate on exactly the same visible result set.
     */
    function getFilteredTraces() {
        const q = agentFilter.value.trim();
        const qLower = normalizeFilterQuery(q);
        return allTraces.filter((trace) => {
            const name = getTraceName(trace);
            const id = trace.traceId || '';
            const agent = getAgentName(trace);
            const searchBlob = trace._uiMeta?.searchBlob || '';
            const matchesText = fuzzyMatch(name, q) || id.includes(q) || fuzzyMatch(agent, q) || searchBlob.includes(qLower);
            const matchesConversation = !conversationOnlyToggle.checked || Boolean(trace._uiMeta?.hasConversation);
            const matchesTools = !toolsOnlyToggle.checked || Boolean(trace._uiMeta?.hasTools);
            const matchesErrors = !errorsOnlyToggle.checked || traceHasErrors(trace);
            const matchesInfra = !excludeInfraToggle.checked || !Boolean(trace._uiMeta?.isInfrastructure);
            const matchesExplorerFocus = matchesErrorExplorerFocus(trace);
            return matchesText && matchesConversation && matchesTools && matchesErrors && matchesInfra && matchesExplorerFocus;
        });
    }

    /**
     * Renders grouped exception analytics for the currently visible traces.
     */
    function renderErrorExplorer(traces) {
        if (!errorExplorerContent || !errorExplorerCount) return;

        const traceCandidates = traces.filter((trace) => trace.traceId);
        const analyzedCount = traceCandidates.filter((trace) => errorInsightsCache.has(trace.traceId)).length;
        const loadingCount = traceCandidates.filter((trace) => errorInsightsInflight.has(trace.traceId)).length;
        const errorTraces = traces.filter((trace) => traceHasErrors(trace));
        errorExplorerCount.textContent = String(errorTraces.length);

        if (!errorTraces.length) {
            errorExplorerContent.innerHTML = `
                <div class="empty-state" style="height:auto; min-height: 180px;">
                    <div class="empty-icon">⚠️</div>
                    <p>${loadingCount || (traceCandidates.length && analyzedCount < traceCandidates.length) ? `Analyzing visible traces for hidden errors... ${loadingCount ? `(${loadingCount} loading)` : ''}` : 'No error traces are visible in the current time range and filter set.'}</p>
                </div>
            `;
            return;
        }

        const cached = errorTraces
            .map((trace) => errorInsightsCache.get(trace.traceId))
            .filter(Boolean);
        const pendingCount = errorTraces.length - cached.length;
        const agentCounts = new Map();
        const spanCounts = new Map();
        const exceptionGroups = new Map();

        cached.forEach((entry) => {
            entry.errors.forEach((error) => {
                const agentKey = error.agentName || 'Unknown Agent';
                agentCounts.set(agentKey, (agentCounts.get(agentKey) || 0) + 1);

                const spanKey = error.spanName || 'Unknown Span';
                spanCounts.set(spanKey, (spanCounts.get(spanKey) || 0) + 1);

                const messageKey = (error.message || 'Unknown error').trim();
                const group = exceptionGroups.get(messageKey) || {
                    count: 0,
                    agents: new Set(),
                    spans: new Set(),
                    traces: new Set(),
                    examples: []
                };

                group.count += 1;
                group.agents.add(agentKey);
                group.spans.add(spanKey);
                if (error.traceId) group.traces.add(error.traceId);
                if (group.examples.length < 4) {
                    group.examples.push({
                        agentName: agentKey,
                        spanName: spanKey,
                        traceId: error.traceId || '',
                        message: error.message || messageKey
                    });
                }
                exceptionGroups.set(messageKey, group);
            });
        });

        const topAgents = Array.from(agentCounts.entries()).sort((a, b) => b[1] - a[1]).slice(0, 6);
        const topSpans = Array.from(spanCounts.entries()).sort((a, b) => b[1] - a[1]).slice(0, 6);
        const groupedExceptions = Array.from(exceptionGroups.entries()).sort((a, b) => b[1].count - a[1].count);

        const renderActionList = (rows, emptyLabel, type) => rows.length
            ? rows.map(([label, count]) => `
                <button
                    type="button"
                    class="error-summary-action ${(
                        (type === 'agent' && errorExplorerFocus.agentName === label && !errorExplorerFocus.spanName && !errorExplorerFocus.message) ||
                        (type === 'span' && errorExplorerFocus.spanName === label && !errorExplorerFocus.message)
                    ) ? 'is-active' : ''}"
                    data-error-filter-type="${type}"
                    data-error-filter-value="${escapeHtml(label)}"
                >
                    <span class="error-summary-action-label">${escapeHtml(label)}</span>
                    <span class="error-summary-action-count">${count}</span>
                </button>
            `).join('')
            : `<div class="error-summary-empty">${escapeHtml(emptyLabel)}</div>`;

        const buildFocusChip = (label, value, key) => `
            <button
                type="button"
                class="error-focus-chip"
                data-error-focus-remove="${key}"
                title="Remove ${label.toLowerCase()} filter"
            >
                <span class="error-focus-chip-label">${escapeHtml(label)}: ${escapeHtml(value)}</span>
                <span class="error-focus-chip-close">✕</span>
            </button>
        `;

        const focusChips = [];
        if (errorExplorerFocus.agentName) focusChips.push(buildFocusChip('Agent', errorExplorerFocus.agentName, 'agentName'));
        if (errorExplorerFocus.spanName) focusChips.push(buildFocusChip('Span', errorExplorerFocus.spanName, 'spanName'));
        if (errorExplorerFocus.message) focusChips.push(buildFocusChip('Exception', errorExplorerFocus.message, 'message'));

        errorExplorerContent.innerHTML = `
            <div class="error-explorer-toolbar">
                <div class="error-explorer-status">Analyzed ${cached.length} of ${errorTraces.length} visible error traces in the current time frame.${pendingCount ? ` Loading ${pendingCount} more...` : ''}</div>
                ${loadingCount ? `<div class="badge">Fetching ${loadingCount} traces</div>` : ''}
            </div>
            ${focusChips.length ? `
                <div class="error-focus-bar">
                    <div class="error-focus-chips">${focusChips.join('')}</div>
                    <button type="button" class="btn btn-outline btn-sm" data-error-filter-clear="true">Clear error focus</button>
                </div>
            ` : ''}
            <div class="error-summary-grid">
                <div class="error-summary-card">
                    <div class="error-summary-title">Top Failing Agents</div>
                    <div class="error-summary-actions">${renderActionList(topAgents, 'No failing agents analyzed yet.', 'agent')}</div>
                </div>
                <div class="error-summary-card">
                    <div class="error-summary-title">Top Failing Spans</div>
                    <div class="error-summary-actions">${renderActionList(topSpans, 'No failing spans analyzed yet.', 'span')}</div>
                </div>
            </div>
            <div class="error-summary-title" style="margin-bottom:12px;">Grouped Exceptions</div>
            <div class="error-groups">
                ${groupedExceptions.length ? groupedExceptions.slice(0, 12).map(([message, group]) => `
                    <div class="error-group">
                        <div class="error-group-topline">
                            <div class="error-group-message">${escapeHtml(message)}</div>
                            <div class="error-group-count">${group.count}</div>
                        </div>
                        <div class="error-group-subline">
                            <div class="error-group-meta">
                                <span class="error-meta-pill">${group.agents.size} agent${group.agents.size === 1 ? '' : 's'}</span>
                                <span class="error-meta-pill">${group.spans.size} span${group.spans.size === 1 ? '' : 's'}</span>
                                <span class="error-meta-pill">${group.traces.size} trace${group.traces.size === 1 ? '' : 's'}</span>
                            </div>
                            <button
                                type="button"
                                class="error-meta-action ${errorExplorerFocus.message === message ? 'is-active' : ''}"
                                data-error-message="${escapeHtml(message)}"
                            >Show traces</button>
                        </div>
                        <ul class="error-group-list">
                            ${group.examples.map((example) => `
                                <li>
                                    <button
                                        type="button"
                                        class="error-trace-link"
                                        data-trace-id="${escapeHtml(example.traceId || '')}"
                                        title="Open trace ${(example.traceId || '').slice(0, 8)}"
                                    >
                                        <span>${escapeHtml(example.agentName)}</span>
                                        <span class="error-trace-link-sep">·</span>
                                        <span>${escapeHtml(example.spanName)}</span>
                                        <span class="error-trace-link-sep">·</span>
                                        <span class="error-trace-link-id">${escapeHtml((example.traceId || '').slice(0, 8))}</span>
                                    </button>
                                </li>
                            `).join('')}
                        </ul>
                    </div>
                `).join('') : '<div style="color:var(--text-secondary);">Waiting for detailed error payloads...</div>'}
            </div>
        `;
    }

    /**
     * Extracts per-trace error records from a full span export for aggregation.
     */
    function extractErrorInsights(trace, spanData) {
        const resourceSpans = spanData?.traceData?.resourceSpans || [];
        const spans = [];

        resourceSpans.forEach((rs) => {
            (rs.scopeSpans || []).forEach((ss) => {
                (ss.spans || []).forEach((span) => spans.push(span));
            });
        });

        const collectedMeta = collectSpanMeta(spanData);
        const agentName = collectedMeta.agentName || getAgentName(trace);
        const errors = [];

        spans.forEach((span) => {
            const attrs = getSpanAttrMap(span);
            const statusMessage = valueToText(span.status?.message);
            const exceptionMessage = valueToText(attrs['exception.message']);
            const errorMessage = valueToText(attrs['error.message']);
            const exceptionType = valueToText(attrs['exception.type']);
            const stackTrace = valueToText(attrs['exception.stacktrace']);
            const headline = exceptionMessage || errorMessage || statusMessage || exceptionType;

            if (!isErrorStatusCode(span.status?.code) && !headline && !stackTrace) return;

            errors.push({
                traceId: trace.traceId || '',
                spanId: span.spanId || '',
                spanName: span.name || 'span',
                agentName,
                message: headline || `${span.name || 'span'} failed`,
                detail: stackTrace || statusMessage || ''
            });
        });

        return {
            traceId: trace.traceId || '',
            agentName,
            errors
        };
    }

    /**
     * Lazily hydrates error details only for the traces visible in the current
     * result set to keep the UI responsive.
     */
    async function hydrateErrorInsights(traces) {
        const candidates = traces
            .filter((trace) => trace.traceId && !errorInsightsCache.has(trace.traceId) && !errorInsightsInflight.has(trace.traceId))
            .slice(0, 12);

        if (!candidates.length) return;

        candidates.forEach((trace) => errorInsightsInflight.add(trace.traceId));
        renderErrorExplorer(traces);

        const env = encodeURIComponent(envSelector.value || '');
        const updates = await Promise.all(candidates.map(async (trace) => {
            try {
                const res = await fetch(`/api/traces/${encodeURIComponent(trace.traceId)}/spans?env=${env}`);
                if (!res.ok) return null;
                const spanData = await res.json();
                return extractErrorInsights(trace, spanData);
            } catch {
                return null;
            } finally {
                errorInsightsInflight.delete(trace.traceId);
            }
        }));

        let changed = false;
        updates.filter(Boolean).forEach((entry) => {
            if (!entry?.traceId) return;
            errorInsightsCache.set(entry.traceId, entry);
            const target = allTraces.find((trace) => trace.traceId === entry.traceId);
            if (target?._uiMeta && entry.errors?.length) {
                target._uiMeta.hasErrors = true;
            }
            changed = true;
        });

        if (changed) {
            renderErrorExplorer(getFilteredTraces());
        }
    }

    /**
     * Renders the systems management list and attaches edit/remove handlers.
     */
    function renderSystemsList() {
        if (!environmentDetails.length) {
            systemsList.innerHTML = '<div style="padding: 8px; color: var(--text-secondary);">No systems configured yet.</div>';
            return;
        }

        systemsList.innerHTML = environmentDetails.map((env) => {
            const canEdit = env.source === 'local';
            return `
                <div class="system-row">
                    <div>
                        <div class="system-name">${escapeHtml(env.name)}</div>
                        <div class="system-source">${env.source === 'env' ? '📄 from .env (read-only)' : '📝 local session'}</div>
                    </div>
                    <div class="system-url" title="${escapeHtml(env.url || '')}">${escapeHtml(env.url || '')}</div>
                    <div style="display:flex; gap:6px;">
                        <button class="btn btn-outline edit-system-btn" data-name="${escapeHtml(env.name)}" data-url="${escapeHtml(env.url || '')}" ${canEdit ? '' : 'disabled title="Managed from .env"'}>Edit</button>
                        <button class="btn btn-outline remove-system-btn" data-name="${escapeHtml(env.name)}" ${canEdit ? '' : 'disabled title="Managed from .env"'}>Remove</button>
                    </div>
                </div>
            `;
        }).join('');

        systemsList.querySelectorAll('.remove-system-btn').forEach((btn) => {
            btn.addEventListener('click', async () => {
                const name = btn.dataset.name;
                if (!name) return;
                await removeSystem(name);
            });
        });

        systemsList.querySelectorAll('.edit-system-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                const name = btn.dataset.name;
                const url = btn.dataset.url;
                if (!name) return;
                // Populate and show edit form
                editSystemOriginalName.value = name;
                editSystemName.value = name;
                editSystemUrl.value = url;
                editSystemKey.value = '';
                systemForm.style.display = 'none';
                editSystemForm.style.display = '';
                systemsStatusText.textContent = `Editing: ${name}`;
                editSystemName.focus();
            });
        });
    }

    /**
     * Removes a locally-added environment from the current session.
     */
    async function removeSystem(name) {
        systemsStatusText.textContent = '';
        try {
            const res = await fetch(`/api/environments/${encodeURIComponent(name)}`, { method: 'DELETE' });
            const payload = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(payload.error || `Failed to remove system (${res.status})`);

            systemsStatusText.textContent = `Removed system: ${name}`;
            await loadEnvironments();
        } catch (e) {
            systemsStatusText.textContent = e.message;
        }
    }

    /**
     * Updates a locally-added environment through the backend API.
     */
    async function editSystem(originalName, newName, url, key) {
        systemsStatusText.textContent = '';
        try {
            const res = await fetch(`/api/environments/${encodeURIComponent(originalName)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName, url, key })
            });
            const payload = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(payload.error || `Failed to update system (${res.status})`);

            systemsStatusText.textContent = `Updated system: ${newName}`;
            editSystemForm.style.display = 'none';
            systemForm.style.display = '';
            await loadEnvironments();
        } catch (e) {
            systemsStatusText.textContent = e.message;
        }
    }

    /**
     * Loads environment metadata, repopulates the selector, and boots the first
     * trace load once the backend confirms at least one environment exists.
     */
    async function loadEnvironments() {
        if (runningFromFileProtocol) {
            renderLocalFileModeWarning();
            return;
        }

        try {
            const previousSelection = envSelector.value;
            const res = await fetch('/api/environments/details');
            if (!res.ok) throw new Error(`Failed to load environments (${res.status})`);

            const payload = await res.json();
            const envs = Array.isArray(payload.environments) ? payload.environments : [];
            environmentDetails = envs;

            if (!Array.isArray(envs) || envs.length === 0) {
                envSelector.innerHTML = '<option value="">No environments</option>';
                traceList.innerHTML = '<div style="padding: 20px; text-align:center; color:#ff6b6b;">No environments are configured in the backend.</div>';
                renderSystemsList();
                return;
            }

            envSelector.innerHTML = '';
            envs.forEach(env => {
                const opt = document.createElement('option');
                opt.value = env.name;
                opt.textContent = env.name;
                envSelector.appendChild(opt);
            });

            const selectedExists = envs.some((env) => env.name === previousSelection);
            if (selectedExists) envSelector.value = previousSelection;

            renderSystemsList();
            loadTraces(); // Boot
        } catch(e) {
            console.error("Could not load environments", e);
            renderTraceLoadError('Could not load environments from backend.', {
                url: '/api/environments/details',
                details: e.message
            });
        }
    }

    /**
     * Initializes the default time window to the last hour in local time.
     */
    function initDates() {
        const now = new Date();
        const start = new Date(now.getTime() - 60 * 60000); // 1 hr ago
        
        // Remove 'Z' format to perfectly match datetime-local local timezone format
        timeEndInput.value = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
        timeStartInput.value = new Date(start.getTime() - start.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    }
    initDates();

    /**
     * Fetches trace summaries for the currently selected environment and time
     * range, then kicks off rendering and optional background enrichment.
     */
    async function loadTraces() {
        const startIso = toIsoFromLocalInput(timeStartInput.value);
        const endIso = toIsoFromLocalInput(timeEndInput.value);
        if (!startIso || !endIso) {
            traceList.innerHTML = '<div style="padding: 20px; text-align:center; color:#ff6b6b;">Please provide a valid start and end time.</div>';
            return;
        }

        const params = new URLSearchParams({
            env: envSelector.value || '',
            start_time: startIso,
            end_time: endIso
        });
        const requestUrl = `/api/traces?${params.toString()}`;
        const now = Date.now();

        if (traceSearchCooldownUntil > now && activeTraceLoadKey === requestUrl) {
            renderTraceLoadError('Trace search is temporarily rate limited.', {
                url: requestUrl,
                status: 429,
                retryAfterMs: traceSearchCooldownUntil - now,
                details: 'The upstream observability API asked the dashboard to slow down. Wait for the cooldown before retrying the same query.'
            });
            return;
        }

        if (traceLoadPromise && activeTraceLoadKey === requestUrl) {
            return traceLoadPromise;
        }

        if (activeTraceLoadController) {
            activeTraceLoadController.abort();
        }

        traceList.innerHTML = '<div style="padding: 20px; text-align:center;">Loading traces... ⏳</div>';
        activeTraceLoadController = new AbortController();
        activeTraceLoadKey = requestUrl;

        traceLoadPromise = (async () => {
            try {
                const res = await fetch(requestUrl, { signal: activeTraceLoadController.signal });
            if (!res.ok) {
                let payload = null;
                let msg = '';
                try {
                    payload = await res.json();
                    msg = payload?.error || payload?.details || JSON.stringify(payload);
                } catch {
                    msg = await res.text();
                }
                const retryAfter = payload?.retryAfter || '';
                const retryAfterMs = payload?.retryAfterMs || 0;
                if (res.status === 429 && retryAfterMs) {
                    traceSearchCooldownUntil = Date.now() + retryAfterMs;
                }
                renderTraceLoadError(`Failed to load traces (${res.status})`, {
                    url: requestUrl,
                    status: res.status,
                    requestId: payload?.requestId || '',
                    retryAfter,
                    retryAfterMs,
                    details: msg || 'No error message returned by backend.'
                });
                return;
            }

            traceSearchCooldownUntil = 0;

            const data = await res.json();
            
            if (data.summaries) {
                errorInsightsCache.clear();
                errorInsightsInflight.clear();
                allTraces = data.summaries.map((trace) => ({
                    ...trace,
                    _uiMeta: buildTraceUiMeta(trace)
                }));
                filterAndRender();
                enrichMissingTraceMetadata(conversationOnlyToggle.checked || toolsOnlyToggle.checked);
            } else {
                traceList.innerHTML = '<div style="padding: 20px; text-align:center; color:#ff6b6b;">Error loading traces.</div>';
            }
            } catch (e) {
                if (e.name === 'AbortError') return;
                console.error(e);
                renderTraceLoadError('Network error. Backend may be down or unreachable.', {
                    url: requestUrl,
                    details: e.message
                });
            } finally {
                traceLoadPromise = null;
                activeTraceLoadController = null;
            }
        })();

        return traceLoadPromise;
    }
    
    /**
     * Simple normalized text matching used by the free-text filter.
     */
    function fuzzyMatch(str, query) {
        const normalizedQuery = normalizeFilterQuery(query);
        if (!normalizedQuery) return true;
        const lowerStr = String(str || '').toLowerCase().replace(/[_.-]+/g, ' ');
        // Split query into words so "Greet Agent" matches "Greeter Agent"
        return normalizedQuery.split(' ').every(term => lowerStr.includes(term));
    }

    /**
     * Recomputes the visible trace set and refreshes every dependent UI surface.
     */
    function filterAndRender() {
        const filtered = getFilteredTraces();
        renderWorkspaceSummary();
        renderOverview(filtered);
        renderErrorExplorer(filtered);
        renderTraceList(filtered);
        hydrateErrorInsights(filtered);
    }

    /**
     * Renders the top-level overview cards for the current filtered result set.
     */
    function renderOverview(traces) {
        if (!overviewStrip) return;

        if (!traces.length) {
            overviewStrip.innerHTML = `
                <div class="overview-card glass" style="grid-column: 1 / -1; min-height:auto;">
                    <div class="overview-label">Overview</div>
                    <div class="overview-note">No traces match the current system, time window, or filters.</div>
                </div>
            `;
            return;
        }

        const errors = traces.filter((trace) => traceHasErrors(trace));
        const withTools = traces.filter((trace) => trace._uiMeta?.hasTools);
        const withConversation = traces.filter((trace) => trace._uiMeta?.hasConversation);
        const infrastructure = traces.filter((trace) => trace._uiMeta?.isInfrastructure);
        const agentCounts = new Map();

        traces.forEach((trace) => {
            const agentName = getAgentName(trace);
            const current = agentCounts.get(agentName) || { total: 0, errors: 0 };
            current.total += 1;
            if (traceHasErrors(trace)) current.errors += 1;
            agentCounts.set(agentName, current);
        });

        const topAgentEntry = Array.from(agentCounts.entries())
            .sort((left, right) => {
                if (right[1].errors !== left[1].errors) return right[1].errors - left[1].errors;
                return right[1].total - left[1].total;
            })[0];

        const topAgentName = topAgentEntry?.[0] || 'None';
        const topAgentStats = topAgentEntry?.[1] || { total: 0, errors: 0 };

        overviewStrip.innerHTML = `
            <div class="overview-card glass">
                <div class="overview-label">Visible Traces</div>
                <div class="overview-value">${traces.length}</div>
                <div class="overview-note">${infrastructure.length ? `${infrastructure.length} visible trace${infrastructure.length === 1 ? '' : 's'} look like infrastructure HTTP traffic.` : 'Current result set after system, time, and text filters.'}</div>
            </div>
            <div class="overview-card glass clickable ${errorsOnlyToggle.checked ? 'active-filter' : ''}" data-overview-action="toggle-errors-only">
                <div class="overview-label">Error Traces</div>
                <div class="overview-value error">${errors.length}</div>
                <div class="overview-note">${errors.length ? `${Math.round((errors.length / traces.length) * 100)}% of visible traces contain exceptions or error spans. Click to ${errorsOnlyToggle.checked ? 'show all traces' : 'filter to errors only'}.` : 'No visible traces currently show captured errors.'}</div>
            </div>
            <div class="overview-card glass">
                <div class="overview-label">Tool Activity</div>
                <div class="overview-value tool">${withTools.length}</div>
                <div class="overview-note">${withTools.length ? `${withTools.length} traces include tool calls. Use the Tools toggle to isolate them.` : 'No tool-calling traces are visible in the current window.'}</div>
            </div>
            <div class="overview-card glass">
                <div class="overview-label">Agent Hotspot</div>
                <div class="overview-value agent">${escapeHtml(topAgentName)}</div>
                <div class="overview-note">${topAgentStats.errors ? `${topAgentStats.errors} error trace${topAgentStats.errors === 1 ? '' : 's'} across ${topAgentStats.total} visible run${topAgentStats.total === 1 ? '' : 's'}.` : `${withConversation.length} visible traces contain conversation payloads.`}</div>
            </div>
        `;
    }

    /**
     * Renders the clickable trace list shown in the main left-hand panel.
     */
    function renderTraceList(traces) {
        traceList.innerHTML = '';
        traceCount.textContent = traces.length;

        if (traces.length === 0) {
            const filters = getActiveFilterLabels();
            traceList.innerHTML = `<div style="padding: 20px; text-align:center; color:var(--text-secondary);">No traces match the current time window.${filters.length ? ` Active filters: ${escapeHtml(filters.join(', '))}.` : ''}</div>`;
            return;
        }

        traces.forEach(trace => {
            const el = document.createElement('div');
            el.className = 'trace-item';
            el.dataset.traceId = trace.traceId || '';
            
            // Format time safely
            let localTime = new Date(trace.startTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            if (localTime === 'Invalid Date') localTime = '--:--:--';
            
            let name = getTraceName(trace);
            if(name.length > 30) name = name.substring(0,30) + '...';
            const traceId = trace.traceId || 'unknown';
            const agentName = getAgentName(trace);
            const meta = trace._uiMeta || {};
            const entityName = meta.entityName || 'Unknown Entity';
            const contextParts = [];
            if (agentName && agentName !== name) contextParts.push(agentName);
            if (
                entityName
                && entityName !== 'Unknown Entity'
                && entityName !== agentName
                && entityName !== name
                && !(entityName === 'wxo-server' && isDerivedSummarySource(meta.entitySource))
            ) {
                contextParts.push(entityName);
            }
            const sourceLabels = [];
            if (!isDerivedSummarySource(meta.agentSource) && meta.agentSource !== meta.entitySource) sourceLabels.push(`agent: ${meta.agentSource}`);
            if (!isDerivedSummarySource(meta.entitySource)) sourceLabels.push(`entity: ${meta.entitySource}`);
            const badges = [];
            if (meta.hasConversation) badges.push('<span class="trace-pill conversation">Chat</span>');
            if (meta.hasTools) badges.push('<span class="trace-pill tool">Tools</span>');
            if (meta.isInterrupt) badges.push('<span class="trace-pill interrupt">Interrupt</span>');
            if (meta.hasErrors) badges.push('<span class="trace-pill error">Error</span>');
            if (meta.isInfrastructure) badges.push('<span class="trace-pill infra">Infra HTTP</span>');

            el.innerHTML = `
                <div class="trace-topline">
                    <div class="trace-name-block">
                        <div class="trace-name">${name}</div>
                        ${contextParts.length ? `<div class="trace-context-row">${contextParts.map((part) => `<span class="trace-context-chip">${escapeHtml(part)}</span>`).join('')}</div>` : ''}
                    </div>
                    <div class="trace-topline-meta">
                        <span>${localTime}</span>
                        <span class="trace-id">${traceId.substring(0,8)}...</span>
                    </div>
                </div>
                ${badges.length ? `<div class="trace-badges trace-badges-inline">${badges.join('')}</div>` : ''}
                ${sourceLabels.length ? `<div class="trace-source-line">${escapeHtml(sourceLabels.join(' • '))}</div>` : ''}
            `;

            el.addEventListener('click', () => {
                document.querySelectorAll('.trace-item').forEach(i => i.classList.remove('active-trace'));
                el.classList.add('active-trace');
                inspectTrace(trace);
            });

            traceList.appendChild(el);
        });
    }

    /**
     * Fetches the full span payload for a trace and opens the inspector modal.
     */
    async function inspectTrace(trace) {
        // Open modal with loading state
        inspectorModalBody.innerHTML = '<div class="inspector-modal-loading">Fetching detailed spans… 🔬</div>';
        const traceName = getTraceName(trace);
        inspectorModalTitle.textContent = `${traceName} · ${(trace.traceId || '').slice(0, 16)}…`;
        inspectorModal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';

        try {
            const traceId = trace.traceId;
            if (!traceId) throw new Error('Missing trace identifier');

            const env = encodeURIComponent(envSelector.value || '');
            const res = await fetch(`/api/traces/${encodeURIComponent(traceId)}/spans?env=${env}`);
            if (!res.ok) {
                const msg = await res.text();
                throw new Error(msg || `Failed to fetch spans (${res.status})`);
            }

            const spanData = await res.json();
            renderInspector(trace, spanData);
        } catch (e) {
            console.error(e);
            inspectorModalBody.innerHTML = `<div class="inspector-modal-loading" style="color:#ff6b6b;">Failed to fetch trace spans: ${escapeHtml(e.message)}</div>`;
        }
    }

    /**
     * Closes the inspector modal and clears list selection state.
     */
    function closeInspectorModal() {
        inspectorModal.classList.add('hidden');
        document.body.style.overflow = '';
        document.querySelectorAll('.trace-item').forEach(i => i.classList.remove('active-trace'));
    }

    /**
     * Extracts inspector-specific derived data such as token counts, recovered
     * LLM prompts/completions, reasoning snippets, and captured errors.
     */
    function extractTokens(traceData) {
        let promptT = 0;
        let compT = 0;
        let spansList = [];
        let chatLogs = [];
        let thoughts = [];
        let systemPrompt = null;
        let errorList = [];

        const resourceSpans = traceData.traceData?.resourceSpans || [];
        resourceSpans.forEach(rs => {
            (rs.scopeSpans || []).forEach(ss => {
                (ss.spans || []).forEach(span => {
                    const attrs = getSpanAttrMap(span);
                    const statusMessage = valueToText(span.status?.message);
                    const exceptionMessage = valueToText(attrs['exception.message']);
                    const errorMessage = valueToText(attrs['error.message']);
                    const exceptionType = valueToText(attrs['exception.type']);
                    const stackTrace = valueToText(attrs['exception.stacktrace']);

                    // Check for Status Code 2 (Error in OTLP)
                    if (isErrorStatusCode(span.status?.code) || statusMessage || exceptionMessage || errorMessage || stackTrace) {
                        errorList.push({
                            spanName: span.name || 'span',
                            message: exceptionMessage || errorMessage || statusMessage || `${span.name || 'span'} failed`,
                            detail: stackTrace || statusMessage || '',
                            type: exceptionType || '',
                            statusCode: span.status?.code || ''
                        });
                        span._isError = true;
                    }
                    
                    spansList.push(span);
                    let pText = null;
                    let cText = null;
                    
                    (span.attributes || []).forEach(attr => {
                        const k = attr.key || '';
                        const v = parseInt(attr.value?.intValue || attr.value?.stringValue || '0', 10);
                        if (k.includes('token') && k.includes('prompt')) promptT += v;
                        if (k.includes('token') && (k.includes('completion') || k.includes('output'))) compT += v;
                        
                        // Strict OpenTelemetry / GenAI standard extraction (avoid generic 'message')
                        const strVal = attr.value?.stringValue;
                        if (strVal && strVal.length > 0) {
                            if (k.match(/^gen_ai\.prompt(\.\d+)?\.content$/) || k === 'llm.prompts') pText = strVal;
                            if (k.match(/^gen_ai\.completion(\.\d+)?\.content$/) || k === 'llm.completions') cText = strVal;
                            if (k.match(/^gen_ai\.system(\.\d+)?\.content$/) || k === 'gen_ai.system') systemPrompt = strVal;

                            // Capture thought/reasoning style attributes when present in traces.
                            if (/(thought|reasoning|analysis|rationale|reflection|plan|deliberat|decision)/i.test(k)) {
                                thoughts.push({ spanName: span.name || 'unknown-span', key: k, text: strVal });
                            }
                        }
                    });
                    
                    if (pText) chatLogs.push({ role: 'Underlying LLM Prompt', text: pText, spanName: span.name });
                    if (cText) chatLogs.push({ role: 'LLM Completion text', text: cText, spanName: span.name });
                });
            });
        });
        
        // Sort spans chronologically safely
        spansList.sort((a,b) => {
            const aStart = BigInt(a.startTimeUnixNano || '0');
            const bStart = BigInt(b.startTimeUnixNano || '0');
            if (aStart < bStart) return -1;
            if (aStart > bStart) return 1;
            return 0;
        });
        
        const limitedThoughts = thoughts.slice(0, 25);
        const dedupedErrors = Array.from(new Map(errorList.map((error) => [`${error.spanName}|${error.message}|${error.detail}`, error])).values());
        const dedupedChatLogs = uniqueBy(chatLogs, (item) => `${item.role}|${item.spanName}|${normalizeComparableText(item.text)}`);
        return { promptT, compT, spansList, chatLogs: dedupedChatLogs, thoughts: limitedThoughts, systemPrompt, errorList: dedupedErrors };
    }

    /**
     * Renders the full inspector modal, including stats, tools, conversation
     * flow, hierarchy, timeline, span explorer, and raw trace payloads.
     */
    function renderInspector(summary, spanData) {
        const { promptT, compT, spansList, chatLogs, thoughts, systemPrompt, errorList } = extractTokens(spanData);
        const { correlation, events: conversationEvents, toolInvocations } = extractConversationArtifacts(spansList);
        
        let localTime = new Date(summary.startTime).toLocaleString();
        const agentName = correlation.agentName || getAgentName(summary);
        const entityName = summary._uiMeta?.entityName || correlation.entityName || 'Unknown Entity';

        const spansForExplorer = spansList.map((s) => {
            const attrs = getSpanAttributes(s);
            const events = getSpanEvents(s);
            const links = getSpanLinks(s);
            return {
                span: s,
                attrs,
                events,
                links,
                spanKind: valueToText(getSpanAttrMap(s)['traceloop.span.kind']) || valueToText(getSpanAttrMap(s)['span.kind']) || s.kind || '',
                durationMs: formatDurationMs(s.startTimeUnixNano, s.endTimeUnixNano),
                statusCode: s.status?.code || 0,
                statusMessage: s.status?.message || ''
            };
        });

        const spanTree = buildSpanTree(spansForExplorer);

        const totalEvents = spansForExplorer.reduce((sum, row) => sum + row.events.length, 0);
        const totalLinks = spansForExplorer.reduce((sum, row) => sum + row.links.length, 0);
        const totalAttributes = spansForExplorer.reduce((sum, row) => sum + row.attrs.length, 0);
        const cleanedConversationEvents = conversationEvents.map((event) => {
            const messages = uniqueBy(event.messages, (item) => `${item.role}|${item.name}|${normalizeComparableText(item.content)}`);
            return {
                ...event,
                messages,
                prompts: uniqueBy(event.prompts, (item) => normalizeComparableText(item)).filter((item) => !messages.some((msg) => normalizeComparableText(msg.content) === normalizeComparableText(item))),
                completions: uniqueBy(event.completions, (item) => normalizeComparableText(item)).filter((item) => !messages.some((msg) => normalizeComparableText(msg.content) === normalizeComparableText(item)))
            };
        }).filter((event) => event.messages.length || event.prompts.length || event.completions.length || event.structuredInput || event.structuredOutput);
        const sectionSummary = (title, countLabel = '') => `<summary class="inspector-section-summary"><span>${escapeHtml(title)}</span>${countLabel ? `<span class="inspector-section-count">${escapeHtml(countLabel)}</span>` : ''}</summary>`;

        let statsHTML = `
            <div class="stats-grid">
                <div class="stat-card">
                    <h4>Total Spans</h4>
                    <div class="value">${spansList.length}</div>
                </div>
                <div class="stat-card tokens">
                    <h4>Prompt Tokens</h4>
                    <div class="value">${promptT}</div>
                </div>
                <div class="stat-card tokens">
                    <h4>Completion Tokens</h4>
                    <div class="value">${compT}</div>
                </div>
                <div class="stat-card ${errorList.length ? 'stat-card-error' : ''}">
                    <h4>Errors</h4>
                    <div class="value">${errorList.length}</div>
                </div>
            </div>
        `;

        const inspectorSummaryHTML = `
            <section class="inspector-summary-block">
                <div class="inspector-summary-grid">
                    <div class="inspector-summary-item">
                        <div class="inspector-summary-label">Started</div>
                        <div class="inspector-summary-value">${escapeHtml(localTime)}</div>
                    </div>
                    <div class="inspector-summary-item">
                        <div class="inspector-summary-label">Agent</div>
                        <div class="inspector-summary-value">${escapeHtml(agentName)}</div>
                    </div>
                    <div class="inspector-summary-item">
                        <div class="inspector-summary-label">Entity</div>
                        <div class="inspector-summary-value">${escapeHtml(entityName)}</div>
                    </div>
                    <div class="inspector-summary-item">
                        <div class="inspector-summary-label">Trace ID</div>
                        <div class="inspector-summary-value inspector-summary-mono">${escapeHtml(summary.traceId || 'unknown')}</div>
                    </div>
                </div>
            </section>
        `;

        let minTime = spansList.reduce((min, s) => s.startTimeUnixNano && BigInt(s.startTimeUnixNano) < min ? BigInt(s.startTimeUnixNano) : min, BigInt('999999999999999999'));
        let maxTime = spansList.reduce((max, s) => s.endTimeUnixNano && BigInt(s.endTimeUnixNano) > max ? BigInt(s.endTimeUnixNano) : max, BigInt(0));
        let totalDur = maxTime > minTime ? (maxTime - minTime) : 1n;

        let timelineHTML = spansForExplorer.map((row, idx) => {
            const s = row.span;
            if(!s.startTimeUnixNano || !s.endTimeUnixNano) return '';
            let start = BigInt(s.startTimeUnixNano);
            let end = BigInt(s.endTimeUnixNano);
            let left = Number((start - minTime) * 100n / totalDur);
            let width = Number((end - start) * 100n / totalDur);
            if(width < 0.5) width = 0.5;
            let durMs = Number((end - start) / 1000000n) + 'ms';
            let barColor = getSpanToneColor(row);
            
            return `<div style="display:flex; align-items:center; margin-bottom:8px; font-family:monospace; position:relative;" class="gantt-row timeline-span-row span-selectable" data-span-id="${escapeHtml(s.spanId || '')}">
                        <div style="width:220px; font-size:0.75rem; color:${s._isError?'var(--error)':'var(--text-secondary)'}; text-overflow:ellipsis; overflow:hidden; white-space:nowrap; padding-right:8px;" title="${escapeHtml(s.name || 'span')}">${escapeHtml(s.name || 'span')}</div>
                        <div style="flex:1; height:18px; background:rgba(0,0,0,0.3); border-radius:4px; position:relative; overflow:hidden;">
                            <div style="position:absolute; left:${left}%; width:${width}%; height:100%; background:${barColor}; border-radius:4px; opacity:0.85; cursor:help; transition:opacity 0.2s;" class="timeline-span-bar" title="${escapeHtml(s.name || 'span')} | ${durMs}"></div>
                        </div>
                        <div style="width:70px; text-align:right; font-size:0.75rem; color:var(--text-secondary);">${durMs}</div>
                    </div>`;
        }).join('');

        // 2. ERROR & SYSTEM PROMPT VIEWER
        let insightsHTML = '';
        if (errorList.length > 0) {
            insightsHTML += `
                <div class="inspector-error-summary">
                    <h4 class="inspector-error-title">⚠️ Exceptions Detected</h4>
                    <div class="inspector-error-list">
                        ${errorList.map((error) => `
                            <div class="inspector-error-item">
                                <div class="inspector-error-item-header">
                                    <span class="inspector-error-span">${escapeHtml(error.spanName)}</span>
                                    <span class="inspector-error-code">${escapeHtml(String(error.statusCode || 'ERROR'))}</span>
                                </div>
                                <div class="inspector-error-message">${escapeHtml(error.message)}</div>
                                ${error.type ? `<div class="inspector-error-meta">Type: ${escapeHtml(error.type)}</div>` : ''}
                                ${error.detail ? `<details class="inspector-error-detail"><summary>Show details</summary><pre>${escapeHtml(error.detail)}</pre></details>` : ''}
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }

        let thoughtHTML = '';
        if (thoughts.length > 0) {
            thoughtHTML = `
                <div style="margin-top:24px;">
                    <h4 style="margin-bottom:12px; color:var(--text-secondary);">Thought Process Signals</h4>
                    ${thoughts.map(t => `
                        <details style="margin-bottom:8px; font-size:0.85rem; background:rgba(255,255,255,0.03); padding:10px; border-radius:6px; border:1px solid var(--border-glass);">
                            <summary style="color:var(--text-secondary); font-weight:600; outline:none;">${escapeHtml(t.spanName)} · ${escapeHtml(t.key)}</summary>
                            <div style="margin-top:10px; white-space:pre-wrap; word-break:break-word; font-family:monospace; color:var(--text-primary);">${escapeHtml(t.text)}</div>
                        </details>
                    `).join('')}
                </div>
            `;
        }

        const correlationRows = [
            ['Agent ID', correlation.agentId],
            ['User ID', correlation.userId],
            ['Session ID', correlation.sessionId],
            ['Thread ID', correlation.threadId],
            ['Global Transaction ID', correlation.globalTransactionId]
        ].filter(([, value]) => value);

        const correlationHTML = correlationRows.length > 0 ? `
            <details class="inspector-section" style="margin-top:24px;">
                ${sectionSummary('Trace Correlation', `${correlationRows.length} ids`)}
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
                    ${correlationRows.map(([label, value]) => `
                        <div style="background:rgba(0,0,0,0.28); border:1px solid var(--border-glass); border-radius:8px; padding:10px;">
                            <div style="font-size:0.76rem; color:var(--text-secondary); text-transform:uppercase; letter-spacing:0.08em; margin-bottom:6px;">${escapeHtml(label)}</div>
                            <div style="font-family:monospace; font-size:0.84rem; word-break:break-word;">${escapeHtml(value)}</div>
                        </div>
                    `).join('')}
                </div>
            </details>
        ` : '';

        const toolsHTML = `
            <details class="inspector-section" style="margin-top:24px;">
                ${sectionSummary('Tools Invoked', `${toolInvocations.length}`)}
                ${toolInvocations.length > 0 ? toolInvocations.map((tool) => `
                    <div style="padding:12px; margin-bottom:8px; border-radius:8px; background:rgba(255,255,255,0.03); border:1px solid var(--border-glass);" class="trace-linked-card span-selectable" data-span-id="${escapeHtml(tool.spanId || '')}">
                        <div style="display:flex; justify-content:space-between; gap:10px; margin-bottom:6px;">
                            <strong style="color:#8bf2a3;">${escapeHtml(tool.name)}</strong>
                            <span style="font-size:0.78rem; color:var(--text-secondary); font-family:monospace;">${escapeHtml(tool.durationMs)}</span>
                        </div>
                        <div style="font-size:0.78rem; color:var(--text-secondary); margin-bottom:8px;">Span: ${escapeHtml(tool.spanName)}${tool.entityName ? ` · Entity: ${escapeHtml(tool.entityName)}` : ''}</div>
                        ${tool.args ? `<pre style="margin:0; white-space:pre-wrap; word-break:break-word; font-size:0.78rem; line-height:1.35; background:rgba(0,0,0,0.3); border-radius:6px; padding:10px; border:1px solid rgba(255,255,255,0.04);">${escapeHtml(valueToText(tool.args))}</pre>` : '<div style="font-size:0.8rem; color:var(--text-secondary);">No arguments captured.</div>'}
                    </div>
                `).join('') : '<div style="color:var(--text-secondary);">No tool invocations were detected in the captured span payload.</div>'}
            </details>
        `;

        const conversationHTML = `
            <details class="inspector-section" style="margin-top:24px;">
                ${sectionSummary('Conversation Flow', `${cleanedConversationEvents.length}`)}
                ${cleanedConversationEvents.length > 0 ? cleanedConversationEvents.map((event) => `
                    <details style="margin-bottom:10px; background:rgba(255,255,255,0.02); border:1px solid var(--border-glass); border-radius:8px; padding:10px;" class="trace-linked-card" data-span-id="${escapeHtml(event.spanId || '')}" ${event.messages.length ? 'open' : ''}>
                        <summary style="display:flex; justify-content:space-between; gap:10px; cursor:pointer; list-style:none;" class="span-selectable" data-span-id="${escapeHtml(event.spanId || '')}">
                            <span style="font-family:monospace; color:var(--text-primary);">${escapeHtml(event.spanName)}</span>
                            <span style="font-size:0.78rem; color:var(--text-secondary);">${escapeHtml(event.entityName || event.spanKind || 'span')} · ${escapeHtml(event.durationMs)}</span>
                        </summary>
                        ${event.messages.length ? `
                            <div style="margin-top:10px;">
                                ${event.messages.map((msg) => `
                                    <div style="padding:10px; margin-bottom:8px; border-radius:8px; background:${msg.role.includes('human') ? 'rgba(93,92,255,0.1)' : msg.role.includes('ai') ? 'rgba(40,167,69,0.12)' : 'rgba(255,255,255,0.04)'}; border:1px solid rgba(255,255,255,0.06);">
                                        <div style="font-size:0.74rem; color:var(--text-secondary); text-transform:uppercase; letter-spacing:0.08em; margin-bottom:6px;">${escapeHtml(msg.role || 'message')}${msg.name ? ` · ${escapeHtml(msg.name)}` : ''}</div>
                                        <div style="white-space:pre-wrap; word-break:break-word; font-family:monospace; font-size:0.84rem;">${escapeHtml(msg.content)}</div>
                                    </div>
                                `).join('')}
                            </div>
                        ` : ''}
                        ${(event.prompts.length || event.completions.length || event.structuredInput || event.structuredOutput) ? `
                            <details style="margin-top:10px;">
                                <summary style="cursor:pointer; color:var(--text-secondary);">Payload</summary>
                                ${event.prompts.length ? `<div style="margin-top:8px; font-size:0.76rem; color:var(--text-secondary); text-transform:uppercase; letter-spacing:0.08em; margin-bottom:6px;">Prompt Content</div>${event.prompts.map((prompt) => `<pre style="margin:0 0 8px 0; white-space:pre-wrap; word-break:break-word; font-size:0.8rem; background:rgba(93,92,255,0.08); border:1px solid rgba(93,92,255,0.18); border-radius:6px; padding:10px;">${escapeHtml(prompt)}</pre>`).join('')}` : ''}
                                ${event.completions.length ? `<div style="font-size:0.76rem; color:var(--text-secondary); text-transform:uppercase; letter-spacing:0.08em; margin:10px 0 6px;">Completion Content</div>${event.completions.map((completion) => `<pre style="margin:0 0 8px 0; white-space:pre-wrap; word-break:break-word; font-size:0.8rem; background:rgba(40,167,69,0.08); border:1px solid rgba(40,167,69,0.18); border-radius:6px; padding:10px;">${escapeHtml(completion)}</pre>`).join('')}` : ''}
                                ${event.structuredInput ? `<div style="font-size:0.76rem; color:var(--text-secondary); text-transform:uppercase; letter-spacing:0.08em; margin:10px 0 6px;">Structured Input</div><pre style="margin-top:8px; white-space:pre-wrap; word-break:break-word; font-size:0.78rem; background:rgba(0,0,0,0.3); border-radius:6px; padding:10px; border:1px solid rgba(255,255,255,0.04);">${escapeHtml(valueToText(event.structuredInput))}</pre>` : ''}
                                ${event.structuredOutput ? `<div style="font-size:0.76rem; color:var(--text-secondary); text-transform:uppercase; letter-spacing:0.08em; margin:10px 0 6px;">Structured Output</div><pre style="margin-top:8px; white-space:pre-wrap; word-break:break-word; font-size:0.78rem; background:rgba(0,0,0,0.3); border-radius:6px; padding:10px; border:1px solid rgba(255,255,255,0.04);">${escapeHtml(valueToText(event.structuredOutput))}</pre>` : ''}
                            </details>
                        ` : ''}
                    </details>
                `).join('') : '<div style="color:var(--text-secondary);">No conversation payload was detected in the captured spans.</div>'}
            </details>
        `;
        if (systemPrompt) {
            insightsHTML += `
                <details style="margin-top:16px; font-size:0.85rem; background:rgba(255,255,255,0.03); padding:10px; border-radius:6px; cursor:pointer; border:1px solid var(--border-glass);">
                    <summary style="color:var(--text-secondary); font-weight:600; outline:none;">View Hidden System Prompt</summary>
                    <div style="margin-top:12px; color:var(--text-primary); white-space:pre-wrap; word-break:break-word; cursor:text; padding:10px; background:rgba(0,0,0,0.4); border-radius:6px;">${escapeHtml(systemPrompt)}</div>
                </details>
            `;
        }

        const spanExplorerHTML = `
            <div class="span-explorer" style="margin-top:24px;">
                <h4 style="margin-bottom:12px; color:var(--text-secondary);">Span Explorer</h4>
                <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:12px;">
                    <div class="stat-card"><h4>Attributes</h4><div class="value" style="font-size:1.1rem;">${totalAttributes}</div></div>
                    <div class="stat-card"><h4>Events</h4><div class="value" style="font-size:1.1rem;">${totalEvents}</div></div>
                    <div class="stat-card"><h4>Links</h4><div class="value" style="font-size:1.1rem;">${totalLinks}</div></div>
                    <div class="stat-card"><h4>Errors</h4><div class="value" style="font-size:1.1rem; color:var(--error);">${errorList.length}</div></div>
                </div>
                ${spansForExplorer.map((row) => {
                    const s = row.span;
                    const statusLabel = isErrorStatusCode(row.statusCode) ? 'ERROR' : (String(row.statusCode) === '1' || row.statusCode === 1 || String(row.statusCode).toUpperCase() === 'STATUS_CODE_OK' ? 'OK' : 'UNSET');
                    const renderValue = (val) => {
                        if (val === null || val === undefined) return '';
                        if (typeof val === 'string') return escapeHtml(val);
                        return escapeHtml(JSON.stringify(val));
                    };

                    return `
                        <details style="margin-bottom:10px; background:rgba(255,255,255,0.02); border:1px solid var(--border-glass); border-radius:8px; padding:10px;" class="span-explorer-node" data-span-id="${escapeHtml(s.spanId || '')}" ${isErrorStatusCode(row.statusCode) ? 'open' : ''}>
                            <summary style="display:flex; justify-content:space-between; gap:10px; cursor:pointer; list-style:none;" class="span-selectable" data-span-id="${escapeHtml(s.spanId || '')}">
                                <span style="font-family:monospace; color:var(--text-primary);">${escapeHtml(s.name || 'span')}</span>
                                <span style="font-family:monospace; color:${isErrorStatusCode(row.statusCode) ? 'var(--error)' : 'var(--text-secondary)'};">${statusLabel} · ${row.durationMs}</span>
                            </summary>
                            <div style="margin-top:10px; display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:0.82rem; color:var(--text-secondary);">
                                <div>Span ID: <span style="font-family:monospace; color:var(--text-primary);">${escapeHtml(s.spanId || '')}</span></div>
                                <div>Parent ID: <span style="font-family:monospace; color:var(--text-primary);">${escapeHtml(s.parentSpanId || '')}</span></div>
                                <div>Start: <span style="font-family:monospace; color:var(--text-primary);">${escapeHtml(String(s.startTimeUnixNano || ''))}</span></div>
                                <div>End: <span style="font-family:monospace; color:var(--text-primary);">${escapeHtml(String(s.endTimeUnixNano || ''))}</span></div>
                            </div>
                            ${row.statusMessage ? `<div style="margin-top:8px; color:var(--error); font-size:0.82rem;">${escapeHtml(row.statusMessage)}</div>` : ''}
                            <details style="margin-top:10px;">
                                <summary style="cursor:pointer; color:var(--text-secondary);">Attributes (${row.attrs.length})</summary>
                                <div style="margin-top:8px; max-height:220px; overflow:auto; border:1px solid var(--border-glass); border-radius:6px;">
                                    <table class="spans-table">
                                        <thead><tr><th>Key</th><th>Value</th></tr></thead>
                                        <tbody>
                                            ${row.attrs.map((a) => `<tr><td>${escapeHtml(a.key)}</td><td style="white-space:pre-wrap; word-break:break-word;">${renderValue(a.value)}</td></tr>`).join('') || '<tr><td colspan="2" style="color:var(--text-secondary);">No attributes</td></tr>'}
                                        </tbody>
                                    </table>
                                </div>
                            </details>
                            <details style="margin-top:10px;">
                                <summary style="cursor:pointer; color:var(--text-secondary);">Events (${row.events.length})</summary>
                                <div style="margin-top:8px;">
                                    ${row.events.map((ev) => `
                                        <div style="padding:8px; border:1px solid var(--border-glass); border-radius:6px; margin-bottom:6px;">
                                            <div style="font-family:monospace; color:var(--text-primary); margin-bottom:4px;">${escapeHtml(ev.name)} · ${escapeHtml(String(ev.timestamp))}</div>
                                            <div style="font-size:0.82rem; color:var(--text-secondary);">
                                                ${ev.attrs.map((a) => `<div><strong>${escapeHtml(a.key)}</strong>: ${renderValue(a.value)}</div>`).join('') || 'No event attributes'}
                                            </div>
                                        </div>
                                    `).join('') || '<div style="color:var(--text-secondary);">No events</div>'}
                                </div>
                            </details>
                            <details style="margin-top:10px;">
                                <summary style="cursor:pointer; color:var(--text-secondary);">Links (${row.links.length})</summary>
                                <div style="margin-top:8px;">
                                    ${row.links.map((lnk) => `
                                        <div style="padding:8px; border:1px solid var(--border-glass); border-radius:6px; margin-bottom:6px; font-size:0.82rem;">
                                            <div style="font-family:monospace; color:var(--text-primary);">traceId: ${escapeHtml(lnk.traceId)}</div>
                                            <div style="font-family:monospace; color:var(--text-primary);">spanId: ${escapeHtml(lnk.spanId)}</div>
                                            <div style="margin-top:4px; color:var(--text-secondary);">
                                                ${lnk.attrs.map((a) => `<div><strong>${escapeHtml(a.key)}</strong>: ${renderValue(a.value)}</div>`).join('') || 'No link attributes'}
                                            </div>
                                        </div>
                                    `).join('') || '<div style="color:var(--text-secondary);">No links</div>'}
                                </div>
                            </details>
                        </details>
                    `;
                }).join('')}
            </div>
        `;

        const spanTreeHTML = `
            <div style="margin-top:24px;">
                <div class="span-tree-toolbar">
                    <h4 style="color:var(--text-secondary);">Execution Path</h4>
                    <div class="span-tree-controls">
                        <button type="button" class="btn btn-outline" data-span-tree-action="expand">Expand All</button>
                        <button type="button" class="btn btn-outline" data-span-tree-action="collapse">Collapse All</button>
                    </div>
                </div>
                <div class="span-legend" style="margin-bottom:12px;">
                    <span class="span-legend-item"><span class="span-legend-swatch swatch-root"></span>Root</span>
                    <span class="span-legend-item"><span class="span-legend-swatch swatch-workflow"></span>Workflow</span>
                    <span class="span-legend-item"><span class="span-legend-swatch swatch-task"></span>Task</span>
                    <span class="span-legend-item"><span class="span-legend-swatch swatch-tool"></span>Tool</span>
                    <span class="span-legend-item"><span class="span-legend-swatch swatch-llm"></span>LLM</span>
                    <span class="span-legend-item"><span class="span-legend-swatch swatch-error"></span>Error</span>
                </div>
                ${spanTree.length ? renderSpanTreeNodes(spanTree) : '<div style="color:var(--text-secondary);">No span hierarchy available.</div>'}
            </div>
        `;

        // 2. CHAT LOGIC 
        let chatHTML = '';
        if (chatLogs.length > 0) {
            chatHTML = `<details class="inspector-section" style="margin-top:24px;">
                ${sectionSummary('LLM Texts', `${chatLogs.length}`)}
                ${chatLogs.map(c => `
                    <div style="padding:12px; margin-bottom:8px; border-radius:8px; background:${c.role.includes('Prompt')?'rgba(93,92,255,0.1)':'rgba(40,167,69,0.1)'}; border:1px solid ${c.role.includes('Prompt')?'rgba(93,92,255,0.2)':'rgba(40,167,69,0.2)'}; font-size:0.9rem;">
                        <div style="display:flex; justify-content:space-between; align-items:flex-end;">
                            <strong style="display:block; margin-bottom:4px; font-size:0.8rem; text-transform:uppercase; color:${c.role.includes('Prompt')?'#9d9cff':'#8bf2a3'};">${c.role}</strong>
                            <span style="font-size:0.75rem; font-family:monospace; color:var(--text-secondary);">${escapeHtml(c.spanName)}</span>
                        </div>
                        <div style="white-space:pre-wrap; word-break:break-word; font-family:monospace; opacity:0.9;">${escapeHtml(c.text)}</div>
                    </div>
                `).join('')}
            </details>`;
        }

        inspectorModalBody.innerHTML = `
            <div class="inspector-content">
                <div class="inspector-body">
                    ${inspectorSummaryHTML}

                    ${statsHTML}

                    ${insightsHTML}

                    ${spanTreeHTML}

                    <details class="inspector-section" style="margin-top: 24px; margin-bottom: 24px;">
                        ${sectionSummary('Execution Timeline', `${spansList.length} spans`)}
                        <div style="background: rgba(255,255,255,0.02); padding: 16px; border-radius: 8px; border: 1px solid var(--border-glass); max-height:400px; overflow-y:auto; overflow-x:hidden;">
                            ${timelineHTML}
                        </div>
                    </details>

                    ${thoughtHTML}

                    ${correlationHTML}

                    ${toolsHTML}

                    ${conversationHTML}

                    ${chatHTML}

                    <details class="inspector-section" style="margin-top:24px;">
                        ${sectionSummary('Raw Span Details', `${spansList.length} spans`)}
                        ${spanExplorerHTML}
                    </details>

                    <details style="margin-top:18px; background:rgba(0,0,0,0.35); border:1px solid var(--border-glass); border-radius:8px; padding:10px;">
                        <summary style="cursor:pointer; color:var(--text-secondary);">Raw Trace JSON</summary>
                        <pre style="margin-top:10px; max-height:420px; overflow:auto; font-size:0.78rem; line-height:1.35; background:rgba(0,0,0,0.42); border-radius:6px; padding:10px; border:1px solid var(--border-glass);">${escapeHtml(JSON.stringify(spanData, null, 2))}</pre>
                    </details>
                </div>
            </div>
        `;
        setupInspectorInteractions();
    }

    // Export Logic
    exportBtn.addEventListener('click', async () => {
        if(allTraces.length === 0) return alert("No traces to export.");
        const modal = document.getElementById('export-modal');
        const prog = document.getElementById('export-progress');
        const txt = document.getElementById('export-status-text');
        modal.classList.remove('hidden');
        
        let exportedPayload = [];
        
        for(let i=0; i<allTraces.length; i++) {
            prog.style.width = ((i / allTraces.length) * 100) + '%';
            txt.innerText = `Fetching spans for trace ${i+1} of ${allTraces.length}...`;
            
            try {
                const env = encodeURIComponent(envSelector.value || '');
                const traceId = allTraces[i].traceId;
                if (!traceId) continue;

                const res = await fetch(`/api/traces/${encodeURIComponent(traceId)}/spans?env=${env}`);
                if (!res.ok) continue;

                const spData = await res.json();
                exportedPayload.push({
                    summary: allTraces[i],
                    payload: spData
                });
            } catch(e) {}
        }
        
        prog.style.width = '100%';
        txt.innerText = "Done! Downloading JSON...";
        
        const blob = new Blob([JSON.stringify(exportedPayload, null, 2)], {type: "application/json"});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `wxo-telemetry-export-${new Date().getTime()}.json`;
        a.click();
        URL.revokeObjectURL(url);
        
        setTimeout(() => modal.classList.add('hidden'), 1000);
    });

    // Inspector modal close controls
    if (inspectorModalClose) {
        inspectorModalClose.addEventListener('click', closeInspectorModal);
    }
    if (inspectorModal) {
        inspectorModal.addEventListener('click', (e) => {
            if (e.target === inspectorModal) closeInspectorModal();
        });
    }
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && inspectorModal && !inspectorModal.classList.contains('hidden')) {
            closeInspectorModal();
        }
    });

    refreshBtn.addEventListener('click', loadTraces);
    envSelector.addEventListener('change', loadTraces);
    overviewStrip.addEventListener('click', (e) => {
        const trigger = e.target.closest('[data-overview-action="toggle-errors-only"]');
        if (!trigger) return;
        errorsOnlyToggle.checked = !errorsOnlyToggle.checked;
        filterAndRender();
        if (errorsOnlyToggle.checked) {
            enrichMissingTraceMetadata(true);
        }
    });
    conversationOnlyToggle.addEventListener('change', () => {
        filterAndRender();
        if (conversationOnlyToggle.checked) {
            enrichMissingTraceMetadata(true);
        }
    });
    toolsOnlyToggle.addEventListener('change', () => {
        filterAndRender();
        if (toolsOnlyToggle.checked) {
            enrichMissingTraceMetadata(true);
        }
    });
    errorsOnlyToggle.addEventListener('change', () => {
        filterAndRender();
        if (errorsOnlyToggle.checked) {
            enrichMissingTraceMetadata(true);
        }
    });
    excludeInfraToggle.addEventListener('change', () => {
        filterAndRender();
        if (excludeInfraToggle.checked) {
            enrichMissingTraceMetadata(true);
        }
    });
    manageSystemsBtn.addEventListener('click', () => {
        systemsStatusText.textContent = '';
        editSystemForm.style.display = 'none';
        systemForm.style.display = '';
        systemsModal.classList.remove('hidden');
        renderSystemsList();
    });
    closeSystemsBtn.addEventListener('click', () => {
        systemsModal.classList.add('hidden');
    });
    systemsModal.addEventListener('click', (e) => {
        if (e.target === systemsModal) systemsModal.classList.add('hidden');
    });

    if (cancelEditSystemBtn) {
        cancelEditSystemBtn.addEventListener('click', () => {
            editSystemForm.style.display = 'none';
            systemForm.style.display = '';
            systemsStatusText.textContent = '';
        });
    }

    if (editSystemForm) {
        editSystemForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            await editSystem(
                editSystemOriginalName.value,
                editSystemName.value.trim(),
                editSystemUrl.value.trim(),
                editSystemKey.value.trim()
            );
        });
    }

    systemForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        systemsStatusText.textContent = '';

        const payload = {
            name: newSystemName.value.trim(),
            url: newSystemUrl.value.trim(),
            key: newSystemKey.value.trim()
        };

        try {
            const res = await fetch('/api/environments', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(result.error || `Failed to add system (${res.status})`);

            systemsStatusText.textContent = `Added system: ${payload.name}`;
            newSystemName.value = '';
            newSystemUrl.value = '';
            newSystemKey.value = '';
            await loadEnvironments();
        } catch (err) {
            systemsStatusText.textContent = err.message;
        }
    });
    timeStartInput.addEventListener('change', loadTraces);
    timeEndInput.addEventListener('change', loadTraces);
    
    // Quick Preset Time Helpers
    document.querySelectorAll('.topbar-time-group button[data-mins]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const mins = parseInt(e.target.dataset.mins, 10);
            const now = new Date();
            const start = new Date(now.getTime() - mins * 60000);
            
            timeEndInput.value = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
            timeStartInput.value = new Date(start.getTime() - start.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
            
            loadTraces();
        });
    });

    // Live client-side agent filter
    agentFilter.addEventListener('input', filterAndRender);

    // Search clear button
    const searchClearBtn = document.getElementById('search-clear-btn');
    if (searchClearBtn) {
        const updateClearBtn = () => {
            searchClearBtn.style.display = agentFilter.value.length > 0 ? '' : 'none';
        };
        agentFilter.addEventListener('input', updateClearBtn);
        searchClearBtn.addEventListener('click', () => {
            agentFilter.value = '';
            updateClearBtn();
            filterAndRender();
        });
    }

    // Error Explorer collapse / expand toggle
    const errorExplorerPanelEl = document.getElementById('error-explorer-panel');
    const errorExplorerToggleBtn = document.getElementById('error-explorer-toggle');
    if (errorExplorerToggleBtn && errorExplorerPanelEl) {
        errorExplorerToggleBtn.addEventListener('click', () => {
            errorExplorerPanelEl.classList.toggle('collapsed');
        });
    }

    if (errorExplorerContent) {
        errorExplorerContent.addEventListener('click', (event) => {
            const chipRemoveTrigger = event.target.closest('[data-error-focus-remove]');
            if (chipRemoveTrigger) {
                event.preventDefault();
                const key = chipRemoveTrigger.dataset.errorFocusRemove || '';
                setErrorExplorerFocus({
                    agentName: key === 'agentName' ? '' : errorExplorerFocus.agentName,
                    spanName: key === 'spanName' ? '' : errorExplorerFocus.spanName,
                    message: key === 'message' ? '' : errorExplorerFocus.message
                });
                return;
            }

            const clearTrigger = event.target.closest('[data-error-filter-clear="true"]');
            if (clearTrigger) {
                event.preventDefault();
                clearErrorExplorerFocus();
                return;
            }

            const summaryFilterTrigger = event.target.closest('[data-error-filter-type]');
            if (summaryFilterTrigger) {
                event.preventDefault();
                const filterType = summaryFilterTrigger.dataset.errorFilterType || '';
                const filterValue = summaryFilterTrigger.dataset.errorFilterValue || '';
                if (filterType === 'agent') {
                    const isSame = errorExplorerFocus.agentName === filterValue && !errorExplorerFocus.spanName && !errorExplorerFocus.message;
                    setErrorExplorerFocus(isSame ? {} : { agentName: filterValue });
                } else if (filterType === 'span') {
                    const isSame = errorExplorerFocus.spanName === filterValue && !errorExplorerFocus.message;
                    setErrorExplorerFocus(isSame ? {} : { agentName: errorExplorerFocus.agentName, spanName: filterValue });
                }
                return;
            }

            const messageTrigger = event.target.closest('[data-error-message]');
            if (messageTrigger) {
                event.preventDefault();
                const message = messageTrigger.dataset.errorMessage || '';
                const isSame = errorExplorerFocus.message === message;
                setErrorExplorerFocus(isSame ? {} : { agentName: errorExplorerFocus.agentName, spanName: errorExplorerFocus.spanName, message });
                const nextVisible = getFilteredTraces()[0];
                if (nextVisible?.traceId) {
                    focusTraceById(nextVisible.traceId, { openInspector: false });
                }
                return;
            }

            const target = event.target.closest('.error-trace-link');
            if (!target) return;

            event.preventDefault();
            const traceId = target.dataset.traceId || '';
            focusTraceById(traceId);
        });
    }

    // Initial Load - start by bootstrapping configs
    loadEnvironments();
});
