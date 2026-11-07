import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> bool:
        return False

load_dotenv()

PDF_PATH = os.getenv("PDF_PATH", "data/input/answer_key.pdf")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "data/output")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "change_me")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
