# uplas-backend/apps/ai_agents/services/ai_agent_client.py

import os
import requests
from typing import Dict, Any
from logging import getLogger

from django.conf import settings

logger = getLogger(__name__)

class AIAgentClient:
    """
    A client for communicating with the Uplas Unified AI Agent Service.
    It handles constructing requests, sending them, and processing responses.
    """

    def __init__(self):
        # Use the URL from Django settings, which should be loaded from .env or Cloud Run env vars.
        self.base_url = getattr(settings, 'AI_AGENT_SERVICE_URL', None)
        if not self.base_url:
            logger.error("AI_AGENT_SERVICE_URL is not configured in settings. AI Agent client will fail.")
            # You could raise an ImproperlyConfigured exception here for a stricter contract.

        self.timeout = getattr(settings, 'AI_AGENT_REQUEST_TIMEOUT', 30) # 30-second timeout

    def _make_request(self, method: str, endpoint: str, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Internal method to make an HTTP request to the AI agent service.
        """
        if not self.base_url:
            raise ValueError("AI Agent Service URL is not configured.")

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Content-Type": "application/json",
            # If you add auth between services (e.g., an API key or a token), add it here.
            # "X-Internal-API-Key": settings.AI_AGENT_INTERNAL_API_KEY
        }

        try:
            response = requests.request(method, url, json=json_data, headers=headers, timeout=self.timeout)
            response.raise_for_status() # Raises an HTTPError for 4xx or 5xx status codes
            return response.json()
        except requests.exceptions.Timeout:
            logger.error(f"Request to AI Agent Service timed out: {url}")
            raise TimeoutError("The request to the AI service timed out. Please try again later.")
        except requests.exceptions.ConnectionError:
            logger.error(f"Could not connect to AI Agent Service at {url}")
            raise ConnectionError("Could not connect to the AI service. It may be offline.")
        except requests.exceptions.HTTPError as e:
            logger.error(f"AI Agent Service returned an error: {e.response.status_code} - {e.response.text}")
            # Propagate a user-friendly error
            raise ValueError(f"The AI service returned an error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"An unexpected error occurred calling AI agent: {str(e)}")
            raise Exception("An unexpected error occurred while communicating with the AI service.")


    def call_nlp_tutor(self, user_id: str, query_text: str, user_profile_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calls the /nlp_tutor/process endpoint.
        """
        endpoint = "/api/v1/nlp_tutor/process"
        payload = {
            "user_id": user_id,
            "query_text": query_text,
            "user_profile_snapshot": user_profile_snapshot,
        }
        return self._make_request("POST", endpoint, payload)


    def call_project_generator(self, user_id: str, course_context: Dict[str, Any], user_profile_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calls the /project_generator/generate_idea endpoint.
        """
        endpoint = "/api/v1/project_generator/generate_idea"
        payload = {
            "user_id": user_id,
            "course_context": course_context,
            "user_profile_snapshot": user_profile_snapshot,
        }
        return self._make_request("POST", endpoint, payload)

# Instantiate a client for easy import and use in views
ai_agent_client = AIAgentClient()
