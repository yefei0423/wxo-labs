# 🚀 Quick Start Guide: SSO E2E Test

This guide will help you run the complete end-to-end test for Microsoft Entra ID SSO integration with Watsonx Orchestrate.

---

## 📋 Prerequisites

- Python 3.x installed
- ngrok installed ([download here](https://ngrok.com/download))
- Access to Microsoft Entra ID admin portal
- WxO credentials configured in `../../.env`

---

## 🎯 Quick Test Options

### Option A: Test with Existing WatsonX Connection (Easiest)

If you already have connections like Box, Salesforce, or ServiceNow configured:

```bash
cd sso_entra_id_test
./run_sso_with_wxo_connection.sh
```

This will:
1. List all your available connections
2. Let you select which one to test
3. Create a test agent automatically
4. Verify SSO identity propagation

**No mock service or ngrok needed!**

---

### Option B: Test with Mock Service (3 Steps)

If you want to test with a custom mock endpoint:

#### Step 1: Setup Mock Service

```bash
cd sso_entra_id_test
./setup_mock_service.sh
```

### Step 2: Start Services (2 Terminals)

**Terminal 1 - Mock Service:**
```bash
python3 mock_identity_service.py
```

**Terminal 2 - ngrok:**
```bash
ngrok http 5000
```

Copy the ngrok URL (e.g., `https://abc123.ngrok-free.app`)

### Step 3: Run E2E Test

```bash
./run_sso_e2e_test.sh https://YOUR-NGROK-URL.ngrok-free.app
```

---

## 🔍 What Happens During the Test?

1. **Connection Bridge Created**: Creates `entra-id-sso-app` connection in WxO
2. **Tool Imported**: Imports the SSO Identity Probe tool with SAML authentication
3. **Agent Deployed**: Deploys the SSO Verifier Agent
4. **Chat Test**: Attempts to chat with the agent (triggers SSO flow)

---

## 📊 Expected Results

### ✅ Success Indicators

- Connection bridge created successfully
- Tool imported with SSO binding
- Agent deployed and available
- Chat triggers SSO login prompt OR shows active session

### ❌ Troubleshooting

**Issue**: `ngrok not found`
- **Solution**: Install ngrok: `brew install ngrok` (macOS) or download from ngrok.com

**Issue**: `Flask not installed`
- **Solution**: Run `pip3 install -r requirements.txt`

**Issue**: `Connection refused`
- **Solution**: Ensure mock service is running on port 5000

**Issue**: `No SSO prompt detected`
- **Solution**: You need to configure the SAML metadata in Entra ID first (see Full Setup below)

---

## 🔧 Full Setup (For First-Time Configuration)

### 1. Get Your SAML Endpoints

```bash
python3 find_saml_endpoints.py
```

This outputs:
- **Entity ID**: Your WxO SAML metadata URL
- **ACS URL**: Your WxO assertion consumer service URL

### 2. Configure Microsoft Entra ID

1. Go to [Microsoft Entra Admin Center](https://entra.microsoft.com)
2. Navigate to: **Enterprise Applications** → **New Application** → **Create your own**
3. Select: **Non-gallery application**
4. Configure **Single Sign-On**:
   - Method: **SAML**
   - Enter the **Entity ID** and **ACS URL** from Step 1
5. Download the **Federation Metadata XML**

### 3. Link Entra ID to WxO Connection

```bash
orchestrate connections configure \
  -a entra-id-sso-app \
  -k oauth_auth_code_flow \
  --sso True \
  -e metadata_url=YOUR_ENTRA_METADATA_XML_URL
```

### 4. Test the Integration

```bash
orchestrate chat ask -n sso_identity_verifier_agent "Who am I?"
```

---

## 📁 File Reference

| File | Purpose |
|------|---------|
| `mock_identity_service.py` | Mock downstream service that receives SSO identity |
| `setup_mock_service.sh` | Installs dependencies and provides setup instructions |
| `run_sso_e2e_test.sh` | Main E2E test runner |
| `find_saml_endpoints.py` | Discovers your WxO SAML endpoints |
| `sso_identity_probe.yaml` | OpenAPI spec with SAML authentication |
| `sso_verifier_agent.yaml` | Agent that tests identity propagation |

---

## 🎓 Understanding the Flow

```
User → WxO Agent → SSO Tool → Entra ID (SAML) → WxO Connection → Mock Service
                                    ↓
                            Identity Propagated
```

1. User asks agent "Who am I?"
2. Agent calls the Identity Probe tool
3. Tool requires SAML authentication
4. WxO redirects to Entra ID for login
5. Entra ID returns SAML assertion
6. WxO forwards identity to mock service
7. Mock service displays received identity

---

## 💡 Tips

- Keep the mock service running during tests
- Check mock service logs to see received headers
- Use `orchestrate connections list` to verify connection status
- Use `orchestrate tools list` to verify tool import
- Use `orchestrate agents list` to verify agent deployment

---

## 🆘 Need Help?

Check the main [README.md](README.md) for detailed documentation and architecture diagrams.

**Author:** Markus van Kempen | mvk@ca.ibm.com  
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)