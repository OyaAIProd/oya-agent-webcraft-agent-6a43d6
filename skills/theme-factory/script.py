"""Theme Factory — entry point dispatcher for sandbox execution."""
import json
import os

# In the sandbox, skill files are at /home/daytona/_skill/
# Locally, use __file__ if available
_SKILL_DIR = os.path.dirname(__file__) if "__file__" in dir() else "/home/daytona/_skill"
ASSETS_DIR = os.path.join(_SKILL_DIR, "assets")
THEMES_DIR = os.path.join(ASSETS_DIR, "themes")

try:
    inp = json.loads(os.environ.get("INPUT_JSON", "{}"))
    action = inp.get("action", "")

    if action == "list_themes":
        themes = []
        if os.path.isdir(THEMES_DIR):
            for f in sorted(os.listdir(THEMES_DIR)):
                if f.endswith(".md"):
                    name = f.replace(".md", "")
                    # Read first line for display name
                    with open(os.path.join(THEMES_DIR, f)) as fh:
                        first_line = fh.readline().strip().lstrip("# ").strip()
                    themes.append({"id": name, "name": first_line or name})
        print(json.dumps({"themes": themes, "count": len(themes)}))

    elif action == "get_theme":
        theme_name = inp.get("theme_name", "")
        if not theme_name:
            print(json.dumps({"error": "theme_name is required"}))
        else:
            theme_file = os.path.join(THEMES_DIR, f"{theme_name}.md")
            if not os.path.exists(theme_file):
                # Try fuzzy match
                available = [f.replace(".md", "") for f in os.listdir(THEMES_DIR) if f.endswith(".md")]
                print(json.dumps({"error": f"Theme '{theme_name}' not found. Available: {', '.join(sorted(available))}"}))
            else:
                with open(theme_file) as fh:
                    content = fh.read()
                print(json.dumps({"theme_name": theme_name, "content": content}))

    elif action == "show_showcase":
        showcase_path = os.path.join(ASSETS_DIR, "theme-showcase.pdf")
        if os.path.exists(showcase_path):
            print(json.dumps({"showcase_path": showcase_path, "exists": True}))
        else:
            print(json.dumps({"error": "theme-showcase.pdf not found"}))

    elif action == "apply_theme":
        theme_name = inp.get("theme_name", "")
        artifact_path = inp.get("artifact_path", "")
        if not theme_name:
            print(json.dumps({"error": "theme_name is required"}))
        elif not artifact_path:
            print(json.dumps({"error": "artifact_path is required"}))
        else:
            theme_file = os.path.join(THEMES_DIR, f"{theme_name}.md")
            if not os.path.exists(theme_file):
                available = [f.replace(".md", "") for f in os.listdir(THEMES_DIR) if f.endswith(".md")]
                print(json.dumps({"error": f"Theme '{theme_name}' not found. Available: {', '.join(sorted(available))}"}))
            else:
                with open(theme_file) as fh:
                    theme_content = fh.read()
                # Return the theme data — the LLM applies it to the artifact
                print(json.dumps({
                    "theme_name": theme_name,
                    "theme": theme_content,
                    "artifact_path": artifact_path,
                    "instruction": "Apply the colors, fonts, and styling from the theme to the artifact file.",
                }))

    elif action == "create_custom_theme":
        description = inp.get("custom_description", "")
        if not description:
            print(json.dumps({"error": "custom_description is required — describe the look and feel you want"}))
        else:
            # Return the description so the LLM generates a theme in the same format
            # Read one existing theme as a format reference
            reference = ""
            for f in os.listdir(THEMES_DIR):
                if f.endswith(".md"):
                    with open(os.path.join(THEMES_DIR, f)) as fh:
                        reference = fh.read()
                    break
            print(json.dumps({
                "instruction": "Generate a custom theme matching the format of the reference theme below, based on the user's description.",
                "description": description,
                "reference_format": reference,
            }))

    else:
        print(json.dumps({"error": f"Unknown action: {action}. Available: list_themes, get_theme, show_showcase, apply_theme, create_custom_theme"}))

except Exception as e:
    print(json.dumps({"error": str(e)}))
