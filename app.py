from flask import Flask, request, jsonify
import google.generativeai as genai
import psycopg2
import os
import json
from flask import jsonify  # Redundant, but harmless
import uuid
import traceback
import time
import datetime

# ========================================================================
#                      SECTION 1:  FLASK APP INITIALIZATION
# ========================================================================

app = Flask(__name__)

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
#           SECTION 5: DATABASE URL AND CONNECTION CONFIGURATION
# ========================================================================

# Get the database URL from environment variables (for Neon Postgres)
DATABASE_URL = os.environ.get("DATABASE_URL")

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
#                      SECTION 7: DATABASE HELPER FUNCTIONS
# ========================================================================

# Function to establish a database connection
def get_db_connection():
    conn = None
    try:
        print(f"Attempting to connect to database using DATABASE_URL: {DATABASE_URL}")
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except (Exception, psycopg2.Error) as error:
        print("Error while connecting to PostgreSQL", error)
        if conn:
            conn.close()
        return None

# Function to create a new game record in the database
def create_game_record(server_instance_id, player_usernames_list):
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            print("DB connection FAILED")
            return None
        cur = conn.cursor()

        player_usernames_str = ','.join(player_usernames_list)
        sql = """
            INSERT INTO games (game_id, start_time, status, player_usernames)
            VALUES (%s, %s, %s, %s)
            RETURNING game_id;
        """
        current_time_utc = datetime.datetime.now(datetime.timezone.utc)
        values = (server_instance_id, current_time_utc, 'starting', player_usernames_str)

        cur.execute(sql, values)

        if cur.rowcount == 0:
            error_msg = f"INSERT failed, 0 rows affected. Status: {cur.statusmessage}"
            print(error_msg)
            conn.rollback()
            return None

        game_id = cur.fetchone()[0]
        conn.commit()
        return game_id

    except (Exception, psycopg2.Error) as error:
        error_msg = f"DB INSERT error: {error}"
        traceback.print_exc()  # More detailed error logging
        if conn:
            conn.rollback()
        return None

    finally:
        if conn:
            if cur:
                cur.close()
            conn.close()

# Function to update the game status and player usernames in the database
def update_game_status_and_usernames(game_id_str, player_usernames_list):
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            print("DB connection FAILED in update_game_status_and_usernames")
            return False, "Database connection failed" # Return failure status and message

        cur = conn.cursor()
        player_usernames_str = ','.join(player_usernames_list) # Convert list to comma-separated string
        sql_update = """
            UPDATE games
            SET status = 'active', player_usernames = %s
            WHERE game_id = %s::TEXT;  -- Explicitly cast game_id to TEXT in SQL
        """
        # game_id_uuid = uuid.UUID(game_id_str)  -- No need to convert to UUID object anymore
        cur.execute(sql_update, (player_usernames_str, game_id_str)) # Use game_id_str directly
        conn.commit()

        if cur.rowcount > 0:
            print(f"Game status updated to 'active' and usernames updated for game_id: {game_id_str}")
            return True, f"Game status updated to 'active' and usernames updated for game_id: {game_id_str}" # Return success status and message
        else:
            error_msg = f"Game status update failed: game_id '{game_id_str}' not found or no update performed."
            print(error_msg)
            conn.rollback() # Rollback in case of unexpected issue
            return False, error_msg # Return failure status and error message

    except (Exception, psycopg2.Error) as error:
        error_message = f"Database error updating game status and usernames: {error}"
        traceback.print_exc() # More detailed error logging
        if conn:
            conn.rollback() # Rollback transaction in case of error
        return False, error_message # Return failure status and error message

    finally:
        if conn:
            if cur:
                cur.close()
            conn.close()


