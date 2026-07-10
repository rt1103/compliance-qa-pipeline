import os
from litellm import Router
import litellm

# 1. Enable LiteLLM Local Caching
# This ensures identical compliance questions don't waste API calls.
litellm.cache = litellm.Cache(type="local") 

# 2. Define the Routing Map
# We group all three models under a single alias: "auditor-llm"
model_list = [
    {
        "model_name": "auditor-llm", 
        "litellm_params": {
            "model": "openai/gpt-4o",
            "api_key": os.getenv("GITHUB_TOKEN"),
            "api_base": "https://models.inference.ai.azure.com"
        }
    },
    {
        "model_name": "auditor-llm",
        "litellm_params": {
            "model": "gemini/gemini-1.5-flash",
            "api_key": os.getenv("GEMINI_API_KEY")
        }
    },
    {
        "model_name": "auditor-llm",
        "litellm_params": {
            "model": "groq/llama-3.3-70b-versatile", # The 2026 upgraded Groq model
            "api_key": os.getenv("GROQ_API_KEY")
        }
    }
]

# 3. Initialize the Gateway Router
# This implements Load Balancing, Latency Routing, and Fallbacks
gateway_router = Router(
    model_list=model_list,
    routing_strategy="latency-based-routing", # Routes to whichever model responds the fastest
    num_retries=2, 
    # If the fastest model fails, it automatically falls back to the others
    fallbacks=[{"auditor-llm": ["gemini/gemini-1.5-flash", "groq/llama-3.3-70b-versatile"]}] 
)