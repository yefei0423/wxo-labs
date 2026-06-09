**Author:** Markus van Kempen | mvk@ca.ibm.com
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
*No bug too small, no syntax too weird.*

---

# Troubleshooting: Python Tool Context Injection Issues

> Findings from a real Slack debug session — March 2026

---

## Issue 1: `ModuleNotFoundError: No module named 'ibm_watsonx_orchestrate.run.context'`

**Symptom:** Tool imports fine locally via CLI, but fails at runtime in the WxO cloud sandbox with:
```
ModuleNotFoundError: No module named 'ibm_watsonx_orchestrate.run.context'
```

**Cause:** The cloud sandbox runtime does not ship the `run.context` submodule. It dynamically injects a duck-typed context object at runtime instead. The bare import statement crashes.

**Fix:** Wrap the import in `try/except`:
```python
try:
    from ibm_watsonx_orchestrate.run.context import AgentRun
except ImportError:
    AgentRun = object  # Fallback for cloud execution sandbox
```
The CLI still resolves the real `AgentRun` for spec generation. The cloud sandbox falls back to `object` and duck typing handles the rest since the injected context still has `.request_context`.

> **Note:** Adding `ibm_watsonx_orchestrate` to `requirements.txt` does **not** fix this. The sandbox doesn't load `run.context` regardless of package version. The `try/except` is the only solution.

---

## Issue 2: `AttributeError: 'dict' object has no attribute 'request_context'`

**Symptom:** After applying the `try/except` fix, you get:
```
AttributeError: 'dict' object has no attribute 'request_context'
```

**Cause:** Your ADK version output shows an override:
```
❯ orchestrate --version
ADK Version: 2.5.1 (override: 1.12.0rc2505)
```
The `(override: 1.12.0rc2505)` means `python_registry.test_package_version_override` is set in your local config. This forces the sandbox to use an old pre-release platform version (`1.12.0rc2505`) which injects the context as a plain `dict` instead of an `AgentRun` object — so `.request_context` doesn't exist.

**Fix:** Remove the override from your local orchestrate config:

```bash
# Open the config file
nano ~/.config/orchestrate/config.yaml

# Find and remove the line:
#   python_registry:
#     test_package_version_override: 1.12.0rc2505

# Verify the override is gone
orchestrate --version
# Should now show: ADK Version: 2.5.1  (no override)
```

After removing the override, the context is injected correctly as an `AgentRun`-compatible object with `.request_context`.

---

## Issue 3: `requirements.txt` — dashes vs underscores

**Symptom:** Tool deploys but fails at runtime, or you get `Error getting Python tool status`.

**Cause:** Using the wrong package name format or pinning an old version:
```
# Wrong (old version — run.context missing or broken)
ibm_watsonx_orchestrate==2.3.0

# Also wrong (pinning 1.12.x via override)
ibm-watsonx-orchestrate==1.12.0rc2505
```

**Fix:** Use the unpinned package name (pip accepts both dashes and underscores):
```
ibm-watsonx-orchestrate
```

Do **not** pin a specific old version. Let the platform resolve the correct version.

---

## Checklist: Context injection not working?

1. **Check for version override:**
   ```bash
   orchestrate --version
   ```
   If you see `(override: X.Y.Z)` — remove `python_registry.test_package_version_override` from `~/.config/orchestrate/config.yaml`.

2. **Check your tool import:**
   ```python
   try:
       from ibm_watsonx_orchestrate.run.context import AgentRun
   except ImportError:
       AgentRun = object
   ```

3. **Check `requirements.txt`:**
   ```
   ibm-watsonx-orchestrate
   ```
   No version pin. No underscores in the name (either format works but keep it consistent).

4. **Check agent YAML / CLI has `--context-variable wxo_email_id`** set, and the tool parameter is typed `context: AgentRun`.

5. **Import command (single-file tool):**
   ```bash
   orchestrate tools import -k python -f context_test_tool.py -r requirements.txt
   ```

---

## Reference

- [WxO Docs: Using context variables](https://developer.watson-orchestrate.ibm.com/tools/create_tool#using-context-variables)
- [WxO Docs: Importing Python tools](https://developer.watson-orchestrate.ibm.com/tools/deploy_tool)
- See [README.md](README.md) for the full workaround and test setup.
