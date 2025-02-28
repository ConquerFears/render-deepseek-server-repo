###############################################################################
# TEAM QUIZ UTILITIES
###############################################################################

# Import required libraries
import os                    # For accessing environment variables
import json                  # For handling JSON data
import logging               # For logging errors and information

# Setup logging
logger = logging.getLogger(__name__)  # Create a logger for this module

# Try to import Google Generative AI library
# We wrap this in a try-except block to handle cases where the package isn't installed
GEMINI_AVAILABLE = False
try:
    import google.generativeai as genai  # Google's Gemini AI API client library
    GEMINI_AVAILABLE = True
    logger.info("Successfully imported google-generativeai package")
    
    # Get Gemini API key from environment variable
    GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")
    
    # Configure the Gemini API with our key
    if GOOGLE_API_KEY:
        genai.configure(api_key=GOOGLE_API_KEY)
    
    # Gemini API configuration for team quiz
    GEMINI_MODEL = "gemini-2.0-flash"  # Using the fast version of Gemini 2.0

    # Safety settings to ensure appropriate content for children
    SAFETY_SETTINGS = [
        {
            "category": "HARM_CATEGORY_HARASSMENT",
            "threshold": "BLOCK_LOW_AND_ABOVE",  # Block most
        },
        {
            "category": "HARM_CATEGORY_HATE_SPEECH",
            "threshold": "BLOCK_LOW_AND_ABOVE",  # Block most
        },
        {
            "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "threshold": "BLOCK_LOW_AND_ABOVE",  # Block most
        },
        {
            "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
            "threshold": "BLOCK_LOW_AND_ABOVE",  # Block most
        },
        {
            "category": "HARM_CATEGORY_CIVIC_INTEGRITY",
            "threshold": "BLOCK_NONE",  # Block most
        },
    ]

    # Response schema for structured JSON output from Gemini
    RESPONSE_SCHEMA = {
        "type": "OBJECT",
        "required": ["questions"],
        "properties": {
            "questions": {
                "type": "ARRAY",
                "description": "List of quiz questions.",
                "items": {
                    "type": "OBJECT",
                    "required": ["question_text", "answer_choices"],
                    "properties": {
                        "question_text": {
                            "type": "STRING",
                            "description": "The quiz question being asked.",
                        },
                        "answer_choices": {
                            "type": "ARRAY",
                            "description": "Four answer choices.",
                            "items": {
                                "type": "OBJECT",
                                "required": ["choice_text", "corresponding_category"],
                                "properties": {
                                    "choice_text": {
                                        "type": "STRING",
                                        "description": "The text of the answer choice.",
                                    },
                                    "corresponding_category": {
                                        "type": "STRING",
                                        "description": "The category this choice corresponds to (filled by Gemini).",
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }
except ImportError:
    logger.error("Cannot import google-generativeai. This functionality will be disabled.")
    logger.error("Please install with: pip install google-generativeai")

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

# Gemini API configuration moved into the try-except block above

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

def get_fallback_quiz_questions(selected_teams):
    """Generate predefined fallback quiz questions when Gemini API is not available
    
    This function:
    1. Takes a list of selected team names
    2. Returns a set of predefined questions with answer choices mapped to teams
    
    Args:
        selected_teams (list): List of selected team names
        
    Returns:
        dict: JSON structure with fallback quiz questions
    """
    logger.info("Using fallback quiz questions (Gemini API unavailable)")
    
    # Ensure we have 2-4 valid teams
    valid_teams = [team for team in selected_teams if team in TEAM_INFO]
    if len(valid_teams) < 2:
        # If we don't have enough valid teams, use the first teams from our list
        valid_teams = list(TEAM_INFO.keys())[:4]
    elif len(valid_teams) > 4:
        # If we have too many teams, use just the first 4
        valid_teams = valid_teams[:4]
    
    # Predefined questions that work with any combination of teams
    fallback_questions = [
        {
            "question_text": "What would you do if you found a secret door in your school?",
            "answer_choices": []
        },
        {
            "question_text": "How do you approach solving a difficult puzzle?",
            "answer_choices": []
        },
        {
            "question_text": "What's your strategy when playing a team game?",
            "answer_choices": []
        },
        {
            "question_text": "What would you do with a day off from school?",
            "answer_choices": []
        },
        {
            "question_text": "How do you react when something doesn't go as planned?",
            "answer_choices": []
        }
    ]
    
    # Answer choices for each team
    team_answers = {
        "EMBER": [
            "Burst through immediately to see what's on the other side!",
            "Try every approach rapidly until something works!",
            "Lead the charge and inspire everyone with energy!",
            "Go on an adventure, trying as many exciting activities as possible!",
            "Jump into fixing it immediately with determination!"
        ],
        "TERRA": [
            "Carefully examine it first and make a plan before proceeding.",
            "Break it down into smaller parts and solve methodically.",
            "Create a solid foundation for my team to build upon.",
            "Spend time in nature or working on a meaningful project.",
            "Stay calm and develop a practical solution step by step."
        ],
        "VEIL": [
            "Watch from a distance first to see if others notice it.",
            "Look for hidden patterns and unexpected connections.",
            "Analyze the other team's strategy and find their weaknesses.",
            "Research something fascinating that others don't know about.",
            "Quietly observe and plan a different approach nobody expects."
        ],
        "AERIAL": [
            "Think of creative ways to use the door for something fun!",
            "Try unusual approaches nobody else would think of.",
            "Come up with unexpected strategies that surprise everyone.",
            "Create something original or explore somewhere new.",
            "See it as an opportunity to try something completely different!"
        ],
        "HALO": [
            "Tell friends so we can explore it together safely.",
            "Ask others for input to find the best solution together.",
            "Make sure everyone on the team feels included and valued.",
            "Spend time connecting with friends and helping others.",
            "Find a solution that makes everyone feel better about the situation."
        ],
        "FLUX": [
            "Gather information quickly and adapt my approach as needed.",
            "Try different approaches and adjust based on what works.",
            "Switch roles whenever needed to help the team succeed.",
            "Keep my options open and change plans based on what seems most interesting.",
            "Quickly adjust my expectations and find a new opportunity."
        ],
        "NOVA": [
            "Create a dramatic reveal and invite everyone to see what I found!",
            "Challenge the conventional methods and create a breakthrough solution.",
            "Completely change how the game is played with bold moves.",
            "Do something that completely transforms my usual routine.",
            "Use this as a chance to completely transform the situation!"
        ],
        "TEMPO": [
            "Create a detailed plan for exploring it safely and efficiently.",
            "Work through it step-by-step with careful attention to detail.",
            "Create a precise strategy and ensure everyone follows it.",
            "Schedule my time carefully to accomplish specific goals.",
            "Analyze what went wrong and create a detailed plan to prevent it happening again."
        ]
    }
    
    # Build answer choices for each question based on selected teams
    for i, question in enumerate(fallback_questions):
        for team in valid_teams:
            if team in team_answers:
                question["answer_choices"].append({
                    "choice_text": team_answers[team][i],
                    "corresponding_category": team
                })
    
    return {"questions": fallback_questions}

def get_gemini_quiz_response(selected_teams):
    """Generate quiz questions using Gemini API
    
    This function:
    1. Creates a prompt based on selected teams
    2. Calls the Gemini API with proper configuration
    3. Returns the structured JSON response
    
    Args:
        selected_teams (list): List of selected team names
        
    Returns:
        dict: JSON response from Gemini containing questions and answers,
              or None if the API call fails or package is not available
    """
    # Check if Gemini API is available
    if not GEMINI_AVAILABLE:
        logger.error("Cannot generate quiz: google-generativeai package is not installed")
        return get_fallback_quiz_questions(selected_teams)
        
    try:
        # Check if API key is configured
        if not os.environ.get("GEMINI_API_KEY"):
            logger.error("GEMINI_API_KEY environment variable not set")
            return get_fallback_quiz_questions(selected_teams)
            
        # Create the prompt for Gemini
        prompt = create_team_prompt(selected_teams)
        logger.debug(f"Generated prompt for Gemini: {prompt[:100]}...")
        
        # Create a model using the same pattern as the working gemini_utils.py
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            generation_config={
                "temperature": 0.65,
                "top_p": 0.9,
                "top_k": 40,
                "max_output_tokens": 1500,
                "response_mime_type": "application/json",
            },
            safety_settings=SAFETY_SETTINGS
        )
        
        # Call the Gemini API
        logger.info("Calling Gemini API to generate quiz questions")
        response = model.generate_content(
            contents=[
                {"role": "user", "parts": [prompt]}
            ],
            generation_config={"response_schema": RESPONSE_SCHEMA}
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
                return get_fallback_quiz_questions(selected_teams)
        else:
            logger.error("Empty response from Gemini API")
            return get_fallback_quiz_questions(selected_teams)
            
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        return get_fallback_quiz_questions(selected_teams)

# ========================================================================
#                  SECTION 4: MAIN PROCESSING FUNCTIONS
# ========================================================================

def process_team_quiz_request(teams_data):
    """Process a team quiz request
    
    This function:
    1. Validates the teams data
    2. Calls Gemini API to generate questions (or uses fallback questions)
    3. Formats the response for Roblox
    
    Args:
        teams_data (list): List of team names from Roblox
        
    Returns:
        dict: Formatted quiz data for Roblox, or error information
    """
    try:
        # Inform if Gemini API is unavailable, but continue with fallback
        if not GEMINI_AVAILABLE:
            logger.warning("Team quiz using fallback questions: google-generativeai package not installed")
            # We'll continue with fallback questions instead of failing completely
            
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
            
        # Get quiz questions from Gemini (or fallback if Gemini unavailable)
        quiz_data = get_gemini_quiz_response(valid_teams)
        
        if not quiz_data:
            # This should never happen since we're using fallback questions,
            # but let's handle it just in case
            return {
                "status": "error",
                "message": "Failed to generate quiz questions"
            }
            
        # Return the successfully generated quiz
        status_message = "Quiz questions generated successfully"
        if not GEMINI_AVAILABLE:
            status_message += " (using fallback questions)"
            
        return {
            "status": "success",
            "message": status_message,
            "quiz_data": quiz_data,
            "using_fallback": not GEMINI_AVAILABLE
        }
        
    except Exception as e:
        logger.error(f"Error processing team quiz request: {e}")
        return {
            "status": "error",
            "message": f"Internal error processing quiz: {str(e)}"
        } 