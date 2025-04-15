import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# OpenAI API settings
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o-mini-2024-07-18"

# Crawler settings
DEFAULT_MAX_PAGES = 10
DEFAULT_TIMEOUT = 30
DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Output settings
OUTPUT_DIR = "output"
CRAWL_DATA_FILENAME = "crawl_data_{timestamp}.json"
ANALYSIS_FILENAME = "analysis_{timestamp}.json"

# Logging settings
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Feature extraction settings
MAX_TOKENS_PER_CHUNK = 4000
CHUNK_OVERLAP = 200 