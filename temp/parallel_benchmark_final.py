import asyncio
import contextlib
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.helixcare_scenarios import SCENARIOS, _load_additional_scenarios, run_multiple_scenarios


def main() -> None:
    names = [s.name for s in (SCENARIOS + _load_additional_scenarios())]
    buf = io.StringIO()
    t0 = time.time()
    with contextlib.redirect_stdout(buf):
        asyncio.run(run_multiple_scenarios(names, parallel=True))
    out = buf.getvalue()
    metrics = {
        "parallel_scenarios": len(names),
        "completed": out.count("completed!"),
        "hard_failures": out.count("Error: All connection attempts failed"),
        "recovered_calls": out.count("recovered on attempt"),
        "elapsed_s": round(time.time() - t0, 2),
    }
    with open("temp/parallel_benchmark_final_result.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f)


if __name__ == "__main__":
    main()