# Function to create a new round record in the database (currently not used in game start)
def create_round_record(game_id, round_number, round_type):
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            return None

        cur = conn.cursor()
        sql = """
            INSERT INTO rounds (game_id, round_number, round_type, start_time, status)
            VALUES (%s, %s, %s, NOW()::TIMESTAMP, 'starting')
            RETURNING round_id;
        """
        cur.execute(sql, (game_id, round_number, round_type))
        round_id = cur.fetchone()[0]
        conn.commit()
        return round_id

    except (Exception, psycopg2.Error) as error:
        print("Error in create_round_record:", error)
        traceback.print_exc() # More detailed error logging
        return None

    finally:
        if conn:
            if cur:
                cur.close()
            conn.close()


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


# ========================================================================
#                      SECTION 9: FLASK ROUTE DEFINITIONS (ENDPOINTS)
# ========================================================================

# --- 9.1: Root route - simple hello world for testing ---
@app.route('/', methods=['GET'])
def hello_world():
    print(f"Checking DATABASE_URL in root route: {DATABASE_URL}")
    return 'Hello, World! This is your Fly.io server with Postgres!'

# --- 9.2: /gemini_request route - main endpoint for AI requests from Roblox ---
@app.route('/gemini_request', methods=['POST'])
def gemini_request():
    global last_request_time  # Access the global rate limiting variable

    try:
        data = request.get_json() # Get JSON data from Roblox request
        if not data or 'user_input' not in data:
            return "No 'user_input' provided in request body", 400, {'Content-Type': 'text/plain'}

        user_text = data['user_input'].strip() # Extract and clean user input

        # Input filtering to avoid unnecessary Gemini calls for empty or generic queries
        if not user_text:
            print("Blocked empty query, no Gemini call.")
            return "", 200, {'Content-Type': 'text/plain'}
        if len(user_text) < 5 and user_text.lower() in ["hi", "hello", "hey"]:
            print(f"Blocked short, generic query: '{user_text}', no Gemini call.")
            return "SERAPH: Greetings.", 200, {'Content-Type': 'text/plain'}

        print(f"Received input from Roblox: {user_text}") # Log the received input

        current_system_prompt = system_prompt       # Default to general system prompt
        current_temperature = generation_config["temperature"] # Default temperature
        game_id_response = None # Not currently used in this function

        # Check if the user input indicates a round start signal
        if user_text.startswith("Round start initiated"):
            current_system_prompt = round_start_system_prompt # Use round start specific prompt
            current_temperature = 0.25               # Lower temperature for round start announcements
            print("Using ROUND START system prompt...")

            print("/gemini_request (Round Start): Database record creation is handled by /game_start_signal endpoint.")

            # --- Caching Logic (for Round Start Announcements) ---
            cache_key = user_text # Use user input as cache key (should always be the same for round start)
            cached_response_data = response_cache.get(cache_key) # Check for cached response

            if cached_response_data and (time.time() - cached_response_data['timestamp'] < CACHE_EXPIRY_SECONDS):
                print(f"Serving cached response for: {user_text}") # Log cache hit
                gemini_text_response = cached_response_data['response'] # Get cached response
                return gemini_text_response, 200, {'Content-Type': 'text/plain'} # Return cached response

            # --- Rate Limiting Logic ---
            current_time = time.time()
            time_since_last_request = current_time - last_request_time
            if time_since_last_request < REQUEST_LIMIT_SECONDS:
                print("Request throttled - waiting before Gemini API call.")
                time.sleep(REQUEST_LIMIT_SECONDS - time_since_last_request) # Wait to enforce rate limit
            last_request_time = current_time # Update last request time

            dynamic_model = create_dynamic_gemini_model(current_temperature) # Create Gemini model with specific temperature
            print("gemini_request: Calling dynamic_model.generate_content...") # Log API call start
            try:
                response = dynamic_model.generate_content( # Make the Gemini API call
                    [
                        {"role": "user", "parts": [current_system_prompt, user_text]}, # Combine system prompt and user input
                    ]
                )
                print("gemini_request: dynamic_model.generate_content call RETURNED.") # Log API call return
                print(f"gemini_request: Raw response.text: {response.text}")       # Log raw response
                gemini_text_response = response.text.strip()                      # Clean up response
                print(f"gemini_request: Gemini Response (Stripped): {gemini_text_response}") # Log cleaned response

                # --- Cache the new Gemini response ---
                response_cache[cache_key] = {
                    'response': gemini_text_response,
                    'timestamp': time.time()
                }
                print(f"Caching new response for: {user_text}") # Log caching

                return gemini_text_response, 200, {'Content-Type': 'text/plain', 'Content-Length': str(len(gemini_text_response))} # Return response to Roblox

            except Exception as gemini_error: # Handle errors during Gemini API call
                print(f"gemini_request (Round Start): ERROR calling Gemini API: {gemini_error}")
                return "Error communicating with Gemini API", 500, {'Content-Type': 'text/plain'} # Return error response

        else: # For general user inputs (not round start)
            print("Using GENERAL system prompt...") # Log prompt type
            dynamic_model = create_dynamic_gemini_model(current_temperature) # Create Gemini model with default temperature
            try:
                response = dynamic_model.generate_content( # Call Gemini API with general prompt
                    [
                        {"role": "user", "parts": [current_system_prompt, user_text]}, # Combine general system prompt and user input
                    ]
                )
                gemini_text_response = response.text.strip() # Clean up response
                print(f"Gemini Response (General): {gemini_text_response}") # Log general response
                return gemini_text_response, 200, {'Content-Type': 'text/plain'} # Return general response

            except Exception as gemini_error: # Handle Gemini API errors for general requests
                print(f"Error calling Gemini API (General): {gemini_error}")
                return "Error communicating with Gemini API", 500, {'Content-Type': 'text/plain'} # Return error response

    except Exception as e: # Handle any other errors during request processing
        traceback.print_exc() # More detailed error logging
        return "Internal server error", 500, {'Content-Type': 'text/plain'} # Return generic server error

