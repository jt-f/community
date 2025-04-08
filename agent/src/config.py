import os
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

load_dotenv('.env')



# --- Mistral AI Configuration ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest") # Default model

if not MISTRAL_API_KEY:
    logger.warning("MISTRAL_API_KEY environment variable not set. LLM functionality will be disabled.")

logger.info(f"Using Mistral model: {MISTRAL_MODEL}") 