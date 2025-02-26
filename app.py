from flask import Flask, request, jsonify
import uuid
import traceback
import os
import json
import time
import datetime
import psycopg2
from db_utils import (
    DATABASE_URL, 
    get_db_connection, 
    create_game_record, 
    update_game_status_and_usernames, 
    create_round_record,
    init_db_pool,
    release_db_connection,
    connection_pool
)
from gemini_utils import (
    default_model, 
    round_start_system_prompt, 
    system_prompt, 
    generation_config, 
    REQUEST_LIMIT_SECONDS, 
    last_request_time, 
    response_cache, 
    CACHE_EXPIRY_SECONDS, 
    create_dynamic_gemini_model
)
import logging

# ========================================================================
#                      SECTION 1:  FLASK APP INITIALIZATION
# ========================================================================

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Create a centralized error handler
def handle_api_error(error, context="API operation"):
    """Centralized error handler for API operations"""
    error_message = f"Error during {context}: {str(error)}"
    logger.error(error_message)
    traceback.print_exc()
    return jsonify({
        "status": "error",
        "message": "Internal server error",
        "detail": str(error) if app.debug else None
    }), 500

# Input validation helper
def validate_request_data(data, required_fields):
    """Validate that request data contains all required fields"""
    if not data:
        return False, "No data provided in request body"
    
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"
    return True, "Valid"

# ========================================================================
#                      SECTION 9: FLASK ROUTE DEFINITIONS (ENDPOINTS)
# ========================================================================

# --- 9.1: Root route - simple hello world for testing ---
@app.route('/', methods=['GET'])
def hello_world():
    logger.info(f"Root route accessed, DATABASE_URL configured: {bool(DATABASE_URL)}")
    return 'Hello, World! This is your Fly.io server with Postgres!'

# --- 9.2: /gemini_request route - main endpoint for AI requests from Roblox ---
@app.route('/gemini_request', methods=['POST'])
def gemini_request():
    global last_request_time
    
    try:
        data = request.get_json()
        valid, message = validate_request_data(data, ['user_input'])
        if not valid:
            return message, 400, {'Content-Type': 'text/plain'}

        user_text = data['user_input'].strip()

        # Input filtering
        if not user_text:
            logger.info("Blocked empty query, no Gemini call.")
            return "", 200, {'Content-Type': 'text/plain'}
        if len(user_text) < 5 and user_text.lower() in ["hi", "hello", "hey"]:
            logger.info(f"Blocked short, generic query: '{user_text}', no Gemini call.")
            return "SERAPH: Greetings.", 200, {'Content-Type': 'text/plain'}

        logger.info(f"Received input from Roblox: {user_text}")

        current_system_prompt = system_prompt
        current_temperature = generation_config["temperature"]

        # Check if round start
        if user_text.startswith("Round start initiated"):
            current_system_prompt = round_start_system_prompt
            current_temperature = 0.25
            logger.info("Using ROUND START system prompt...")

            # Caching Logic
            cache_key = user_text
            cached_response_data = response_cache.get(cache_key)

            if cached_response_data and (time.time() - cached_response_data['timestamp'] < CACHE_EXPIRY_SECONDS):
                logger.info(f"Serving cached response for: {user_text}")
                gemini_text_response = cached_response_data['response']
                return gemini_text_response, 200, {'Content-Type': 'text/plain'}

            # Rate Limiting Logic
            current_time = time.time()
            time_since_last_request = current_time - last_request_time
            if time_since_last_request < REQUEST_LIMIT_SECONDS:
                logger.info("Request throttled - waiting before Gemini API call.")
                time.sleep(REQUEST_LIMIT_SECONDS - time_since_last_request)
            last_request_time = current_time

            dynamic_model = create_dynamic_gemini_model(current_temperature)
            logger.info("gemini_request: Calling dynamic_model.generate_content...")
            try:
                response = dynamic_model.generate_content(
                    [
                        {"role": "user", "parts": [current_system_prompt, user_text]},
                    ]
                )
                logger.info("gemini_request: dynamic_model.generate_content call RETURNED.")
                logger.debug(f"gemini_request: Raw response.text: {response.text}")
                gemini_text_response = response.text.strip()
                logger.info(f"gemini_request: Gemini Response (Stripped): {gemini_text_response}")

                # Cache the new Gemini response
                response_cache[cache_key] = {
                    'response': gemini_text_response,
                    'timestamp': time.time()
                }
                logger.info(f"Caching new response for: {user_text}")

                return gemini_text_response, 200, {'Content-Type': 'text/plain', 'Content-Length': str(len(gemini_text_response))}

            except Exception as gemini_error:
                logger.error(f"gemini_request (Round Start): ERROR calling Gemini API: {gemini_error}")
                return "Error communicating with Gemini API", 500, {'Content-Type': 'text/plain'}

        else:
            logger.info("Using GENERAL system prompt...")
            dynamic_model = create_dynamic_gemini_model(current_temperature)
            try:
                response = dynamic_model.generate_content(
                    [
                        {"role": "user", "parts": [current_system_prompt, user_text]},
                    ]
                )
                gemini_text_response = response.text.strip()
                logger.info(f"Gemini Response (General): {gemini_text_response}")
                return gemini_text_response, 200, {'Content-Type': 'text/plain'}

            except Exception as gemini_error:
                logger.error(f"Error calling Gemini API (General): {gemini_error}")
                return "Error communicating with Gemini API", 500, {'Content-Type': 'text/plain'}

    except Exception as e:
        return handle_api_error(e, "gemini_request processing")

