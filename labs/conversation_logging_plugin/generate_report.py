"""
Premium Log Visualization Generator

Reads the local SQLite conversation vault and generates a modern, responsive 
HTML dashboard for log analysis.

**Author:** Markus van Kempen | mvk@ca.ibm.com  
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
*No bug too small, no syntax too weird.*
"""
import sqlite3
import os
from datetime import datetime

# Design tokens (Aesthetic: Dark Modern Premium)
CSS = """
:root {
    --bg: #0f172a;
    --card: #1e293b;
    --text: #f8fafc;
    --accent: #38bdf8;
    --user: #7dd3fc;
    --bot: #c084fc;
}
body { 
    background: var(--bg); 
    color: var(--text); 
    font-family: 'Inter', system-ui, sans-serif; 
    padding: 2rem;
    margin: 0;
}
.container { max-width: 1000px; margin: 0 auto; }
h1 { font-weight: 800; font-size: 2.5rem; margin-bottom: 0.5rem; color: var(--accent); }
.subtitle { opacity: 0.7; margin-bottom: 2rem; }
.turn-card { 
    background: var(--card); 
    border-radius: 12px; 
    padding: 1.5rem; 
    margin-bottom: 1.5rem; 
    border: 1px solid rgba(255,255,255,0.1);
    box-shadow: 0 10px 15px -3px rgba(0,0,0,0.3);
    transition: transform 0.2s;
}
.turn-card:hover { transform: translateY(-2px); border-color: var(--accent); }
.meta { font-size: 0.8rem; opacity: 0.5; margin-bottom: 1rem; display: flex; justify-content: space-between; }
.message { margin-bottom: 1rem; line-height: 1.6; }
.label { font-weight: 700; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.05em; margin-bottom: 0.4rem; display: block; }
.user-msg { color: var(--user); border-left: 3px solid var(--user); padding-left: 1rem; }
.bot-msg { color: var(--bot); border-left: 3px solid var(--bot); padding-left: 1rem; }
.badge { background: rgba(56, 189, 248, 0.2); color: var(--accent); padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; }
"""

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>WxO Private Log Viewer</title>
    <style>{css}</style>
</head>
<body>
    <div class="container">
        <h1>🕵️‍♂️ Conversation Vault</h1>
        <p class="subtitle">Secure server-side interaction logs for Watsonx Orchestrate</p>
        
        {content}
    </div>
</body>
</html>
"""

def generate_report():
    if not os.path.exists("conversations.db"):
        print("❌ Database not found. Run a test first.")
        return

    conn = sqlite3.connect("conversations.db")
    c = conn.cursor()
    c.execute("SELECT timestamp, agent_id, user_input, assistant_output FROM logs ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()

    cards = []
    for row in rows:
        ts, agent_id, user, bot = row
        card = f'''
        <div class="turn-card">
            <div class="meta">
                <span>🕒 {ts}</span>
                <span class="badge">AGENT: {agent_id}</span>
            </div>
            <div class="message user-msg">
                <span class="label">User Input</span>
                {user}
            </div>
            <div class="message bot-msg">
                <span class="label">Assistant Response</span>
                {bot}
            </div>
        </div>
        '''
        cards.append(card)

    final_html = HTML_TEMPLATE.format(css=CSS, content="".join(cards))
    
    with open("log_report.html", "w") as f:
        f.write(final_html)
    
    print(f"✅ Report generated successfully: {os.path.abspath('log_report.html')}")

if __name__ == "__main__":
    generate_report()
