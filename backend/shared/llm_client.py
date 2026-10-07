import google.generativeai as genai
from backend.config import get_settings
from backend.shared.logger import get_logger

logger = get_logger(__name__)

class GeminiClient:
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.gemini_api_key
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set.")
        else:
            genai.configure(api_key=self.api_key)
        
        self.model_name = "gemini-1.5-pro" # Default model, can be overridden

    async def generate_content(self, prompt: str, system_instruction: str = None) -> str:
        if not self.api_key:
            return "Mock response: API key not configured."
        
        try:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_instruction
            )
            response = await model.generate_content_async(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            raise

llm_client = GeminiClient()
