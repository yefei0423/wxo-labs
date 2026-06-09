#!/bin/bash
# ---
# **Author**: Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# *No bug too small, no syntax too weird.*
# ---
export PYTHONUNBUFFERED=1
python3 "$(dirname "$0")/simple_mcp_server.py"