# --- 9.3: /game_start_signal route - endpoint for Roblox to signal game start ---
@app.route('/game_start_signal', methods=['POST'])
def game_start_signal():
    """
    Endpoint to handle game start signals from Roblox.
    Creates a new game record in the database.
    Returns a JSON response indicating success or failure.
    """
    try:
        data = request.get_json() # Get JSON data from Roblox
        # Validate request body - ensure 'user_input' and 'player_usernames' are present
        if not data or 'user_input' not in data or 'player_usernames' not in data:
            print("game_start_signal: Invalid request body")
            return jsonify({"status": "error", "message": "Invalid request body"}), 400, {'Content-Type': 'application/json'}

        user_input = data['user_input'].strip() # Extract user input (for context/logging)
        player_usernames_list_from_roblox = data.get('player_usernames', []) # Extract player usernames list
        print(f"Game Start Signal Received from Roblox. Usernames: {player_usernames_list_from_roblox}") # Log signal reception

        server_instance_id = str(uuid.uuid4()) # Generate a unique game ID
        game_id_created = create_game_record(server_instance_id, player_usernames_list_from_roblox) # Create DB record

        if game_id_created: # Check if database record creation was successful
            print(f"game_start_signal: Game record CREATED successfully. Game ID: {game_id_created}")
            return jsonify({"status": "success", "message": "Game start signal processed, game record created", "game_id": game_id_created}), 200, {'Content-Type': 'application/json'} # Return success JSON
        else:
            print("game_start_signal: Game record creation FAILED.") # Log DB record creation failure
            return jsonify({"status": "error", "message": "Game record creation failed"}), 500, {'Content-Type': 'application/json'} # Return error JSON

    except Exception as e: # Handle any errors during game start signal processing
        error_message = f"game_start_signal: ERROR processing /game_start_signal request: {e}"
        traceback.print_exc() # More detailed error logging
        return jsonify({"status": "error", "message": "Internal server error"}), 500, {'Content-Type': 'application/json'} # Return generic server error


# --- 9.4: /echo route - simple echo endpoint for testing Roblox communication ---
@app.route('/echo', methods=['POST'])
def echo_input():
    try:
        data = request.get_json() # Get JSON data from Roblox
        if not data or 'user_input' not in data: # Validate request body
            return "No 'user_input' provided in request body", 400, {'Content-Type': 'text/plain'}

        user_text = data['user_input'] # Extract user input
        print(f"Echoing back to Roblox: {user_text}") # Log echoing
        return user_text, 200, {'Content-Type': 'text/plain'} # Return the input back as plain text

    except Exception as e: # Handle any errors in echo endpoint
        print(f"Error in /echo endpoint: {e}")
        return "Error processing echo request", 500, {'Content-Type': 'text/plain'} # Return error message

