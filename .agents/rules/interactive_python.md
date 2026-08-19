# Interactive Python Preference

The user prefers Python scripts to be formatted for interactive execution in Jupyter/VS Code Interactive Window style.
When creating or modifying Python scripts, default to using `#%%` cell markers to separate code into logical blocks:
- `#%% Parameters and Imports` (for imports, constants, and adjustable parameters)
- `#%% Functions` (for function definitions)
- `#%% Execution` (for the main execution flow, instead of using an `if __name__ == "__main__":` block)

Ensure scripts are designed to be run top-to-bottom iteratively, avoiding things like `sys.exit(1)` that would crash interactive kernels.
