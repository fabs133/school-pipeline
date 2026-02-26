"""Allow running as `python -m schulpipeline`."""
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from schulpipeline.cli import main

main()