# --- 9.3: /game_start_signal route - endpoint for Roblox to signal game start ---
@app.route('/game_start_signal', methods=['POST'])
def game_start_signal():
    """
    Endpoint to handle game start signals from Roblox.
    Creates a new game record in the database.
    Returns a JSON response indicating success or failure.
    """
    try:
        data = request.get_json()
        valid, message = validate_request_data(data, ['user_input', 'player_usernames'])
        if not valid:
            logger.warning(f"game_start_signal: {message}")
            return jsonify({"status": "error", "message": message}), 400

        user_input = data['user_input'].strip()
        player_usernames_list_from_roblox = data.get('player_usernames', [])
        logger.info(f"Game Start Signal Received from Roblox. Usernames: {player_usernames_list_from_roblox}")

        server_instance_id = str(uuid.uuid4())
        game_id_created = create_game_record(server_instance_id, player_usernames_list_from_roblox)

        if game_id_created:
            logger.info(f"game_start_signal: Game record CREATED successfully. Game ID: {game_id_created}")
            return jsonify({
                "status": "success", 
                "message": "Game start signal processed, game record created", 
                "game_id": game_id_created
            }), 200
        else:
            logger.error("game_start_signal: Game record creation FAILED.")
            return jsonify({"status": "error", "message": "Game record creation failed"}), 500

    except Exception as e:
        return handle_api_error(e, "game_start_signal processing")

# --- 9.4: /echo route - simple echo endpoint for testing Roblox communication ---
@app.route('/echo', methods=['POST'])
def echo_input():
    try:
        data = request.get_json()
        valid, message = validate_request_data(data, ['user_input'])
        if not valid:
            return message, 400, {'Content-Type': 'text/plain'}

        user_text = data['user_input']
        logger.info(f"Echoing back to Roblox: {user_text}")
        return user_text, 200, {'Content-Type': 'text/plain'}

    except Exception as e:
        return handle_api_error(e, "echo endpoint")

# --- 9.5: /test_db route - endpoint to test database connection and schema ---
@app.route('/test_db', methods=['GET'])
def test_db_connection():
    logger.info("Entering /test_db route... (schema inspection version)")
    conn = None
    try:
        conn = get_db_connection()
        if conn:
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
            return jsonify({"status": "Database connection successful", "table_name": "games", "columns": column_names}), 200
        else:
            return jsonify({"status": "Database connection failed"}), 500
    except Exception as e:
        return handle_api_error(e, "database test")
    finally:
        if conn:
            release_db_connection(conn)

# --- 9.6: /hello_test_route - simple hello test route for Fly.io verification ---
@app.route('/hello_test_route', methods=['GET'])
def hello_test_route():
    logger.info("Accessed /hello_test_route endpoint!")
    return "Hello from Fly.io! This is a test route.", 200, {'Content-Type': 'text/plain'}

# --- 9.7: /test_db_insert route - endpoint to test database INSERT operation ---
@app.route('/test_db_insert', methods=['GET'])
def test_db_insert():
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"message": "Failed to connect to database", "status": "error"})
        cur = conn.cursor()
        cur.execute("INSERT INTO games (status) VALUES ('running')")
        conn.commit()
        cur.close()
        return jsonify({"message": "Data inserted successfully into games table", "status": "success"})
    except Exception as e:
        return handle_api_error(e, "database insert test")
    finally:
        if conn:
            release_db_connection(conn)

