"""Entry point for `python -m auris`.

Loads a `.env` file from the current working directory (or any parent)
before delegating to the audit pipeline, so users don't need to
manually `export` env vars like `GROQ_API_KEY` each shell session.
"""
from dotenv import load_dotenv

load_dotenv()

from auris.audit_risk import main

if __name__ == "__main__":
    main()
