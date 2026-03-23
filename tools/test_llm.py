"""Quick smoke-test for llm_chat — uses OPENAI_API_KEY from environment."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from shared.nexus_common.openai_helper import llm_chat  # noqa: E402

if not os.getenv("OPENAI_API_KEY"):
    print("ERROR: Set OPENAI_API_KEY environment variable before running this script.")
    sys.exit(1)

print("Testing LLM...")
try:
    resp = llm_chat("You are a helper. Respond in JSON.", "Give me a simple valid JSON object.")
    print("Response:", resp)
except Exception as e:
    print("Error:", e)
