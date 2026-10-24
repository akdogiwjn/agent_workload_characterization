import json, time, uuid
from pathlib import Path
receipt = uuid.uuid4().hex
out = Path("/task/output/receipt.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"receipt": receipt, "written_at_monotonic": time.monotonic()}))
print("RECEIPT:", receipt)