# --- 9.8: /game_status_update route - endpoint to update game status and usernames ---
@app.route('/game_status_update', methods=['POST'])
def game_status_update():
    """
    Endpoint to update the status of a game record to 'active' AND update player usernames.
    Expects a JSON payload with 'game_id' and 'player_usernames'.
    """
    try:
        data = request.get_json()
        valid, message = validate_request_data(data, ['game_id', 'player_usernames'])
        if not valid:
            return jsonify({"status": "error", "message": message}), 400

        game_id_str = data['game_id']
        player_usernames_list_from_roblox = data['player_usernames']

        success, message = update_game_status_and_usernames(game_id_str, player_usernames_list_from_roblox)

        if success:
            return jsonify({"status": "success", "message": message}), 200
        else:
            return jsonify({"status": "error", "message": message}), 500
    except Exception as e:
        return handle_api_error(e, "game status update")

# --- 9.9: /game_cleanup route - endpoint to handle game cleanup when a Roblox server shuts down ---
@app.route('/game_cleanup', methods=['POST'])
def game_cleanup():
    """
    Endpoint to handle game cleanup when a Roblox server shuts down.
    Expects a JSON payload with game_id.
    Deletes the corresponding game record from the database.
    """
    try:
        data = request.get_json()
        valid, message = validate_request_data(data, ['game_id'])
        if not valid:
            logger.warning(f"game_cleanup: {message}")
            return jsonify({"status": "error", "message": message}), 400

        game_id = data['game_id']
        logger.info(f"game_cleanup: Received cleanup request for game_id: {game_id}")

        # Handle the "UNKNOWN_GAME_ID" case from Roblox
        if game_id == "UNKNOWN_GAME_ID":
            logger.info("game_cleanup: Received UNKNOWN_GAME_ID, skipping cleanup")
            return jsonify({
                "status": "warning",
                "message": "Skipped cleanup for UNKNOWN_GAME_ID"
            }), 200

        conn = None
        cur = None
        try:
            conn = get_db_connection()
            if conn is None:
                return jsonify({
                    "status": "error",
                    "message": "Database connection failed"
                }), 500

            cur = conn.cursor()
            
            # First verify the game exists
            cur.execute("SELECT status FROM games WHERE game_id = %s", (game_id,))
            game = cur.fetchone()
            
            if not game:
                logger.warning(f"game_cleanup: No game found with ID: {game_id}")
                return jsonify({
                    "status": "warning",
                    "message": f"No game found with ID: {game_id}"
                }), 404

            # Delete the game record
            cur.execute("DELETE FROM games WHERE game_id = %s", (game_id,))
            conn.commit()
            
            logger.info(f"game_cleanup: Successfully deleted game {game_id}")
            return jsonify({
                "status": "success",
                "message": f"Game {game_id} cleaned up successfully"
            }), 200

        except Exception as db_error:
            return handle_api_error(db_error, "game cleanup database operation")
        finally:
            if cur:
                cur.close()
            if conn:
                release_db_connection(conn)

    except Exception as e:
        return handle_api_error(e, "game cleanup")

# --- 9.10: /debug_info route - endpoint to check system configuration ---
@app.route('/debug_info', methods=['GET'])
def debug_info():
    """
    Return information about the system configuration for debugging.
    Does not expose actual secret values.
    """
    info = {
        "database": {
            "url_configured": bool(DATABASE_URL),
            "connection_pool": {
                "initialized": connection_pool is not None,
                "min_connections": 1,
                "max_connections": 10
            }
        },
        "security": {
            "gemini_key_configured": bool(os.environ.get("GEMINI_API_KEY"))
        },
        "timestamp": datetime.datetime.now().isoformat(),
        "flask_debug_mode": app.debug
    }
    
    # Try a test connection
    conn = None
    try:
        conn = get_db_connection()
        info["database"]["test_connection"] = "success" if conn else "failed"
        
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            info["database"]["query_test"] = "success"
            cur.close()
        else:
            info["database"]["query_test"] = "not_attempted"
    except Exception as e:
        info["database"]["error"] = str(e)
        info["database"]["query_test"] = "error"
    finally:
        if conn:
            release_db_connection(conn)
    
    return jsonify(info)

# ========================================================================
#                      SECTION 10: MAIN APPLICATION START
# ========================================================================

if __name__ == '__main__':
    # Initialize database connection pool
    logger.info("Initializing database connection pool...")
    pool_initialized = init_db_pool(min_conn=1, max_conn=10)
    if not pool_initialized:
        logger.warning("Failed to initialize connection pool, will use direct connections")
    
    # Log configuration state for debugging
    logger.info(f"Configuration: DATABASE_URL configured: {bool(DATABASE_URL)}")
    logger.info(f"Configuration: GEMINI_API_KEY configured: {bool(os.environ.get('GEMINI_API_KEY'))}")
    
    logger.info("Starting Flask application...")
    # Run the Flask app
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))