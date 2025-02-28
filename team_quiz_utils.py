###############################################################################
# TEAM QUIZ UTILITIES
###############################################################################

# Import required libraries
import os                    # For accessing environment variables
import json                  # For handling JSON data
import logging               # For logging errors and information
from google import genai     # Google's Generative AI library
from google.genai import types  # Type definitions for Gemini API

# Setup logging
logger = logging.getLogger(__name__)  # Create a logger for this module

# ========================================================================
#                  SECTION 1: TEAM DEFINITIONS AND CONSTANTS
# ========================================================================

# Define the team information with their characteristics
TEAM_INFO = {
    "EMBER": {"traits": ["Fiery", "Passionate", "Unstoppable"]},
    "TERRA": {"traits": ["Grounded", "Steady", "Resilient"]},
    "VEIL":  {"traits": ["Stealthy", "Scheming", "Mysterious"]},
    "AERIAL": {"traits": ["Free", "Inventive", "Adventurous"]},
    "HALO": {"traits": ["Bright", "Empathetic", "Unifying"]},
    "FLUX": {"traits": ["Adaptive", "Quick", "Resourceful"]},
    "NOVA": {"traits": ["Explosive", "Revolutionary", "Destructive"]},
    "TEMPO": {"traits": ["Methodical", "Precise", "Strategic"]}
}

# ========================================================================
#                  SECTION 2: GEMINI API CONFIGURATION
# ========================================================================

# Gemini API configuration for team quiz
GEMINI_MODEL = "gemini-2.0-flash"  # Using the fast version of Gemini 2.0

# Safety settings to ensure appropriate content for children
SAFETY_SETTINGS = [
    types.SafetySetting(
        category="HARM_CATEGORY_HARASSMENT",
        threshold="BLOCK_LOW_AND_ABOVE",  # Block most
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_HATE_SPEECH",
        threshold="BLOCK_LOW_AND_ABOVE",  # Block most
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
        threshold="BLOCK_LOW_AND_ABOVE",  # Block most
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_DANGEROUS_CONTENT",
        threshold="BLOCK_LOW_AND_ABOVE",  # Block most
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_CIVIC_INTEGRITY",
        threshold="BLOCK_LOW_AND_ABOVE",  # Block most
    ),
]

# Response schema for structured JSON output from Gemini
RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    enum=[],
    required=["questions"],
    properties={
        "questions": types.Schema(
            type=types.Type.ARRAY,
            description="List of quiz questions.",
            items=types.Schema(
                type=types.Type.OBJECT,
                enum=[],
                required=["question_text", "answer_choices"],
                properties={
                    "question_text": types.Schema(
                        type=types.Type.STRING,
                        description="The quiz question being asked.",
                    ),
                    "answer_choices": types.Schema(
                        type=types.Type.ARRAY,
                        description="Four answer choices.",
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            enum=[],
                            required=["choice_text", "corresponding_category"],
                            properties={
                                "choice_text": types.Schema(
                                    type=types.Type.STRING,
                                    description="The text of the answer choice.",
                                ),
                                "corresponding_category": types.Schema(
                                    type=types.Type.STRING,
                                    description="The category this choice corresponds to (filled by Gemini).",
                                ),
                            },
                        ),
                    ),
                },
            ),
        ),
    },
)

# ========================================================================
#                  SECTION 3: HELPER FUNCTIONS
# ========================================================================

