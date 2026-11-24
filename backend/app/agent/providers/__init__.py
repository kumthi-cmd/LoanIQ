"""LLM providers: one interface (base.LLMProvider), one adapter per model vendor.

BUSINESS: the model behind Ask the Tape can be swapped (Claude, ChatGPT, Gemini,
  built-in rules) without touching the loop, the tools or the screen.
TECH: the Strategy pattern. The orchestrator holds an LLMProvider and calls chat();
  each adapter translates LoanIQ's neutral messages and tools into its vendor's API.
"""
