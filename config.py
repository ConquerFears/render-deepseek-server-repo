# Create a new config.py file for centralized configuration
import os

class Config:
    """Application configuration"""
    # Database
    DATABASE_URL = os.environ.get("DATABASE_URL")
    
    # Gemini API
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    GEMINI_MODEL = "models/gemini-2.0-flash"
    
    # Rate limiting
    REQUEST_LIMIT_SECONDS = 1
    CACHE_EXPIRY_SECONDS = 60 * 5  # 5 minutes
    
    # Default generation config
    GENERATION_CONFIG = {
        "temperature": 0.35,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 150
    } 