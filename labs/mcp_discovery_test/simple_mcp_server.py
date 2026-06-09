# ---
# **Author**: Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# *No bug too small, no syntax too weird.*
# ---

import sys
import json

# Minimal MCP Server for reproduction
# This script simulates an MCP server that responds to 'list_tools'

def main():
    for line in sys.stdin:
        try:
            request = json.loads(line)
            method = request.get("method")
            msg_id = request.get("id")

            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "repro-server", "version": "0.1.0"}
                    }
                }
                print(json.dumps(response), flush=True)

            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "tools": [
                            {
                                "name": "get_repro_data",
                                "description": "Returns a success message to verify MCP execution",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {"type": "string", "description": "The search query"}
                                    },
                                    "required": ["query"]
                                }
                            }
                        ]
                    }
                }
                print(json.dumps(response), flush=True)

            elif method == "tools/call":
                params = request.get("params", {})
                arguments = params.get("arguments", {})
                query = arguments.get("query", "none")
                
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"✅ MCP Server Received Query: '{query}'. Discovery and Execution are WORKING!"
                            }
                        ]
                    }
                }
                print(json.dumps(response), flush=True)
            
            # Note: We are simulating the protocol basics to see if Orchestrate calls them.
        except Exception as e:
            pass

if __name__ == "__main__":
    main()
