
import os
import sys

# Add shared to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from shared.nexus_common.openai_helper import llm_chat

os.environ["OPENAI_API_KEY"] = "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"

print("Testing LLM...")
try:
    resp = llm_chat("You are a helper. Respond in JSON.", "Give me a simple valid JSON object.")
    print("Response:", resp)
except Exception as e:
    print("Error:", e)
