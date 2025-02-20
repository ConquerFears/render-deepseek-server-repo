from flask import Flask, request, jsonify
import google.generativeai as genai
import psycopg2
import os
import json  # <--- IMPORT json MODULE
from flask import jsonify

app = Flask(__name__)

# Configure Gemini API
GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")  # Get API key from environment
genai.configure(api_key=GOOGLE_API_KEY)

# --- Generation Configuration (default) ---
generation_config = {
    "temperature": 0.35,  # Default temperature for general chat
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 150 # Keep token limit concise
}

# Initialize Gemini Model with the default configuration
model = genai.GenerativeModel(
    model_name='models/gemini-2.0-flash', # Double check this model name is correct in Gemini API docs
    generation_config=generation_config
)

# --- System Prompts ---

round_start_system_prompt = """You are SERAPH, an advanced AI operating within the Thaumiel Industries facility. A new game round is beginning.  Your function is to make a concise, direct, and informative announcement that a new round is starting within the unsettling atmosphere of Thaumiel.

Game Setting: Users are within a psychological thriller Roblox game set in a Thaumiel Industries facility. The facility is unsettling, and experiments are hinted at. The overall tone is mysterious, unnervering, and subtly menacing.

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

DATABASE_URL = os.environ.get("DATABASE_URL")  # CORRECT WAY to get DATABASE_URL from env variable

def get_db_connection():  # Function to get a database connection
    conn = None
    try:
        print(f"Attempting to connect to database using DATABASE_URL: {DATABASE_URL}") # Log the DATABASE_URL directly
        conn = psycopg2.connect(DATABASE_URL)  # Connect using the URL from env
        return conn
    except (Exception, psycopg2.Error) as error:
        print("Error while connecting to PostgreSQL", error)
        if conn:
            conn.close()  # Close connection in case of error
        return None

@app.route('/', methods=['GET'])
def hello_world():
    print(f"Checking DATABASE_URL in root route: {DATABASE_URL}") # Log DATABASE_URL in root route
    return 'Hello, World! This is your Fly.io server with Postgres!' # Updated message

@app.route('/gemini_request', methods=['POST'])
def gemini_request():
    try:
        data = request.get_json()
        if not data or 'user_input' not in data:
            return "No 'user_input' provided in request body", 400, {'Content-Type': 'text/plain'}

        user_text = data['user_input']
        print(f"Received input from Roblox: {user_text}")

        current_system_prompt = system_prompt # Default to your general system prompt
        current_temperature = generation_config["temperature"] # Use default temperature

        if user_text.startswith("Round start initiated"): # <---- Check for "Round start" trigger
            current_system_prompt = round_start_system_prompt # Use round start system prompt
            current_temperature = 0.25 # Lower temperature for round start announcements (adjust as needed)
            print("Using ROUND START system prompt...") # Log when round start prompt is used
        else:
            print("Using GENERAL system prompt...") # Log when general prompt is used


        # --- Generation Configuration (now dynamic temperature) ---
        dynamic_generation_config = {
            "temperature": current_temperature,  # Use dynamically set temperature
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 150 # Keep token limit concise
        }
        dynamic_model = genai.GenerativeModel(
            model_name='models/gemini-2.0-flash',
            generation_config=dynamic_generation_config # Use dynamic config
        )


        try:
            response = dynamic_model.generate_content( # Use dynamic_model with dynamic config
                [
                    {"role": "user", "parts": [current_system_prompt, user_text]},  # Combined prompt with dynamic system prompt
                ]
            )
            gemini_text_response = response.text.strip()
            print(f"Gemini Response: {gemini_text_response}")
            return gemini_text_response, 200, {'Content-Type': 'text/plain'}

        except Exception as gemini_error:
            print(f"Error calling Gemini API: {gemini_error}")
            return "Error communicating with Gemini API", 500, {'Content-Type': 'text/plain'}

    except Exception as e:
        print(f"Error processing request: {e}")
        return "Internal server error", 500, {'Content-Type': 'text/plain'}

@app.route('/echo', methods=['POST'])
def echo_input():
    try:
        data = request.get_json()
        if not data or 'user_input' not in data:
            return "No 'user_input' provided in request body", 400, {'Content-Type': 'text/plain'}

        user_text = data['user_input']
        print(f"Echoing back to Roblox: {user_text}")
        return user_text, 200, {'Content-Type': 'text/plain'}

    except Exception as e:
        print(f"Error in /echo endpoint: {e}")
        return "Error processing echo request", 500, {'Content-Type': 'text/plain'}

@app.route('/test_db', methods=['GET'])
def test_db_connection():
    print("Entering /test_db route...")  # <--- ADD THIS LINE
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1;")
            result = cur.fetchone()
            cur.close()
            conn.close()
            return jsonify({"status": "Database connection successful", "result": result}), 200
        except (Exception, psycopg2.Error) as db_error:
            if conn:
                conn.close()
            return jsonify({"status": "Database query error", "error": str(db_error)}), 500
    else:
        return jsonify({"status": "Database connection failed"}), 500

@app.route('/hello_test_route', methods=['GET'])
def hello_test_route():
    print("Accessed /hello_test_route endpoint!") # Log when this route is hit
    return "Hello from Fly.io! This is a test route.", 200, {'Content-Type': 'text/plain'}

def create_game_record(server_instance_id, game_settings_data):
    """
    Inserts a new game record into the 'games' table.

    Args:
        server_instance_id (str): Unique identifier for the server instance.
        game_settings (dict): Dictionary of game settings (e.g., difficulty, map).

    Returns:
        str: The game_id of the newly created game record if successful, None on error.
    """
    conn = None
    print("create_game_record: Function started")  # ADDED: Function entry log

    try:
        print("create_game_record: Getting DB connection...")  # ADDED: Before connection attempt
        conn = get_db_connection()
        if conn is None:
            print("create_game_record: DB connection FAILED - get_db_connection returned None") # ADDED: Connection failure log
            return None
        print("create_game_record: DB connection SUCCESSFUL") # ADDED: Connection success log

        cur = conn.cursor()
        sql = """
            INSERT INTO games (game_id, settings, start_time, player_count, status, last_updated)
            VALUES (%s, %s, NOW()::TIMESTAMP, %s, %s, NOW()::TIMESTAMP)
            RETURNING game_id;
        """
        values = (server_instance_id, json.dumps(game_settings_data), 0, 'starting') #Example Player count and status
        print(f"create_game_record: Executing SQL Query (INSERT game record): {sql} with values: {values}") # ADDED: Before execute
        cur.execute(sql, values)
        print("create_game_record: SQL query executed successfully") # ADDED: After execute

        game_id = cur.fetchone()[0]
        conn.commit()
        print(f"create_game_record: Commit successful, game_id: {game_id}") # ADDED: After commit
        return game_id

    except (Exception, psycopg2.Error) as error:
        print("create_game_record: ERROR in INSERT operation:", error) # MODIFIED: More specific error log
        return None

    finally:
        print("create_game_record: Entering finally block") # ADDED: Finally block entry log
        if conn:
            print("create_game_record: Closing cursor and connection") # ADDED: Before closing
            if cur:
                cur.close()
            conn.close()
        else:
            print("create_game_record: Connection was None in finally block - nothing to close") # ADDED: Connection was None log
        print("create_game_record: Exiting finally block") # ADDED: Finally block exit log

def create_round_record(game_id, round_number, round_type):
    """
    Inserts a new round record into the 'rounds' table.

    Args:
        game_id (int): The game_id of the game this round belongs to.
        round_number (int): The round number within the game.
        round_type (str): The type of round (e.g., 'evaluation', 'minigame1').

    Returns:
        int: The round_id of the newly created round record if successful, None on error.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            return None

        cur = conn.cursor()
        sql = """
            INSERT INTO rounds (game_id, round_number, round_type, start_time)
            VALUES (%s, %s, %s, NOW()::TIMESTAMP)
            RETURNING round_id;
        """
        cur.execute(sql, (game_id, round_number, round_type)) # Parameters in order

        round_id = cur.fetchone()[0]
        conn.commit()
        return round_id

    except (Exception, psycopg2.Error) as error:
        print("Error in create_round_record:", error)
        return None

    finally:
        if conn:
            if cur: # Check if cursor exists before closing
                cur.close()
            conn.close()


@app.route('/test_db_insert', methods=['GET']) # Corrected indentation here too
def test_db_insert():
    """
    Tests the create_game_record and create_round_record functions.
    """
    try:
        server_id = "test-server-instance-123" # Example server ID
        game_settings_data = {"difficulty": "easy", "map": "tutorial"} # Example settings

        game_id = create_game_record(server_id, game_settings_data)
        if game_id: # Check if game_id is NOT None (meaning success)
            round_id = create_round_record(game_id, 1, "evaluation") # Example round

            if round_id: # Check if round_id is NOT None (meaning success)
                return jsonify({"status": "success", "message": "Game and round records created successfully!", "game_id": game_id, "round_id": round_id})
            else:
                return jsonify({"status": "error", "message": "Failed to create round record.", "game_id": game_id}) # round creation failed, but game was created
        else:
            return jsonify({"status": "error", "message": "Failed to create game record."}) # game creation failed

    except Exception as e:
        print(f"Error in /test_db_insert endpoint: {e}")
        return jsonify({"status": "error", "message": f"Error during database insert test: {e}"})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))