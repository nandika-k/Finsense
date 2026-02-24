"""
Utility module for standardizing LLM calls across Finsense.
Handles rate limits from primary providers (Groq) by falling back to free-tier alternatives (Gemini).
"""
import os
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False
    Groq = None

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    OpenAI = None

# Global clients to reuse connections
_groq_client = None
_fallback_client = None

def get_groq_client():
    global _groq_client
    if not HAS_GROQ:
        return None
    
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if api_key:
            try:
                _groq_client = Groq(api_key=api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Groq client: {e}")
    return _groq_client


def get_fallback_client():
    """Initializes an OpenAI-compatible client for Gemini (free tier fallback)."""
    global _fallback_client
    
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package not installed. Fallback disabled.")
        return None
        
    if _fallback_client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            try:
                _fallback_client = OpenAI(
                    api_key=api_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                )
            except Exception as e:
                logger.error(f"Failed to initialize fallback client: {e}")
    return _fallback_client


def call_llm(
    messages: List[Dict[str, str]], 
    model: str = "llama-3.3-70b-versatile", 
    temperature: float = 0.1, 
    max_tokens: int = 800,
    response_format: Optional[Dict[str, str]] = None
) -> str:
    """
    Call LLM with automatic fallback on rate limit or other errors.
    Returns the message content string.
    """
    groq_client = get_groq_client()
    latest_err = None
    
    if groq_client:
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format
                
            response = groq_client.chat.completions.create(**kwargs)
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            latest_err = e
            is_rate_limit = "RateLimitError" in type(e).__name__ or "429" in str(e)
            
            if is_rate_limit:
                logger.warning("Groq rate limit hit. Attempting fallback...")
                if os.getenv("DEBUG_CHATBOT"):
                    print("[DEBUG] Groq rate limit hit. Attempting fallback...")
            else:
                logger.warning(f"Groq API error: {e}. Attempting fallback...")
                if os.getenv("DEBUG_CHATBOT"):
                    print(f"[DEBUG] Groq API error: {e}. Attempting fallback...")
    
    # Fallback to Gemini via OpenAI compability
    fallback_client = get_fallback_client()
    if fallback_client:
        try:
            # Use a free Gemini model
            fallback_model = "gemini-2.5-flash"
            
            kwargs = {
                "model": fallback_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format
                
            response = fallback_client.chat.completions.create(**kwargs)
            return response.choices[0].message.content.strip()
        except Exception as fallback_err:
            logger.error(f"Fallback LLM also failed: {fallback_err}")
            raise Exception(f"Both primary and fallback LLMs failed. Primary error: {latest_err}. Fallback error: {fallback_err}")
    else:
        logger.error("No fallback client available (missing openai package or GEMINI_API_KEY).")
        if latest_err:
            raise latest_err
        else:
            raise Exception("No LLM clients available. Ensure GROQ_API_KEY or GEMINI_API_KEY is set.")