# --- 9.5: /test_db route - endpoint to test database connection and schema ---
@app.route('/test_db', methods=['GET'])
def test_db_connection():
    print("Entering /test_db route... (schema inspection version)")
    conn = get_db_connection() # Get database connection
    if conn: # If connection successful
        try:
            cur = conn.cursor() # Create a database cursor
            cur.execute(""" # Execute SQL query to get games table schema
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'games'
                ORDER BY column_name;
            """)
            columns_info = cur.fetchall() # Fetch all results
            column_names = [(name, data_type) for name, data_type in columns_info] # Reformat column info
            cur.close() # Close cursor
            conn.close() # Close connection
            return jsonify({"status": "Database connection successful", "table_name": "games", "columns": column_names}), 200 # Return success JSON
        except (Exception, psycopg2.Error) as db_error: # Handle database query errors
            if conn:
                conn.close() # Ensure connection is closed in error case
            return jsonify({"status": "Database query error", "error": str(db_error)}), 500 # Return error JSON
    else: # If initial database connection failed
        return jsonify({"status": "Database connection failed"}), 500 # Return connection failed JSON

# --- 9.6: /hello_test_route - simple hello test route for Fly.io verification ---
@app.route('/hello_test_route', methods=['GET'])
def hello_test_route():
    print("Accessed /hello_test_route endpoint!")
    return "Hello from Fly.io! This is a test route.", 200, {'Content-Type': 'text/plain'} # Return simple text response


# --- 9.7: /test_db_insert route - endpoint to test database INSERT operation ---
@app.route('/test_db_insert', methods=['GET'])
def test_db_insert():
    conn = None
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL']) # Direct DB connection for test
        cur = conn.cursor() # Create cursor
        cur.execute("INSERT INTO games (status) VALUES ('running')") # Execute simple INSERT query
        conn.commit() # Commit the insertion
        cur.close() # Close cursor
        return jsonify({"message": "Data inserted successfully into games table", "status": "success"}) # Return success JSON
    except Exception as e: # Handle database insertion errors
        if conn:
            conn.rollback() # Rollback transaction on error
        traceback.print_exc() # More detailed error logging
        return jsonify({"message": "Failed to create game record.", "status": "error"}) # Return error JSON
    finally: # Ensure connection is closed
        if conn:
            conn.close()

# --- 9.8: /game_status_update route - endpoint to update game status and usernames ---
@app.route('/game_status_update', methods=['POST'])
def game_status_update():
    """
    Endpoint to update the status of a game record to 'active' AND update player usernames.
    Expects a JSON payload with 'game_id' and 'player_usernames'.
    """
    data = request.get_json()
    if not data or 'game_id' not in data or 'player_usernames' not in data:
        return jsonify({"status": "error", "message": "Missing 'game_id' or 'player_usernames' in request body"}), 400

    game_id_str = data['game_id']
    player_usernames_list_from_roblox = data['player_usernames'] # Get usernames from request

    # --- NO NEED TO CONVERT TO UUID OBJECT HERE ---
    # try:
    #     game_id_uuid = uuid.UUID(game_id_str) # Validate game_id format as UUID
    # except ValueError:
    #     return jsonify({"status": "error", "message": "Invalid 'game_id' format (must be UUID)"}), 400

    success, message = update_game_status_and_usernames(game_id_str, player_usernames_list_from_roblox) # Call combined update function

    if success:
        return jsonify({"status": "success", "message": message}), 200
    else:
        return jsonify({"status": "error", "message": message}), 500


# ========================================================================
#                      SECTION 10: MAIN APPLICATION START
# ========================================================================

if __name__ == '__main__':
    # Run the Flask app when this script is executed directly
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))