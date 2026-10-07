import json
from backend.shared.llm_client import llm_client
from backend.agents.researcher.models import ResearcherOutput
from backend.agents.researcher.prompts import SYSTEM_PROMPT

class ResearcherAgent:
    def __init__(self):
        self.system_prompt = SYSTEM_PROMPT
        
    async def run(self, problem: str, context: dict = None) -> ResearcherOutput:
        context_str = json.dumps(context) if context else ""
        prompt = f"Problem: {problem}\nContext: {context_str}\nPlease output valid JSON adhering to your schema."
        
        response_text = await llm_client.generate_content(
            prompt=prompt,
            system_instruction=self.system_prompt
        )
        
        if "Mock response" in response_text:
            mock_data = {}
            for field, field_info in ResearcherOutput.model_fields.items():
                if "list" in str(field_info.annotation).lower():
                    mock_data[field] = ["Mocked data"]
                elif "dict" in str(field_info.annotation).lower():
                    mock_data[field] = {"mock_key": "mock_value"}
                else:
                    mock_data[field] = "Mocked data"
            return ResearcherOutput(**mock_data)
            
        try:
            import json
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text
            data = json.loads(json_str)
            return ResearcherOutput(**data)
        except Exception as e:
            raise ValueError(f"Failed to parse LLM output into ResearcherOutput: {e}")
