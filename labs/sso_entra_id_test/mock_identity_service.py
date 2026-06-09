#!/usr/bin/env python3
# ==============================================================================
# Mock Identity Service: SSO Identity Probe Endpoint
# ==============================================================================
# **Author:** Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# *No bug too small, no syntax too weird.*
# ==============================================================================

from flask import Flask, request, jsonify
import json
from datetime import datetime

app = Flask(__name__)

@app.route('/whoami', methods=['GET'])
def whoami():
    """
    Mock endpoint that returns user identity information.
    This simulates a downstream service receiving SSO identity from WxO.
    """
    # Capture all headers
    headers_dict = dict(request.headers)
    
    # Extract common identity headers
    username = (
        headers_dict.get('X-User-Name') or 
        headers_dict.get('X-Forwarded-User') or
        headers_dict.get('Remote-User') or
        'unknown'
    )
    
    # Extract authorization header
    auth_header = headers_dict.get('Authorization', 'No Authorization header')
    
    # Build response
    response_data = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'username': username,
        'roles': headers_dict.get('X-User-Roles', '').split(',') if headers_dict.get('X-User-Roles') else [],
        'raw_headers': headers_dict,
        'authorization': auth_header,
        'message': 'Identity probe successful'
    }
    
    # Log to console for debugging
    print("\n" + "="*80)
    print(f"🔍 Identity Probe Request Received at {response_data['timestamp']}")
    print("="*80)
    print(f"👤 Username: {username}")
    print(f"🔑 Authorization: {auth_header[:50]}..." if len(auth_header) > 50 else f"🔑 Authorization: {auth_header}")
    print(f"📋 All Headers:")
    for key, value in headers_dict.items():
        print(f"   {key}: {value}")
    print("="*80 + "\n")
    
    return jsonify(response_data), 200

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'SSO Identity Probe Mock'}), 200

@app.route('/', methods=['GET'])
def root():
    """Root endpoint with service info"""
    return jsonify({
        'service': 'SSO Identity Probe Mock Service',
        'endpoints': {
            '/whoami': 'GET - Returns user identity information',
            '/health': 'GET - Health check'
        },
        'status': 'running'
    }), 200

if __name__ == '__main__':
    print("\n" + "="*80)
    print("🚀 Starting SSO Identity Probe Mock Service")
    print("="*80)
    print("📍 Endpoints:")
    print("   GET /whoami  - Identity probe endpoint")
    print("   GET /health  - Health check")
    print("   GET /        - Service info")
    print("="*80)
    print("⚠️  Remember to expose this with ngrok on port 5000")
    print("   Run: ngrok http 5000")
    print("="*80 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)

# Made by Research | 7 1/2 Floor
