from flask import Flask, request, jsonify
import google.generativeai as genai
import psycopg2
import os
import json  # <--- IMPORT json MODULE
from flask import jsonify
import uuid  # <--- IMPORT UUID MODULE for generating unique game_id

app = Flask(__name__)

# Configure Gemini API
GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")  # Get API key from environment
genai.configure(api_key=GOOGLE_API_KEY)

# --- Default Generation Configuration ---
generation_config = {
    "temperature": 0.35,  # Default temperature for general chat
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 150 # Keep token limit concise
}

# Initialize Gemini Model with the default configuration
default_model = genai.GenerativeModel( # Renamed to default_model for clarity
    model_name='models/gemini-2.0-flash',
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

def create_dynamic_gemini_model(temperature):
    """
    Creates a dynamic Gemini model with the specified temperature.
    Reduces code duplication in gemini_request function.
    """
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


@app.route('/', methods=['GET'])
def hello_world():
    print(f"Checking DATABASE_URL in root route: {DATABASE_URL}") # Log DATABASE_URL in root route
    return 'Hello, World! This is your Fly.io server with Postgres!' # Updated message

@app.route('/gemini_request', methods=['POST'])
def gemini_request():
    nonlocal last_request_time

    try:
        data = request.get_json()
        if not data or 'user_input' not in data:
            return "No 'user_input' provided in request body", 400, {'Content-Type': 'text/plain'}

        user_text = data['user_input'].strip() # IMPORTANT: Strip whitespace FIRST

        # --- Server-side Input Filtering (Example - Adjust as needed) ---
        if not user_text:
            print("Blocked empty query, no Gemini call.")
            return "", 200, {'Content-Type': 'text/plain'} # Return empty, no AI call
        if len(user_text) < 5 and user_text.lower() in ["hi", "hello", "hey"]: # Example short greetings
            print(f"Blocked short, generic query: '{user_text}', no Gemini call.")
            return "SERAPH: Greetings.", 200, {'Content-Type': 'text/plain'} # Canned response


        print(f"Received input from Roblox: {user_text}")

        current_system_prompt = system_prompt
        current_temperature = generation_config["temperature"]
        game_id_response = None

        if user_text.startswith("Round start initiated"):
            current_system_prompt = round_start_system_prompt
            current_temperature = 0.25
            print("Using ROUND START system prompt...")

            # --- EXTRACT PLAYER USERNAMES from request data ---
            player_usernames_list_from_roblox = data.get('player_usernames', []) # Get usernames from request, default to empty list if not present
            print(f"gemini_request (Round Start): Player usernames received from Roblox: {player_usernames_list_from_roblox}") # Log received usernames


            server_instance_id = str(uuid.uuid4())
            # --- PASS player_usernames_list to create_game_record ---
            game_id = create_game_record(server_instance_id, player_usernames_list_from_roblox) # <--- Pass usernames here!
            if game_id:
                print(f"Successfully created new game record with game_id: {game_id}")
                game_id_response = str(game_id)
            else:
                print("Failed to create game record in database.")
                game_id_response = "DB_ERROR"


            # --- Caching Logic --- (No changes here)
            cache_key = user_text # Simple cache key
            cached_response_data = response_cache.get(cache_key)

            if cached_response_data and (time.time() - cached_response_data['timestamp'] < CACHE_EXPIRY_SECONDS):
                print(f"Serving cached response for: {user_text}")
                gemini_text_response = cached_response_data['response']
                return gemini_text_response, 200, {'Content-Type': 'text/plain'} # Return cached response


            # --- Rate Limiting Logic --- (No changes here)
            current_time = time.time()
            time_since_last_request = current_time - last_request_time
            if time_since_last_request < REQUEST_LIMIT_SECONDS:
                print("Request throttled - waiting before Gemini API call.")
                time.sleep(REQUEST_LIMIT_SECONDS - time_since_last_request)
            last_request_time = current_time # Update last request time


            # --- Gemini API Call --- (No changes here)
            dynamic_model = create_dynamic_gemini_model(current_temperature)
            print("gemini_request: Calling dynamic_model.generate_content...")
            try:
                response = dynamic_model.generate_content(
                    [
                        {"role": "user", "parts": [current_system_prompt, user_text]},
                    ]
                )
                print("gemini_request: dynamic_model.generate_content call RETURNED.")
                print(f"gemini_request: Raw response.text: {response.text}")
                gemini_text_response = response.text.strip()
                print(f"gemini_request: Gemini Response (Stripped): {gemini_text_response}")

                # --- Store in Cache --- (No changes here)
                response_cache[cache_key] = {
                    'response': gemini_text_response,
                    'timestamp': time.time()
                }
                print(f"Caching new response for: {user_text}")


                return gemini_text_response, 200, {'Content-Type': 'text/plain', 'Content-Length': str(len(gemini_text_response))}

            except Exception as gemini_error:
                print(f"gemini_request (Round Start): ERROR calling Gemini API: {gemini_error}")
                return "Error communicating with Gemini API", 500, {'Content-Type': 'text/plain'}


        else: # --- GENERAL PROMPT PATH --- (No changes in ELSE path)
            print("Using GENERAL system prompt...")
            dynamic_model = create_dynamic_gemini_model(current_temperature)
            try:
                response = dynamic_model.generate_content(
                    [
                        {"role": "user", "parts": [current_system_prompt, user_text]},
                    ]
                )
                gemini_text_response = response.text.strip()
                print(f"Gemini Response (General): {gemini_text_response}")
                return gemini_text_response, 200, {'Content-Type': 'text/plain'}

            except Exception as gemini_error:
                print(f"Error calling Gemini API (General): {gemini_error}")
                return "Error communicating with Gemini API", 500, {'Content-Type': 'text/plain'}

    except Exception as e:
        print(f"Error processing request: {e}")
        return "Internal server error", 500, {'Content-Type': 'text/plain'}

@app.route('/echo', methods=['POST'])
def echo_input(): # ... (rest of echo_input function - no changes) ...
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
def test_db_connection(): # ... (rest of test_db_connection - no changes) ...
    print("Entering /test_db route... (schema inspection version)")
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(""" ... (SQL query) ... """)
            columns_info = cur.fetchall()
            column_names = [(name, data_type) for name, data_type in columns_info]
            cur.close()
            conn.close()
            return jsonify({"status": "Database connection successful", "table_name": "games", "columns": column_names}), 200
        except (Exception, psycopg2.Error) as db_error:
            if conn:
                conn.close()
            return jsonify({"status": "Database query error", "error": str(db_error)}), 500
    else:
        return jsonify({"status": "Database connection failed"}), 500

@app.route('/hello_test_route', methods=['GET'])
def hello_test_route(): # ... (rest of hello_test_route - no changes) ...
    print("Accessed /hello_test_route endpoint!")
    return "Hello from Fly.io! This is a test route.", 200, {'Content-Type': 'text/plain'}

def create_game_record(server_instance_id, player_usernames_list): # ... (rest of create_game_record - updated version) ...
    conn = None
    print("create_game_record: Function started (simplified schema, with usernames)") # Updated log

    try:
        print("create_game_record: Getting DB connection...")
        conn = get_db_connection()
        if conn is None:
            print("create_game_record: DB connection FAILED - get_db_connection returned None")
            return None
        print("create_game_record: DB connection SUCCESSFUL")

        cur = conn.cursor()

        # --- Convert list of usernames to comma-separated string ---
        player_usernames_str = ','.join(player_usernames_list) # NEW - Join usernames into string
        print(f"create_game_record: Player usernames string: {player_usernames_str}") # Log the username string

        sql = """
            INSERT INTO games (game_id, start_time, status, player_usernames)  -- Added player_usernames column
            VALUES (%s, NOW()::TIMESTAMP, %s, %s)                                -- Added %s placeholder for usernames
            RETURNING game_id;
        """
        values = (server_instance_id, 'starting', player_usernames_str) # Values now include usernames
        print(f"create_game_record: Executing SQL Query (INSERT game record - with usernames): {sql} with values: {values}") # Updated log
        cur.execute(sql, values)
        print("create_game_record: SQL query executed successfully (with usernames)")

        game_id = cur.fetchone()[0]
        conn.commit()
        print(f"create_game_record: Commit successful, game_id: {game_id} (with usernames)")
        return game_id

    except (Exception, psycopg2.Error) as error:
        print("create_game_record: ERROR in INSERT operation (with usernames):", error) # Updated error log
        return None

    finally:
        print("create_game_record: Entering finally block (with usernames)")
        if conn:
            print("create_game_record: Closing cursor and connection (with usernames)")
            if cur:
                cur.close()
            conn.close()
        else:
            print("create_game_record: Connection was None in finally block (with usernames) - nothing to close")
        print("create_game_record: Exiting finally block (with usernames)")


def create_round_record(game_id, round_number, round_type): # ... (rest of create_round_record - no changes) ...
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            return None

        cur = conn.cursor()
        sql = """ ... (SQL INSERT rounds query) ... """
        cur.execute(sql, (game_id, round_number, round_type))
        round_id = cur.fetchone()[0]
        conn.commit()
        return round_id

    except (Exception, psycopg2.Error) as error:
        print("Error in create_round_record:", error)
        return None

    finally:
        if conn:
            if cur:
                cur.close()
            conn.close()


@app.route('/test_db_insert', methods=['GET']) # ... (rest of test_db_insert - no changes) ...
def test_db_insert():
    conn = None
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        cur.execute("INSERT INTO games (status) VALUES ('running')")
        conn.commit()
        cur.close()
        return jsonify({"message": "Data inserted successfully into games table", "status": "success"})
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Database insertion error: {e}")
        return jsonify({"message": "Failed to create game record.", "status": "error"})
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))