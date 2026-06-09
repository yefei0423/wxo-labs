# ---
# **Author:** Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# *No bug too small, no syntax too weird.*
# ---
import os
import re

bundle_dir = "extracted_bundle"
suffix = "_v2"

# 1. We need to append suffix to the tool decorator's name or function name in the Python files
tools_dir = os.path.join(bundle_dir, "tools")

for tool_folder in os.listdir(tools_dir):
    tool_path = os.path.join(tools_dir, tool_folder)
    if not os.path.isdir(tool_path):
        continue
        
    for file in os.listdir(tool_path):
        if file.endswith(".py"):
            py_path = os.path.join(tool_path, file)
            with open(py_path, "r") as f:
                content = f.read()
            
            # The tools are long_running_tool, check_tool_status, clear_tool_state, blocking_plugin
            tool_names = ["long_running_tool", "check_tool_status", "clear_tool_state", "blocking_plugin"]
            
            for t_name in tool_names:
                # 1. Update function definition: def my_tool( -> def my_tool_v2(
                content = re.sub(rf"def {t_name}\(", f"def {t_name}{suffix}(", content)
                # 2. Update @tool(name="my_tool" -> @tool(name="my_tool_v2"
                content = re.sub(rf'@tool\(name="{t_name}"', f'@tool(name="{t_name}{suffix}"', content)
                
            with open(py_path, "w") as f:
                f.write(content)

print("Python files massaged!")
