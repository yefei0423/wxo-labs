const fs = require('fs');
const path = require('path');

const envPath = path.join(__dirname, '..', '..', '..', '.env');
const envFile = {};
if (fs.existsSync(envPath)) {
    const envConfig = fs.readFileSync(envPath, 'utf-8');
    envConfig.split('\n').forEach(line => {
        const match = line.match(/^([^#\s][^=]+)=(.*)$/);
        if (match) envFile[match[1].trim()] = match[2].trim();
    });
}

const INSTANCE_URL = envFile.WO_INSTANCE_URL;
const API_KEY = envFile.WO_API_KEY || envFile.WO_TRIAL_API_KEY;
const TOKEN_URL = envFile.WO_MCSP_TOKEN_URL || "https://iam.platform.saas.ibm.com/siusermgr/api/1.0/apikeys/token";

async function run() {
    console.log("Fetching token...");
    const tRes = await fetch(TOKEN_URL, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({apikey: API_KEY})});
    const tData = await tRes.json();
    const token = tData.access_token || tData.token;

    const end = new Date().toISOString();
    const start = new Date(Date.now() - 24 * 3600000).toISOString();
    console.log("Searching traces...");
    const sRes = await fetch(`${INSTANCE_URL}/v1/traces/search`, {
        method: "POST", headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ filters: { start_time: start, end_time: end }, page_size: 20 })
    });
    const sData = await sRes.json();
    const summaries = sData.traceSummaries || sData.traces || sData.data || sData.items || [];
    console.log(`Found ${summaries.length} trace summaries`);

    for (const summary of summaries) {
        const traceId = summary.traceId;
        if (!traceId) continue;
        console.log("Inspecting trace: " + traceId);

        const spansRes = await fetch(`${INSTANCE_URL}/v1/traces/${traceId}/spans`, {
            method: "GET", headers: { "Authorization": `Bearer ${token}` }
        });
        if (!spansRes.ok) continue;

        const traceData = await spansRes.json();
        const resourceSpans = traceData.traceData?.resourceSpans || [];
        const interesting = [];
        let hasConversation = false;

        resourceSpans.forEach(rs => {
            (rs.scopeSpans || []).forEach(ss => {
                (ss.spans || []).forEach(span => {
                    (span.attributes || []).forEach(attr => {
                        if (/^gen_ai\.(prompt|completion)(\.\d+)?\.content$/.test(attr.key) || attr.key === 'traceloop.entity.input' || attr.key === 'traceloop.entity.output') {
                            hasConversation = true;
                        }
                        if (/agent|assistant|workflow|skill|entity\.name|thread\.id|session\.id|traceloop|gen_ai/i.test(attr.key)) {
                            const rawValue = attr.value?.stringValue || attr.value?.intValue || attr.value?.boolValue || '';
                            const safeValue = /^(traceloop\.entity\.(input|output)|gen_ai\.(prompt|completion)(\.\d+)?\.content)$/i.test(attr.key)
                                ? `<present:${String(rawValue).length}>`
                                : String(rawValue).slice(0, 120);
                            interesting.push({
                                span: span.name,
                                key: attr.key,
                                value: safeValue
                            });
                        }
                    });
                });
            });
        });

        if (hasConversation) {
            console.log(JSON.stringify({
                traceId,
                summaryAgent: summary.agentName || summary.agent_name || summary['agent.name'] || summary.agentNames || null,
                rootSpanName: summary.rootSpanName || summary.name || null,
                interesting: interesting.slice(0, 40)
            }, null, 2));
            return;
        }
    }

    console.log('No conversation-like trace found in the current window');
}
run();
