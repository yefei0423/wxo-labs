"""
Premium Live Log Dashboard v3.1 (Name-Aware)

Adds Agent Name extraction and enhanced Filtering.

**Author:** Markus van Kempen | mvk@ca.ibm.com
"""

from flask import Flask, request, jsonify, render_template_string
import sqlite3
import os
import json

app = Flask(__name__)
DB_FILE = "conversations.db"

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WxO Intelligence Vault</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #020617;
            --card: #0f172a;
            --accent: #38bdf8;
            --text: #f1f5f9;
            --user-color: #7dd3fc;
            --bot-color: #c084fc;
        }
        body { background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; margin: 0; display: flex; height: 100vh; overflow: hidden; }
        .sidebar { width: 320px; background: #070a1a; border-right: 1px solid rgba(255,255,255,0.05); padding: 2rem; overflow-y: auto; }
        .main { flex: 1; padding: 2rem; overflow-y: auto; }
        h1 { font-weight: 800; font-size: 1.5rem; color: var(--accent); margin-bottom: 2rem; }
        .filter-group { margin-bottom: 1.5rem; }
        .filter-label { font-size: 0.65rem; font-weight: 800; opacity: 0.5; text-transform: uppercase; margin-bottom: 0.5rem; display: block; letter-spacing: 0.05em; }
        select { width: 100%; background: var(--card); color: var(--text); border: 1px solid rgba(255,255,255,0.1); padding: 10px; border-radius: 8px; font-size: 0.8rem; outline: none; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }
        .btn { background: var(--card); color: var(--text); border: 1px solid rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 0.75rem; font-weight: 600; }
        .turn-card { background: var(--card); border-radius: 12px; padding: 1.2rem; margin-bottom: 1rem; border: 1px solid rgba(255,255,255,0.05); }
        .meta { font-size: 0.65rem; opacity: 0.5; margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center; }
        .msg { position: relative; padding-left: 1.2rem; margin-bottom: 0.8rem; border-left: 2px solid transparent; }
        .user { border-left-color: var(--user-color); }
        .bot { border-left-color: var(--bot-color); }
        .label { font-size: 0.6rem; font-weight: 800; opacity: 0.4; display: block; }
        .content { font-size: 0.95rem; line-height: 1.5; }
        .thread-pill { background: rgba(56, 189, 248, 0.1); color: var(--accent); padding: 4px 10px; border-radius: 6px; font-size: 0.65rem; font-weight: 600; }
    </style>
</head>
<body>
    <div class="sidebar">
        <h1>🔍 Intelligence</h1>
        <div class="filter-group">
            <span class="filter-label">Keyword Search</span>
            <input type="text" id="filter-search" placeholder="Search logs..." onkeyup="applyFilters()">
        </div>

        <div class="filter-group">
            <span class="filter-label">Agent Filter</span>
            <select id="filter-agent" onchange="applyFilters()"><option value="all">All Agents</option></select>
        </div>
        <div class="filter-group">
            <span class="filter-label">Conversation Thread</span>
            <select id="filter-thread" onchange="applyFilters()"><option value="all">All Threads</option></select>
        </div>

        <button class="btn" style="width:100%; margin-top:1rem;" onclick="clearFilters()">🧹 CLEAR FILTERS</button>
        <div style="margin-top: 4rem; opacity: 0.3; font-size: 0.65rem; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 1rem;">
            Markus van Kempen | Floor 7½<br>No bug too small.
        </div>
    </div>
    <div class="main">
        <div class="header">
            <div style="font-size: 1.2rem; font-weight: 800;">Secure Log Vault</div>
            <button class="btn" onclick="fetchLogs()">🔄 REFRESH</button>
        </div>
        <div id="log-container"></div>
    </div>
    <script>
        let allLogs = [];
        async function fetchLogs() {
            try {
                const response = await fetch('/view');
                const rawLogs = await response.json();
                const merged = [];
                for (let i = 0; i < rawLogs.length; i++) {
                    const current = rawLogs[i];
                    if (current[5] === 'N/A' && i + 1 < rawLogs.length && rawLogs[i+1][6] === '[PRE-INVOKE]') {
                        merged.push({ id: current[0], ts: current[1], agent: current[2], name: current[3], thread: current[4], user: rawLogs[i+1][5], bot: current[6] });
                        i++;
                    } else {
                        merged.push({ id: current[0], ts: current[1], agent: current[2], name: current[3], thread: current[4], user: current[5], bot: current[6] });
                    }
                }
                allLogs = merged;
                updateFilterOptions();
                applyFilters();
            } catch (err) { console.error(err); }
        }
        function updateFilterOptions() {
            const agents = [...new Set(allLogs.map(l => `${l.name} (${l.agent.substring(0,6)})`))];
            const threads = [...new Set(allLogs.map(l => l.thread))];
            const agentSel = document.getElementById('filter-agent');
            const threadSel = document.getElementById('filter-thread');
            const curA = agentSel.value; const curT = threadSel.value;
            agentSel.innerHTML = '<option value="all">All Agents</option>' + agents.map(a => `<option value="${a}">${a}</option>`).join('');
            threadSel.innerHTML = '<option value="all">All Threads</option>' + threads.map(t => `<option value="${t}">${t.substring(0,12)}...</option>`).join('');
            agentSel.value = curA; threadSel.value = curT;
        }
        function applyFilters() {
            const agentFilter = document.getElementById('filter-agent').value;
            const threadFilter = document.getElementById('filter-thread').value;
            const searchFilter = document.getElementById('filter-search').value.toLowerCase();

            const filtered = allLogs.filter(log => {
                const fullAgent = `${log.name} (${log.agent.substring(0,6)})`;
                const textMatch = !searchFilter || 
                                 log.user.toLowerCase().includes(searchFilter) || 
                                 log.bot.toLowerCase().includes(searchFilter);
                                 
                return (agentFilter === 'all' || fullAgent === agentFilter) && 
                       (threadFilter === 'all' || log.thread === threadFilter) &&
                       textMatch;
            });
            renderLogs(filtered);
        }

        function clearFilters() {
            document.getElementById('filter-agent').value = 'all';
            document.getElementById('filter-thread').value = 'all';
            document.getElementById('filter-search').value = '';
            renderLogs(allLogs);
        }
        function renderLogs(logs) {
            document.getElementById('log-container').innerHTML = logs.map(log => `
                <div class="turn-card">
                    <div class="meta">
                        <span>🕒 ${log.ts} • <b>${log.name}</b></span>
                        <span class="thread-pill">THREAD: ${log.thread.substring(0,8)}</span>
                    </div>
                    ${log.user !== 'N/A' ? `<div class="msg user"><span class="label">USER</span><div class="content">${log.user}</div></div>` : ''}
                    ${log.bot !== '[PRE-INVOKE]' ? `<div class="msg bot"><span class="label">ASSISTANT</span><div class="content">${log.bot}</div></div>` : ''}
                </div>
            `).join('');
        }
        setInterval(fetchLogs, 5000);
        fetchLogs();
    </script>
</body>
</html>
"""

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Migration: Add agent_name column
    try:
        c.execute("SELECT agent_name FROM logs LIMIT 1")
    except:
        c.execute("DROP TABLE IF EXISTS logs")
        c.execute('''CREATE TABLE logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      timestamp TEXT, 
                      agent_id TEXT, 
                      agent_name TEXT,
                      thread_id TEXT,
                      user_input TEXT, 
                      assistant_output TEXT,
                      raw_payload TEXT)''')
    conn.commit()
    conn.close()

@app.route('/')
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route('/log', methods=['POST'])
def log_conversation():
    data = request.json
    context = data.get('context', {})
    agent_id = data.get('agent_id', 'Unknown')
    
    # 🕵️‍♂️ Smart Agent Resolver
    # Mapping known technical IDs to friendly names
    AGENT_MAP = {
        "f807329a-1e36-4711-9555-08861a13d1a6": "Conversation Logger Agent",
        "travel_agent": "Travel Assistant",
        "it_support": "IT Support Pro"
    }
    
    agent_name = context.get('agent_name') or AGENT_MAP.get(agent_id) or f"Agent-{agent_id[:8]}"
    thread_id = context.get('thread_id') or context.get('conversation_id') or "T-" + str(agent_id)[-4:]
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO logs (timestamp, agent_id, agent_name, thread_id, user_input, assistant_output, raw_payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (data.get('timestamp'), agent_id, agent_name, thread_id, data.get('user_input'), data.get('assistant_output'), json.dumps(data)))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"}), 200

@app.route('/view', methods=['GET'])
def view_logs():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, timestamp, agent_id, agent_name, thread_id, user_input, assistant_output FROM logs ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return jsonify(rows)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5002)
