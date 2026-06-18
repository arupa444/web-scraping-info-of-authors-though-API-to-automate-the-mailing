"""AI service package: the single entry point for all Gemini-backed features.

No module outside this package imports ``google-genai`` directly (§9.1). Every
capability is schema-validated and degrades gracefully when ``GEMINI_API_KEY``
is unset.
"""
