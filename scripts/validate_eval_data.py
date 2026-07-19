"""Validate all evaluation data files have correct structure."""
import json
from pathlib import Path

# Use absolute path based on this script location
script_dir = Path(__file__).parent
project_root = script_dir.parent
data_dir = project_root / "codeinsight-backend" / "codeinsight" / "evaluation" / "data"
errors = []

# Check root Python files
for f in data_dir.glob("*.json"):
    with open(f, encoding="utf-8") as fp:
        data = json.load(fp)
    if "language" not in data:
        errors.append(f"MISSING language field: {f.name}")
    elif data["language"] != "python":
        errors.append(f'Wrong language for {f.name}: {data["language"]}')

# Check subdirectory files
for lang_dir in ["javascript", "typescript", "java", "go", "vue"]:
    dir_path = data_dir / lang_dir
    if not dir_path.exists():
        errors.append(f"MISSING directory: {lang_dir}/")
        continue
    expected_lang = lang_dir
    for f in sorted(dir_path.glob("*.json")):
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
        if "language" not in data:
            errors.append(f"MISSING language field: {lang_dir}/{f.name}")
        elif data["language"] != expected_lang:
            errors.append(f'Wrong language in {lang_dir}/{f.name}: {data["language"]} != {expected_lang}')
        cases = data.get("test_cases", [])
        if len(cases) != 8:
            errors.append(f"Wrong case count in {lang_dir}/{f.name}: {len(cases)} != 8")

if errors:
    print("ERRORS:")
    for e in errors:
        print(f"  - {e}")
    exit(1)
else:
    print("All data files validated successfully!")

# Count totals
total = 0
for d in ["javascript", "typescript", "java", "go", "vue"]:
    dp = data_dir / d
    if dp.exists():
        total += sum(len(json.loads((dp / f).read_text(encoding="utf-8")).get("test_cases", [])) for f in dp.glob("*.json"))

for f in data_dir.glob("*.json"):
    with open(f, encoding="utf-8") as fp:
        data = json.load(fp)
    total += len(data.get("test_cases", []))

print(f"Total test cases across all languages: {total}")
