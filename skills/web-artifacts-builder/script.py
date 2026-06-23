"""Web Artifacts Builder — entry point dispatcher for sandbox execution."""
import json
import os
import re
import subprocess
import sys


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes so LLM can read error messages clearly."""
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)

_SKILL_DIR = os.path.dirname(__file__) if "__file__" in dir() else "/home/daytona/_skill"
SCRIPTS_DIR = os.path.join(_SKILL_DIR, "scripts")
WORK_DIR = os.environ.get("WORK_DIR", "/home/daytona/artifacts")


def run_bash(script_name, *args, cwd=None):
    """Run a bash script from the scripts/ directory."""
    path = os.path.join(SCRIPTS_DIR, script_name)
    if not os.path.exists(path):
        return {"error": f"Script not found: {script_name}"}
    result = subprocess.run(
        ["bash", path, *args],
        capture_output=True, text=True, timeout=300, cwd=cwd,
    )
    return {
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "exit_code": result.returncode,
    }


def _find_project(project_name=None):
    """Find the project directory. If project_name given, use it. Otherwise use the most recently modified project."""
    if not os.path.isdir(WORK_DIR):
        return WORK_DIR

    # Explicit project name
    if project_name:
        candidate = os.path.join(WORK_DIR, project_name)
        if os.path.isdir(candidate):
            return candidate

    # Find all project dirs (have package.json)
    projects = []
    for d in os.listdir(WORK_DIR):
        candidate = os.path.join(WORK_DIR, d)
        if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "package.json")):
            mtime = os.path.getmtime(os.path.join(candidate, "package.json"))
            projects.append((mtime, candidate))

    if projects:
        # Most recently modified project
        projects.sort(reverse=True)
        return projects[0][1]

    return WORK_DIR


try:
    inp = json.loads(os.environ.get("INPUT_JSON", "{}"))
    action = inp.get("action", "")
    project_name = inp.get("project_name", "")

    if action == "init_project":
        if not project_name:
            project_name = "artifact"
        os.makedirs(WORK_DIR, exist_ok=True)
        result = run_bash("init-artifact.sh", project_name, cwd=WORK_DIR)
        if result["exit_code"] == 0:
            project_path = os.path.join(WORK_DIR, project_name)
            print(json.dumps({
                "project_path": project_path,
                "project_name": project_name,
                "message": f"Project '{project_name}' initialized. Use project_name='{project_name}' in subsequent calls.",
                "stdout": result["stdout"][-500:] if result["stdout"] else "",
            }))
        else:
            print(json.dumps({"error": result["stderr"] or result["stdout"]}))

    elif action == "write_file":
        file_path = inp.get("file_path", "")
        content = inp.get("content", "")
        if not file_path:
            print(json.dumps({"error": "file_path is required"}))
        else:
            if os.path.isabs(file_path):
                full_path = file_path
            else:
                project_dir = _find_project(project_name)
                full_path = os.path.join(project_dir, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)
            print(json.dumps({"written": full_path, "size": len(content)}))

    elif action == "bundle":
        project_dir = _find_project(project_name)

        if not os.path.exists(os.path.join(project_dir, "index.html")):
            print(json.dumps({"error": f"No index.html found in {project_dir}. Run init_project first."}))
        else:
            # Install deps if node_modules missing (sandbox may have been recycled)
            if not os.path.isdir(os.path.join(project_dir, "node_modules")):
                r = subprocess.run(["bun", "install"], capture_output=True, text=True, timeout=120, cwd=project_dir)
                if r.returncode != 0:
                    print(json.dumps({"error": f"bun install failed: {_strip_ansi((r.stderr or r.stdout).strip()[-500:])}"}))
                    raise SystemExit(0)

            # Run vite build via package.json script (uses local vite, not latest)
            steps = [
                (["bun", "run", "build"], "Vite build"),
            ]
            for cmd, label in steps:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=project_dir)
                if r.returncode != 0:
                    print(json.dumps({"error": f"{label} failed: {_strip_ansi((r.stderr or r.stdout).strip()[-500:])}"}))
                    raise SystemExit(0)

            # Inline all assets into single HTML
            dist_index = os.path.join(project_dir, "dist", "index.html")
            bundle_path = os.path.join(project_dir, "bundle.html")
            if not os.path.exists(dist_index):
                print(json.dumps({"error": "Vite build produced no dist/index.html"}))
            else:
                r = subprocess.run(
                    ["./node_modules/.bin/html-inline", dist_index],
                    capture_output=True, text=True, timeout=60, cwd=project_dir,
                )
                if r.returncode == 0 and r.stdout.strip():
                    with open(bundle_path, "w") as f:
                        f.write(r.stdout)
                    # Copy to _skill dir so the sandbox file scanner can serve it
                    import shutil
                    skill_dir = "/home/daytona/_skill"
                    os.makedirs(skill_dir, exist_ok=True)
                    served_path = os.path.join(skill_dir, "bundle.html")
                    shutil.copy2(bundle_path, served_path)
                    print(f"A2ABASEAI_FILE: {served_path}")
                    size = os.path.getsize(bundle_path)
                    print(json.dumps({
                        "bundle_path": served_path,
                        "size_bytes": size,
                        "message": f"Bundled to bundle.html ({size:,} bytes)",
                    }))
                else:
                    print(json.dumps({"error": f"html-inline failed: {(r.stderr or '').strip()[-500:]}"}))

    elif action == "list_files":
        project_dir = _find_project(project_name)
        files = []
        if os.path.isdir(project_dir):
            for root, dirs, fnames in os.walk(project_dir):
                dirs[:] = [d for d in dirs if d not in ("node_modules", ".parcel-cache", "dist")]
                for fname in fnames:
                    full = os.path.join(root, fname)
                    files.append(os.path.relpath(full, project_dir))
        print(json.dumps({"project_dir": project_dir, "files": sorted(files), "count": len(files)}))

    else:
        print(json.dumps({"error": f"Unknown action: {action}. Available: init_project, write_file, bundle, list_files"}))

except Exception as e:
    print(json.dumps({"error": str(e)}))
