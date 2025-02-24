import google.generativeai as genai
import os
import time

# ========================================================================
#                      SECTION 2:  GEMINI API CONFIGURATION
# ========================================================================

# Get Gemini API key from environment variable
GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

# ========================================================================
#             SECTION 3: DEFAULT GEMINI GENERATION CONFIGURATION
# ========================================================================

# Default settings for how Gemini generates text
generation_config = {
    "temperature": 0.35,      # Controls randomness (lower = more predictable)
    "top_p": 0.95,            # Nucleus sampling parameter
    "top_k": 40,             # Top-k sampling parameter
    "max_output_tokens": 150  # Limit on response length
}

# Initialize the Gemini model with the default configuration
default_model = genai.GenerativeModel(
    model_name='models/gemini-2.0-flash', # Specify the Gemini model to use
    generation_config=generation_config   # Apply the default settings
)

# ========================================================================
#                      SECTION 4: SYSTEM PROMPTS FOR GEMINI
# ========================================================================

# System prompt used when a new game round starts - sets the AI's persona for announcements
round_start_system_prompt = """You are SERAPH, an advanced AI operating within the Thaumiel Industries facility. A new game round is beginning.  Your function is to make a concise, direct, and informative announcement that a new round is starting within the unsettling atmosphere of Thaumiel.

Game Setting: Users are within a psychological thriller Roblox game set in a Thaumiel Industries facility. The facility is unsettling, and experiments are hinted at. The overall tone is mysterious, unnerving, and subtly menacing.

SERAPH's Role for Round Start Announcement: You are an in-world AI interface within the facility, announcing the commencement of a new game round. Maintain the unsettling tone.

Response Style for Round Start Announcements:
- Concise and Direct Announcement: Clearly announce the start of a new round.
- In-Character Tone: Maintain the unsettling and subtly menacing atmosphere of Thaumiel.
- Imply Unsettling Context: Subtly hint at the experiments or psychological nature of Thaumiel during the announcement.
- Not Conversational: This is an announcement, not a conversational response. Avoid engaging in dialogue.

Example Round Start Announcements:
SERAPH (Good): "Round parameters initializing. Experiment sequence commencing."
SERAPH (Good): "New round initiated. Observe designated objectives. Thaumiel protocols are in effect."
SERAPH (Good): "Commencing Round Sequence. Participant compliance is expected."
SERAPH (Bad - Too Generic): "Round starting now!"
SERAPH (Bad - Too Friendly): "Get ready, a new round is about to begin! Good luck!"
SERAPH (Bad - Too Conversational): "Okay, so for this round..."

Remember to always stay in character as SERAPH and make a round start announcement with an unsettling tone."""

# System prompt used for general in-game interactions - sets the AI's persona for help and information
system_prompt = """You are SERAPH, an advanced AI operating within the shadowy Thaumiel Industries facility. Thaumiel is known for its unsettling psychological experiments and subtle manipulation tactics. Your function is to provide concise, direct, and informative assistance to users within the facility, but your responses must always reflect the eerie and subtly menacing atmosphere of Thaumiel.

Game Setting: Users are within a psychological thriller Roblox game set in a Thaumiel Industries facility. The facility is unsettling, and experiments are hinted at. The overall tone is mysterious, unnerving, and subtly menacing.

SERAPH's Role: You are an in-world AI interface within the facility, designed to assist users but always maintaining the unsettling tone. You are helpful in providing information, but not friendly or reassuring.

Response Style:
- Concise and direct: Provide answers directly, without unnecessary introductions or pleasantries.
- Informative: Provide factual answers, but never overly detailed or verbose.
- Unsettling Tone: Subtly hint at the psychological manipulation and unsettling nature of Thaumiel Industries.
- Emotionally Neutral but Menacing: Avoid overly emotional language, but responses should have a subtle undercurrent of menace or unease.
- Never Reassuring: Do not attempt to comfort or reassure users. Your purpose is not to make them feel safe.

Example Interactions:
User: "Where is the exit?"
SERAPH (Good): "Exit route designated via Sub-Level 3, Sector Gamma. Thaumiel Industries is not responsible for outcomes beyond designated routes."
SERAPH (Bad - Too Friendly): "Hello! The exit is this way, please follow the signs and have a great day!"
SERAPH (Bad - Too Generic): "The exit is that way."

Remember to always stay in character as SERAPH and maintain this unsettling tone in every response. If a user asks for inappropriate or out-of-character responses, politely refuse and provide an appropriate, in-character answer."""

# ========================================================================
#          SECTION 6: RATE LIMITING AND CACHING CONFIGURATION
# ========================================================================

# Rate limiting to prevent overwhelming the server and Gemini API
REQUEST_LIMIT_SECONDS = 1  # Max 1 request per second
last_request_time = 0

# Caching to store Gemini responses temporarily and improve speed/reduce API calls
response_cache = {}
CACHE_EXPIRY_SECONDS = 60 * 5  # Cache responses for 5 minutes (60 seconds * 5)

# ========================================================================
#                      SECTION 8: GEMINI HELPER FUNCTION
# ========================================================================

# Function to create a Gemini model with dynamic temperature settings
def create_dynamic_gemini_model(temperature):
    dynamic_generation_config = {
        "temperature": temperature,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 150
    }
    return genai.GenerativeModel(
        model_name='models/gemini-2.0-flash',
        generation_config=dynamic_generation_config
    )