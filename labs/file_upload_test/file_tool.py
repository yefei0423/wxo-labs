# Author: Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# No bug too small, no syntax too weird.
import pandas as pd

from ibm_watsonx_orchestrate.agent_builder.tools import tool

@tool
def vt_template_header_reader_tool_saal_dup(filepath: str) -> str:
    """
    Returns dataframe of the file
    """
    try:
        df = pd.read_excel(filepath)
        return str(df)
    except Exception as e:
        return f"Error reading file: {str(e)}"
