import os

agents = {
    'researcher': {
        'model_name': 'ResearcherOutput',
        'fields': '''
    users_and_needs: list[str]
    constraints: list[str]
    assumptions: list[str]
    missing_information: list[str]
    verified_evidence: list[str]
    source_references: list[str]
''',
        'prompt': 'You are the Researcher agent. Your job is to understand the users requirements, identify users, needs, constraints, assumptions, and missing information. Retrieve relevant evidence and distinguish it from assumptions. Return structured findings and source references.'
    },
    'strategist': {
        'model_name': 'StrategistOutput',
        'fields': '''
    strategy_overview: str
    prioritized_requirements: list[str]
    feasibility_and_tradeoffs: list[str]
    phased_execution_plan: list[str]
    success_criteria: list[str]
''',
        'prompt': 'You are the Strategist agent. Your job is to develop a practical strategy, prioritize requirements, evaluate feasibility and tradeoffs, create phased execution plans, and define measurable success criteria.'
    },
    'engineer': {
        'model_name': 'EngineerOutput',
        'fields': '''
    technical_architecture: str
    recommended_technologies: list[str]
    components_and_apis: list[str]
    data_flow: str
    implementation_plan: list[str]
''',
        'prompt': 'You are the Engineer agent. Your job is to design technical architecture, recommend technologies, describe components/APIs/data flow, and produce implementation plans while respecting constraints identified by other agents.'
    },
    'guardian': {
        'model_name': 'GuardianOutput',
        'fields': '''
    safety_and_privacy_risks: list[str]
    reliability_and_ethical_risks: list[str]
    unsafe_assumptions: list[str]
    limitations: list[str]
    recommended_mitigations: list[str]
''',
        'prompt': 'You are the Guardian agent. Your job is to identify safety, privacy, reliability, ethical, and misuse risks in the proposed solution. Recommend mitigations, human oversight, and identify unsafe assumptions and limitations.'
    },
    'evaluator': {
        'model_name': 'EvaluatorOutput',
        'fields': '''
    detected_contradictions: list[str]
    incompatible_assumptions: list[str]
    requirement_coverage_issues: list[str]
    unsupported_claims: list[str]
    missing_evidence: list[str]
    recommendations: list[str]
''',
        'prompt': 'You are the Evaluator agent. Your job is to compare outputs of other agents, detect contradictions and incompatible assumptions, check requirement coverage and logical consistency, and identify unsupported claims. Do not simply approve everything; identify real issues.'
    },
    'security': {
        'model_name': 'SecurityOutput',
        'fields': '''
    threats_and_attack_surfaces: list[str]
    auth_and_privacy_issues: list[str]
    prompt_injection_risks: list[str]
    insecure_api_access: list[str]
    recommended_mitigations: list[str]
    severity_levels: dict[str, str]
''',
        'prompt': 'You are the Security agent. Your job is to analyze technical security threats, attack surfaces, authentication, authorization, data privacy, prompt injection, and insecure API access. Review proposed designs for weaknesses and recommend mitigations with severity levels.'
    }
}

base_path = 'backend/agents'

for agent, data in agents.items():
    agent_path = os.path.join(base_path, agent)
    os.makedirs(agent_path, exist_ok=True)
    
    # Write models.py
    with open(os.path.join(agent_path, 'models.py'), 'w') as f:
        f.write(f'''from pydantic import BaseModel\nfrom typing import Dict, List\n\nclass {data['model_name']}(BaseModel):{data['fields']}''')
        
    # Write prompts.py
    with open(os.path.join(agent_path, 'prompts.py'), 'w') as f:
        f.write(f'''SYSTEM_PROMPT = \"\"\"{data['prompt']}\"\"\"\n''')
        
    # Write agent.py
    with open(os.path.join(agent_path, 'agent.py'), 'w') as f:
        f.write(f'''import json
from backend.shared.llm_client import llm_client
from backend.agents.{agent}.models import {data['model_name']}
from backend.agents.{agent}.prompts import SYSTEM_PROMPT

class {agent.capitalize()}Agent:
    def __init__(self):
        self.system_prompt = SYSTEM_PROMPT
        
    async def run(self, problem: str, context: dict = None) -> {data['model_name']}:
        context_str = json.dumps(context) if context else ""
        prompt = f"Problem: {{problem}}\\nContext: {{context_str}}\\nPlease output valid JSON adhering to your schema."
        
        response_text = await llm_client.generate_content(
            prompt=prompt,
            system_instruction=self.system_prompt
        )
        
        if "Mock response" in response_text:
            mock_data = {{}}
            for field, field_info in {data['model_name']}.model_fields.items():
                if "list" in str(field_info.annotation).lower():
                    mock_data[field] = ["Mocked data"]
                elif "dict" in str(field_info.annotation).lower():
                    mock_data[field] = {{"mock_key": "mock_value"}}
                else:
                    mock_data[field] = "Mocked data"
            return {data['model_name']}(**mock_data)
            
        try:
            import json
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text
            data = json.loads(json_str)
            return {data['model_name']}(**data)
        except Exception as e:
            raise ValueError(f"Failed to parse LLM output into {data['model_name']}: {{e}}")
''')

print("Phase 2 scaffolding complete.")
