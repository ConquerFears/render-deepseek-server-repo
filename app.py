from flask import Flask, request, jsonify
import google.generativeai as genai
import psycopg2
import os
import json
from flask import jsonify
import uuid
import traceback
import time
import datetime

app = Flask(__name__)

# Configure Gemini API
GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

# --- Default Generation Configuration ---
generation_config = {
    "temperature": 0.35,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 150
}

# Initialize Gemini Model with the default configuration
default_model = genai.GenerativeModel(
    model_name='models/gemini-2.0-flash',
    generation_config=generation_config
)

# --- System Prompts ---
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

DATABASE_URL = os.environ.get("DATABASE_URL")

# --- Rate Limiting Configuration ---
REQUEST_LIMIT_SECONDS = 1
last_request_time = 0

# --- Caching Configuration ---
response_cache = {}
CACHE_EXPIRY_SECONDS = 60 * 5


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


@app.route('/', methods=['GET'])
def hello_world():
    print(f"Checking DATABASE_URL in root route: {DATABASE_URL}")
    return 'Hello, World! This is your Fly.io server with Postgres!'


@app.route('/gemini_request', methods=['POST'])
def gemini_request():
    global last_request_time

    try:
        data = request.get_json()
        if not data or 'user_input' not in data:
            return "No 'user_input' provided in request body", 400, {'Content-Type': 'text/plain'}

        user_text = data['user_input'].strip()

        if not user_text:
            print("Blocked empty query, no Gemini call.")
            return "", 200, {'Content-Type': 'text/plain'}
        if len(user_text) < 5 and user_text.lower() in ["hi", "hello", "hey"]:
            print(f"Blocked short, generic query: '{user_text}', no Gemini call.")
            return "SERAPH: Greetings.", 200, {'Content-Type': 'text/plain'}

        print(f"Received input from Roblox: {user_text}")

        current_system_prompt = system_prompt
        current_temperature = generation_config["temperature"]
        game_id_response = None

        if user_text.startswith("Round start initiated"):
            current_system_prompt = round_start_system_prompt
            current_temperature = 0.25
            print("Using ROUND START system prompt...")

            print("/gemini_request (Round Start): Database record creation is handled by /game_start_signal endpoint.")

            cache_key = user_text
            cached_response_data = response_cache.get(cache_key)

            if cached_response_data and (time.time() - cached_response_data['timestamp'] < CACHE_EXPIRY_SECONDS):
                print(f"Serving cached response for: {user_text}")
                gemini_text_response = cached_response_data['response']
                return gemini_text_response, 200, {'Content-Type': 'text/plain'}

            current_time = time.time()
            time_since_last_request = current_time - last_request_time
            if time_since_last_request < REQUEST_LIMIT_SECONDS:
                print("Request throttled - waiting before Gemini API call.")
                time.sleep(REQUEST_LIMIT_SECONDS - time_since_last_request)
            last_request_time = current_time

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

                response_cache[cache_key] = {
                    'response': gemini_text_response,
                    'timestamp': time.time()
                }
                print(f"Caching new response for: {user_text}")

                return gemini_text_response, 200, {'Content-Type': 'text/plain', 'Content-Length': str(len(gemini_text_response))}

            except Exception as gemini_error:
                print(f"gemini_request (Round Start): ERROR calling Gemini API: {gemini_error}")
                return "Error communicating with Gemini API", 500, {'Content-Type': 'text/plain'}

        else:
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


@app.route('/game_start_signal', methods=['POST'])
def game_start_signal():
    """
    Endpoint to handle game start signals from Roblox.
    Creates a new game record in the database.
    Returns a JSON response indicating success or failure.
    """
    try:
        data = request.get_json()
        if not data or 'user_input' not in data or 'player_usernames' not in data:
            print("game_start_signal: Invalid request body")
            return jsonify({"status": "error", "message": "Invalid request body"}), 400, {'Content-Type': 'application/json'}

        user_input = data['user_input'].strip()
        player_usernames_list_from_roblox = data.get('player_usernames', [])
        print(f"Game Start Signal Received from Roblox. Usernames: {player_usernames_list_from_roblox}")

        server_instance_id = str(uuid.uuid4())
        game_record_created = create_game_record(server_instance_id, player_usernames_list_from_roblox)

        if game_record_created:
            print(f"game_start_signal: Game record CREATED successfully. Game ID: {game_record_created}")
            return jsonify({"status": "success", "message": "Game start signal processed, game record created", "game_id": game_record_created}), 200, {'Content-Type': 'application/json'}
        else:
            print("game_start_signal: Game record creation FAILED.")
            return jsonify({"status": "error", "message": "Game record creation failed"}), 500, {'Content-Type': 'application/json'}

    except Exception as e:
        error_message = f"game_start_signal: ERROR processing /game_start_signal request: {e}"
        full_trace = traceback.format_exc()
        print(error_message)
        print(f"game_start_signal: Full Traceback:\n{full_trace}")
        print(error_message, file=sys.stderr)
        print(f"game_start_signal: Full Traceback (stderr):\n{full_trace}", file=sys.stderr)
        return jsonify({"status": "error", "message": "Internal server error"}), 500, {'Content-Type': 'application/json'}


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
    print("Entering /test_db route... (schema inspection version)")
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'games'
                ORDER BY column_name;
            """)
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
def hello_test_route():
    print("Accessed /hello_test_route endpoint!")
    return "Hello from Fly.io! This is a test route.", 200, {'Content-Type': 'text/plain'}


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
        full_trace = traceback.format_exc()
        print(error_msg)
        print(f"Full Traceback:\n{full_trace}")
        print(error_msg, file=sys.stderr)
        print(f"Full Traceback (stderr):\n{full_trace}", file=sys.stderr)
        if conn:
            conn.rollback()
        return None

    finally:
        if conn:
            if cur:
                cur.close()
            conn.close()


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
        return None

    finally:
        if conn:
            if cur:
                cur.close()
            conn.close()


@app.route('/test_db_insert', methods=['GET'])
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