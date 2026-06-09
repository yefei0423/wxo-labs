import os
# Author: Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# No bug too small, no syntax too weird.
from file_tool import vt_template_header_reader_tool_saal_dup


def test_file_reader():
    # Use absolute path for reliability
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sample_file = os.path.join(current_dir, 'sample.xlsx')
    
    print(f"Testing tool with file: {sample_file}")
    
    if not os.path.exists(sample_file):
        print("Error: sample.xlsx not found!")
        return

    result = vt_template_header_reader_tool_saal_dup(sample_file)
    print("\nResult from tool:")
    print(result)

if __name__ == "__main__":
    test_file_reader()
