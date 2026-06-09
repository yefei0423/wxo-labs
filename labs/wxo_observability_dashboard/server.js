const express = require('express');
const cors = require('cors');
const fs = require('fs');
const path = require('path');

/**
 * WxO Observability Dashboard backend.
 *
 * Responsibilities:
 * - discover configured Watsonx Orchestrate environments from .env files
 * - allow temporary in-memory environments to be added from the UI
 * - mint and cache IAM tokens per environment
 * - proxy trace summary and span export requests to the selected instance
 * - serve the static dashboard frontend
 */

const envMap = {};
const localEnvMap = {};

// Configuration bootstrap: prefer a local .env, then walk upward toward the repo root.
const envCandidates = [
    path.join(__dirname, '.env'),
    path.join(__dirname, '..', '.env'),
    path.join(__dirname, '..', '..', '.env'),
    path.join(__dirname, '..', '..', '..', '.env')
];
const envFile = {};
let loadedEnvPath = null;
for (const candidate of envCandidates) {
    if (fs.existsSync(candidate)) {
        loadedEnvPath = candidate;
        console.log(`📄 Loading .env from: ${candidate}`);
        const envConfig = fs.readFileSync(candidate, 'utf-8');
        envConfig.split('\n').forEach(line => {
            const match = line.match(/^([^#\s][^=]+)=(.*)$/);
            if (match) envFile[match[1].trim()] = match[2].trim();
        });
        break; // stop at first found
    }
}

// Discover every configured instance using the <PREFIX>_INSTANCE_URL naming convention.
Object.keys(envFile).forEach(key => {
    if (key.endsWith('_INSTANCE_URL')) {
        const prefix = key.replace('_INSTANCE_URL', '');
        const url = envFile[key];
        
        // Find matching API key (either exact prefix match or trial key fallback)
        let apiKey = envFile[`${prefix}_API_KEY`];
        
        // Special case fallback for WO_INSTANCE_URL -> WO_API_KEY -> WO_TRIAL_API_KEY
        if (!apiKey && prefix === 'WO') apiKey = envFile['WO_API_KEY'] || envFile['WO_TRIAL_API_KEY'];
        
        if (url && apiKey) {
            // Make name pretty: SYNC_TZ1 -> Sync Tz1
            const name = prefix.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            envMap[name] = { url, key: apiKey };
        }
    }
});

// IAM endpoint used to exchange an API key for a bearer token.
const TOKEN_URL = envFile.WO_MCSP_TOKEN_URL || "https://iam.platform.saas.ibm.com/siusermgr/api/1.0/apikeys/token";

if (Object.keys(envMap).length === 0) {
    const hint = loadedEnvPath ? loadedEnvPath : envCandidates.join(', ');
    console.error("❌ Error: No valid WxO Instances found. Checked: " + hint);
    process.exit(1);
}

const app = express();
app.use(cors());
app.use(express.json());

function parseRetryAfterMs(headerValue) {
    if (!headerValue) return 0;

    const numericSeconds = Number(headerValue);
    if (Number.isFinite(numericSeconds) && numericSeconds > 0) {
        return numericSeconds * 1000;
    }

    const asDate = Date.parse(headerValue);
    if (Number.isNaN(asDate)) return 0;
    return Math.max(0, asDate - Date.now());
}

// Lightweight request tracing for debugging UI "Network error" issues.
let requestCounter = 0;
app.use((req, res, next) => {
    const reqId = `${Date.now()}-${++requestCounter}`;
    req._reqId = reqId;
    const start = Date.now();
    console.log(`➡️ [${reqId}] ${req.method} ${req.originalUrl}`);
    res.on('finish', () => {
        console.log(`⬅️ [${reqId}] ${res.statusCode} ${Date.now() - start}ms`);
    });
    next();
});

const publicDir = path.join(__dirname, 'public');
app.use(express.static(publicDir));

app.get('/', (req, res) => {
    res.sendFile(path.join(publicDir, 'index.html'));
});

// In-memory token cache keyed by display environment name.
const tokenCache = {}; // envName -> { token, expires }

/**
 * Returns the first configured environment name, which acts as the UI default.
 */
function getDefaultEnvironment() {
    return Object.keys({ ...envMap, ...localEnvMap })[0] || null;
}

/**
 * Resolves a requested environment name to a known environment, falling back to the default.
 */
function resolveEnvironment(requestedEnv) {
    const merged = { ...envMap, ...localEnvMap };
    if (requestedEnv && merged[requestedEnv]) return requestedEnv;
    return getDefaultEnvironment();
}

/**
 * Looks up the URL/API key pair for a display environment name.
 */
function getEnvironmentEntry(envName) {
    const merged = { ...envMap, ...localEnvMap };
    return merged[envName] || null;
}

/**
 * Normalizes UI-provided environment names so they are safe to use as object keys.
 */
function normalizeEnvironmentName(name) {
    return String(name || '')
        .trim()
        .replace(/\s+/g, ' ')
        .replace(/[\r\n\t]+/g, '');
}

/**
 * Returns environment metadata for the picker and systems management UI.
 */
function getEnvironmentDetails() {
    const staticEntries = Object.entries(envMap).map(([name, cfg]) => ({
        name,
        url: cfg.url,
        source: 'env'
    }));
    const localEntries = Object.entries(localEnvMap).map(([name, cfg]) => ({
        name,
        url: cfg.url,
        source: 'local'
    }));

    return [...staticEntries, ...localEntries].sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * Parses user-supplied date strings into normalized ISO timestamps.
 */
function parseIsoDate(value) {
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return null;
    return dt.toISOString();
}

/**
 * Returns a valid bearer token for the target environment.
 *
 * Tokens are cached in memory until shortly before the reported expiration time
 * to reduce IAM traffic during active dashboard sessions.
 */
async function getAuthToken(envName) {
    const creds = getEnvironmentEntry(envName);
    if (!creds) throw new Error("Unknown environment: " + envName);
    
    if (tokenCache[envName] && Date.now() < tokenCache[envName].expires) {
        return tokenCache[envName].token;
    }
    console.log(`🔑 Refreshing IAM token for ${envName}...`);
    try {
        const res = await fetch(TOKEN_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ apikey: creds.key })
        });
        if (!res.ok) throw new Error(`Token fetch failed: ${res.status}`);
        const data = await res.json();
        const token = data.token || data.access_token;
        if (!token) throw new Error('Token response missing token value');

        const expiresIn = Number(data.expires_in);
        const ttlMs = Number.isFinite(expiresIn) && expiresIn > 60 ? (expiresIn - 60) * 1000 : 3300 * 1000;

        tokenCache[envName] = {
            token,
            expires: Date.now() + ttlMs
        };
        return tokenCache[envName].token;
    } catch (e) {
        console.error("Auth Error", e);
        throw e;
    }
}

// Provide environment list to UI.
app.get('/api/environments', (req, res) => {
    const names = getEnvironmentDetails().map((entry) => entry.name);
    res.json(names);
});

// Provide environment metadata, including source and URL, to the systems modal.
app.get('/api/environments/details', (req, res) => {
    res.json({ environments: getEnvironmentDetails() });
});

// Expose backend state used when the browser reports a generic network failure.
app.get('/api/debug/status', (req, res) => {
    const environments = getEnvironmentDetails();
    const activeEnv = resolveEnvironment(req.query.env);
    const activeCfg = activeEnv ? getEnvironmentEntry(activeEnv) : null;

    res.json({
        ok: true,
        serverTime: new Date().toISOString(),
        uptimeSec: Math.round(process.uptime()),
        requestId: req._reqId,
        loadedEnvPath,
        tokenUrl: TOKEN_URL,
        environmentCount: environments.length,
        activeEnvironment: activeEnv,
        activeInstanceUrl: activeCfg?.url || null,
        hasCachedToken: Boolean(activeEnv && tokenCache[activeEnv] && Date.now() < tokenCache[activeEnv].expires)
    });
});

// Add a session-scoped environment that exists only for the current server process.
app.post('/api/environments', (req, res) => {
    const name = normalizeEnvironmentName(req.body?.name);
    const url = String(req.body?.url || '').trim();
    const key = String(req.body?.key || '').trim();

    if (!name || !url || !key) {
        return res.status(400).json({ error: 'name, url, and key are required' });
    }

    if (!/^https?:\/\//i.test(url)) {
        return res.status(400).json({ error: 'url must start with http:// or https://' });
    }

    if (envMap[name] || localEnvMap[name]) {
        return res.status(409).json({ error: `System already exists: ${name}` });
    }

    localEnvMap[name] = { url, key };
    res.status(201).json({ ok: true, environment: { name, url, source: 'local' } });
});

// Update a session-scoped environment. .env-backed entries remain read-only.
app.put('/api/environments/:name', (req, res) => {
    const oldName = normalizeEnvironmentName(decodeURIComponent(req.params.name));
    if (!oldName) return res.status(400).json({ error: 'Missing system name' });

    if (envMap[oldName]) {
        return res.status(403).json({ error: 'Cannot edit systems loaded from .env' });
    }
    if (!localEnvMap[oldName]) {
        return res.status(404).json({ error: `System not found: ${oldName}` });
    }

    const newName = normalizeEnvironmentName(req.body?.name || oldName);
    const url = String(req.body?.url || localEnvMap[oldName].url).trim();
    const key = String(req.body?.key || '').trim();

    if (!newName || !url) {
        return res.status(400).json({ error: 'name and url are required' });
    }
    if (!/^https?:\/\//i.test(url)) {
        return res.status(400).json({ error: 'url must start with http:// or https://' });
    }
    if (newName !== oldName && (envMap[newName] || localEnvMap[newName])) {
        return res.status(409).json({ error: `System already exists: ${newName}` });
    }

    // Rename key if name changed
    delete localEnvMap[oldName];
    delete tokenCache[oldName];
    localEnvMap[newName] = { url, key: key || localEnvMap[oldName]?.key || '' };
    res.json({ ok: true, environment: { name: newName, url, source: 'local' } });
});

// Remove a session-scoped environment and any cached token for it.
app.delete('/api/environments/:name', (req, res) => {
    const name = normalizeEnvironmentName(decodeURIComponent(req.params.name));
    if (!name) return res.status(400).json({ error: 'Missing system name' });

    if (envMap[name]) {
        return res.status(403).json({ error: 'Cannot remove systems loaded from .env' });
    }

    if (!localEnvMap[name]) {
        return res.status(404).json({ error: `System not found: ${name}` });
    }

    delete localEnvMap[name];
    delete tokenCache[name];
    res.json({ ok: true, removed: name });
});

// Search for trace summaries inside a requested date range or lookback window.
app.get('/api/traces', async (req, res) => {
    try {
        const envName = resolveEnvironment(req.query.env);
        if (!envName) {
            return res.status(503).json({ error: 'No environment configured' });
        }

        const token = await getAuthToken(envName);
        const envConfig = getEnvironmentEntry(envName);
        if (!envConfig) {
            return res.status(404).json({ error: `Unknown environment: ${envName}` });
        }

        const INSTANCE_URL = envConfig.url.replace(/\/$/, '');
        
        let startIso, endIso;
        const hasStart = typeof req.query.start_time === 'string' && req.query.start_time.length > 0;
        const hasEnd = typeof req.query.end_time === 'string' && req.query.end_time.length > 0;

        if (hasStart || hasEnd) {
            if (!(hasStart && hasEnd)) {
                return res.status(400).json({ error: 'Both start_time and end_time are required when filtering by date' });
            }

            startIso = parseIsoDate(req.query.start_time);
            endIso = parseIsoDate(req.query.end_time);
            if (!startIso || !endIso) {
                return res.status(400).json({ error: 'Invalid date range values' });
            }

            if (new Date(startIso).getTime() > new Date(endIso).getTime()) {
                return res.status(400).json({ error: 'start_time must be before end_time' });
            }
        } else {
            const mins = parseInt(req.query.mins || '60', 10);
            const now = new Date();
            startIso = new Date(now.getTime() - mins * 60000).toISOString();
            endIso = now.toISOString();
        }

        const rawLimit = parseInt(req.query.limit, 10);
        const pageSize = Number.isFinite(rawLimit) && rawLimit > 0 ? Math.min(rawLimit, 200) : 50;
        
        console.log(`🔍 Searching traces from ${startIso} to ${endIso}`);

        const searchRes = await fetch(`${INSTANCE_URL}/v1/traces/search`, {
            method: "POST",
            headers: { 
                "Authorization": `Bearer ${token}`, 
                "Content-Type": "application/json" 
            },
            body: JSON.stringify({ 
                filters: { 
                    start_time: startIso,
                    end_time: endIso
                },
                page_size: pageSize
            })
        });

        if (!searchRes.ok) {
            const bodyText = await searchRes.text();
            const retryAfter = searchRes.headers.get('retry-after') || '';
            const retryAfterMs = parseRetryAfterMs(retryAfter);
            console.error(`❌ [${req._reqId}] Trace search failed (${searchRes.status}) env=${envName} body=${bodyText.slice(0, 800)}`);
            if (retryAfter) {
                res.set('Retry-After', retryAfter);
            }
            return res.status(searchRes.status).json({
                error: `Trace search failed (${searchRes.status})`,
                requestId: req._reqId,
                envName,
                instanceUrl: INSTANCE_URL,
                retryAfter,
                retryAfterMs,
                details: bodyText
            });
        }

        const searchData = await searchRes.json();
                // Normalize the response to a stable newest-first order for the UI.
          const summaries = Array.isArray(searchData.traceSummaries) ? searchData.traceSummaries : [];
          const sortedTraces = summaries.sort((a,b) => {
           return new Date(b.startTime).getTime() - new Date(a.startTime).getTime(); 
        });
        res.json({ summaries: sortedTraces });
    } catch (err) {
        console.error(`❌ [${req._reqId}] /api/traces error`, err);
        res.status(500).json({ error: err.message, requestId: req._reqId });
    }
});

// Fetch the full OTLP span payload for a specific trace.
app.get('/api/traces/:traceId/spans', async (req, res) => {
    try {
        const envName = resolveEnvironment(req.query.env);
        if (!envName) {
            return res.status(503).json({ error: 'No environment configured' });
        }

        const token = await getAuthToken(envName);
        const envConfig = getEnvironmentEntry(envName);
        if (!envConfig) {
            return res.status(404).json({ error: `Unknown environment: ${envName}` });
        }

        const INSTANCE_URL = envConfig.url.replace(/\/$/, '');
        const { traceId } = req.params;
        
        const exportRes = await fetch(`${INSTANCE_URL}/v1/traces/${traceId}/spans`, {
            method: "GET",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Accept": "application/json"
            }
        });

        if (!exportRes.ok) {
            const bodyText = await exportRes.text();
            console.error(`❌ [${req._reqId}] Trace span export failed (${exportRes.status}) trace=${traceId} env=${envName} body=${bodyText.slice(0, 800)}`);
            return res.status(exportRes.status).json({
                error: `Trace span export failed (${exportRes.status})`,
                requestId: req._reqId,
                envName,
                traceId,
                instanceUrl: INSTANCE_URL,
                details: bodyText
            });
        }

        const traceData = await exportRes.json();
        res.json(traceData);
    } catch (err) {
        console.error(`❌ [${req._reqId}] /api/traces/:traceId/spans error`, err);
        res.status(500).json({ error: err.message, requestId: req._reqId });
    }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`🚀 WxO Observability Dashboard running at http://localhost:${PORT}`);
});
