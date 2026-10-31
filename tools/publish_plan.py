#!/usr/bin/env python3
"""Publish the v1 spec and build-plan tasks to GitHub Issues with the gh CLI.

Run from the repo root on a machine where `gh auth status` succeeds:
    python3 tools/publish_plan.py docs/spec-v1.md tools/issues.json docs/plan.md

The Blocked by section in each body stays as a fallback where native links fail.
Creates missing labels, the spec issue (ready-for-agent), one issue per step with
#numbers filled in, appends a task checklist to the spec issue, and rewrites
docs/plan.md with the issue numbers.
"""
import json, re, subprocess, sys

REPO = "BobbyJoeCool/Voicewright"
spec_path, issues_path, plan_path = sys.argv[1:4]

def gh(*args):
    return subprocess.run(["gh", *args, "--repo", REPO], check=True, capture_output=True, text=True).stdout.strip()

for name, color in [("ready-for-agent", "0e8a16"), ("ready-for-human", "fbca04"), ("enhancement", "a2eeef")]:
    subprocess.run(["gh", "label", "create", name, "--color", color, "--repo", REPO, "--force"], check=True, capture_output=True)

def create(title, body, labels):
    url = gh("issue", "create", "--title", title, "--body", body, *sum([["--label", l] for l in labels], []))
    return int(url.rsplit("/", 1)[1])

spec_body = open(spec_path).read()
spec = create("Voicewright v1", spec_body, ["ready-for-agent", "enhancement"])
nums = {"spec": spec}
issues = json.load(open(issues_path))
fill = lambda text: re.sub(r"\{\{([\w.]+)\}\}", lambda m: f"#{nums[m.group(1)]}", text)
for it in issues:
    nums[it["step"]] = create(it["title"], fill(it["body"]), [it["label"]])
    print(f"{it['step']} -> #{nums[it['step']]}")

# Native GitHub links: tasks as sub-issues of the spec, and blocked-by edges.
def db_id(n):
    return subprocess.run(["gh", "api", f"repos/{REPO}/issues/{n}", "--jq", ".id"], check=True, capture_output=True, text=True).stdout.strip()

def api_post(path, field):
    r = subprocess.run(["gh", "api", "--method", "POST", f"repos/{REPO}/{path}", "-F", field], capture_output=True, text=True)
    if r.returncode:
        print(f"  (skipped {path}: {r.stderr.strip()[:120]})")

ids = {k: db_id(v) for k, v in nums.items()}
for it in issues:
    api_post(f"issues/{spec}/sub_issues", f"sub_issue_id={ids[it['step']]}")
    for dep in it.get("deps", []):
        api_post(f"issues/{nums[it['step']]}/dependencies/blocked_by", f"issue_id={ids[dep]}")

checklist = "\n\n## Tasks\n\nBuild plan: `docs/plan.md`.\n\n" + "\n".join(f"- [ ] #{nums[i['step']]}" for i in issues) + "\n"
gh("issue", "edit", str(spec), "--body", spec_body + checklist)
open(plan_path, "w").write(fill(open(plan_path).read()))
print(f"Spec #{spec}; plan updated at {plan_path}")