def create_team_prompt(selected_teams):
    """Create a prompt for Gemini based on selected teams
    
    This function:
    1. Takes a list of selected team names
    2. Builds a detailed prompt describing the teams and requirements
    3. Returns the formatted prompt as a string
    
    Args:
        selected_teams (list): List of selected team names
        
    Returns:
        str: Formatted prompt for Gemini
    """
    # Validate that we have the right number of teams
    if not 2 <= len(selected_teams) <= 4:
        logger.warning(f"Invalid number of teams: {len(selected_teams)}. Must be 2-4 teams.")
        # Default to using all teams if invalid
        selected_teams = list(TEAM_INFO.keys())[:4]
        
    # Build a description of each selected team
    team_descriptions = []
    for team in selected_teams:
        if team in TEAM_INFO:
            traits = ", ".join(TEAM_INFO[team]["traits"])
            team_descriptions.append(f"{team} ({traits})")
        else:
            logger.warning(f"Unknown team name: {team}")
            
    teams_text = "; ".join(team_descriptions)
    
    # Create the full prompt
    prompt = f"""Generate 5 short, fun, personality-quiz style questions for players aged 8-18 in a Roblox game. 
Each question should have exactly {len(selected_teams)} answer choices, with each choice corresponding to one of these team personalities:
{teams_text}

Requirements:
1. Questions should be brief, clear, and age-appropriate
2. Each answer choice must correspond to ONE specific team from the list
3. Keep the corresponding_category strictly to one of: {", ".join(selected_teams)}
4. Each question should have exactly {len(selected_teams)} answer choices
5. Make questions relatable to young players (hobbies, school, friends, games, etc.)
6. Focus on personality traits, preferences, and situations
7. Use simple language appropriate for the age group
8. Avoid mature themes, complex situations, or overly abstract concepts

Example question format:
"What would you do if you found a secret door in your school?"
- "Burst through it immediately to see what's on the other side!" (EMBER)
- "Carefully examine it first and make a plan before proceeding." (TERRA)

Return exactly 5 questions in the specified JSON format, with each answer choice mapping to one team category.
"""
    return prompt

def get_gemini_quiz_response(selected_teams):
    """Generate quiz questions using Gemini API
    
    This function:
    1. Creates a prompt based on selected teams
    2. Calls the Gemini API with proper configuration
    3. Returns the structured JSON response
    
    Args:
        selected_teams (list): List of selected team names
        
    Returns:
        dict: JSON response from Gemini containing questions and answers
    """
    try:
        # Get API key from environment
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY environment variable not set")
            return None
            
        # Initialize the Gemini client
        client = genai.Client(api_key=api_key)
        
        # Create the prompt for Gemini
        prompt = create_team_prompt(selected_teams)
        logger.debug(f"Generated prompt for Gemini: {prompt[:100]}...")
        
        # Configure the generation parameters
        generate_content_config = types.GenerateContentConfig(
            temperature=0.65,  # Balanced between creativity and consistency
            top_p=0.9,
            top_k=40,
            max_output_tokens=1500,  # Generous limit for 5 questions
            safety_settings=SAFETY_SETTINGS,
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        )
        
        # Create the content for the API request
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            ),
        ]
        
        # Call the Gemini API
        logger.info("Calling Gemini API to generate quiz questions")
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=generate_content_config,
        )
        
        # Parse the response
        if response and response.text:
            try:
                # Parse the JSON response
                json_response = json.loads(response.text)
                logger.info(f"Successfully generated {len(json_response.get('questions', []))} quiz questions")
                return json_response
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Gemini response as JSON: {e}")
                logger.debug(f"Raw response: {response.text[:200]}...")
                return None
        else:
            logger.error("Empty response from Gemini API")
            return None
            
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        return None

# ========================================================================
#                  SECTION 4: MAIN PROCESSING FUNCTIONS
# ========================================================================

def process_team_quiz_request(teams_data):
    """Process a team quiz request
    
    This function:
    1. Validates the teams data
    2. Calls Gemini API to generate questions
    3. Formats the response for Roblox
    
    Args:
        teams_data (list): List of team names from Roblox
        
    Returns:
        dict: Formatted quiz data for Roblox, or error information
    """
    try:
        # Validate team names
        valid_teams = [team for team in teams_data if team in TEAM_INFO]
        
        if not valid_teams:
            logger.warning(f"No valid teams found in request: {teams_data}")
            return {
                "status": "error",
                "message": "No valid team names provided",
                "valid_teams": list(TEAM_INFO.keys())
            }
            
        if len(valid_teams) < 2 or len(valid_teams) > 4:
            logger.warning(f"Invalid number of teams: {len(valid_teams)}. Must be 2-4 teams.")
            return {
                "status": "error",
                "message": f"Invalid number of teams: {len(valid_teams)}. Must be 2-4 teams."
            }
            
        # Get quiz questions from Gemini
        quiz_data = get_gemini_quiz_response(valid_teams)
        
        if not quiz_data:
            return {
                "status": "error",
                "message": "Failed to generate quiz questions"
            }
            
        # Return the successfully generated quiz
        return {
            "status": "success",
            "message": "Quiz questions generated successfully",
            "quiz_data": quiz_data
        }
        
    except Exception as e:
        logger.error(f"Error processing team quiz request: {e}")
        return {
            "status": "error",
            "message": f"Internal error processing quiz: {str(e)}"
        } 