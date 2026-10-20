import pathlib, json
root = pathlib.Path(".")
print("=== CherryPulse-KR-01 진행 체크 ===\n")

must = [
 "docs/CherryPulse-KR-01-Development-Direction.md",
 "docs/CherryPulse-KR-01-Rebuild-Plan.md",
 "docs/REBUILD-02-CONTRACTS.md",
 "docs/treadding/REST-MIGRATION-PLAN.md",
 "docs/treadding/REST-MIGRATION-HANDOFF.md",
 "docs/treadding/REST-MIGRATION-STATUS.json"
]

for p in must:
    print(f"{'✅' if (root/p).exists() else '❌ 미진행'} {p}")

print("\n--- deprecated root engine files ---")
deprecated = {
    "main_live.py": "back/legacy-2026-09-13/main_live.py",
    "engine.py": "back/legacy-2026-09-13/engine.py",
    "config_live.py": "back/legacy-2026-09-13/config_live.py",
    "broker/kiwoom_broker.py": "back/legacy-2026-09-13/broker/kiwoom_broker.py",
}
for name, archive in deprecated.items():
    archive_status = (root/archive).is_file()
    state = (
        "✅ DEPRECATED (보관본 확인)"
        if archive_status
        else "⚠️ DEPRECATED (보관본 미확인)"
    )
    print(f"{state} {name} → {archive}")

print("\n--- 화면/보드 관련 ---")
for p in root.rglob("*board*"): print(p)
for p in root.rglob("*screen*"): print(p)
for p in root.glob("*.py"): print(f"ROOT PY: {p.name}")

print("\n--- docs/treadding 내용 ---")
td = root/"docs/treadding"
if td.exists():
    for f in td.iterdir(): print(f.name)
else:
    print("❌ docs/treadding 폴더 없음")

print("\n--- back 폴더가 활성 import 되고 있는지 ---")
import os
for dirpath,_,files in os.walk("."):
    if "back" in dirpath and ".py" in str(files):
        continue
    for f in files:
        if f.endswith(".py"):
            source = pathlib.Path(dirpath, f)
            if source.resolve() == pathlib.Path(__file__).resolve():
                continue
            try:
                txt = source.read_text(encoding="utf-8", errors="ignore")
                if "from back" in txt or "import back" in txt:
                    print(f"⚠️ {dirpath}/{f} 에서 back import 중!")
            except: pass
print("\n끝 - 이 결과를 복사해서 붙여넣어줘")