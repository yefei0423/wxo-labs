# ---
# **Author:** Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# *No bug too small, no syntax too weird.*
# ---
import os
import json
import yaml
import shutil

bundle_dir = "extracted_bundle"
suffix = "_v2"

# 1. Rename tool folders and update their skill_v2.json
tools_dir = os.path.join(bundle_dir, "tools")
for tool_folder in os.listdir(tools_dir):
    old_tool_path = os.path.join(tools_dir, tool_folder)
    if os.path.isdir(old_tool_path):
        new_tool_name = tool_folder + suffix
        new_tool_path = os.path.join(tools_dir, new_tool_name)
        
        # Rename folder
        os.rename(old_tool_path, new_tool_path)
        
        # Update skill_v2.json
        skill_json_path = os.path.join(new_tool_path, "skill_v2.json")
        with open(skill_json_path, "r") as f:
            skill_data = json.load(f)
        
        skill_data["name"] = new_tool_name
        skill_data["display_name"] = skill_data.get("display_name", tool_folder) + suffix
        
        with open(skill_json_path, "w") as f:
            json.dump(skill_data, f, indent=2)

# 2. Update the agent yaml
agent_yaml_path = os.path.join(bundle_dir, "agents", "native", "input_blocking_test_agent.yaml")
with open(agent_yaml_path, "r") as f:
    agent_data = yaml.safe_load(f)

# Rename agent
agent_data["name"] = agent_data["name"] + suffix
if "display_name" in agent_data:
    agent_data["display_name"] = agent_data["display_name"] + suffix

# Update tools references
if "tools" in agent_data:
    agent_data["tools"] = [t + suffix for t in agent_data["tools"]]

# Update plugins references
if "plugins" in agent_data and "pre_invoke" in agent_data["plugins"]:
    agent_data["plugins"]["pre_invoke"] = [p + suffix for p in agent_data["plugins"]["pre_invoke"]]

new_agent_yaml_path = os.path.join(bundle_dir, "agents", "native", f"input_blocking_test_agent{suffix}.yaml")
with open(new_agent_yaml_path, "w") as f:
    yaml.dump(agent_data, f, sort_keys=False)

# Remove old agent yaml
os.remove(agent_yaml_path)

print(f"Bundle successfully massaged. New agent YAML created at: {new_agent_yaml_path}")
