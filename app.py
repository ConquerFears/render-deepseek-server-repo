###############################################################################
# FLASK SERVER APPLICATION
###############################################################################

# IMPORTS SECTION
# ------------------------------------------------------------------------------
# Flask - Web framework that handles HTTP requests
from flask import Flask, request, jsonify  # Core Flask components to build a web server

# Python standard libraries
import uuid          # For generating unique IDs (like game session IDs)
import traceback     # For detailed error reporting
import os            # For accessing environment variables and system functions
import json          # For working with JSON data
import time          # For timing and delays
import datetime      # For working with dates and times
import psycopg2      # PostgreSQL database connector

# Import functions from our database utility module
from db_utils import (
    DATABASE_URL,                   # Database connection string
    get_db_connection,              # Get a connection to the database
    create_game_record,             # Create a new game session in the database
    update_game_status_and_usernames, # Update game status and player information
    create_round_record,            # Create a new game round record
    init_db_pool,                   # Initialize the database connection pool
    release_db_connection,          # Return a connection to the pool when done
    connection_pool                 # The shared connection pool object
)

# Import functions and variables from our AI utility module
from gemini_utils import (
    default_model,                  # The default Gemini AI model configuration
    round_start_system_prompt,      # Special prompt for starting a new game round
    system_prompt,                  # General prompt for normal AI interactions
    generation_config,              # Configuration settings for the AI
    REQUEST_LIMIT_SECONDS,          # Minimum time between API requests (rate limiting)
    last_request_time,              # When we last made an API request
    response_cache,                 # Cache to store AI responses (avoid duplicate API calls)
    CACHE_EXPIRY_SECONDS,           # How long to keep responses in the cache
    create_dynamic_gemini_model     # Create a Gemini model with custom settings
)

# Logging - For tracking application activity and errors
import logging

# ========================================================================
#                      SECTION 1:  FLASK APP INITIALIZATION
# ========================================================================

# Setup logging - This helps us track what happens in our application
# ------------------------------------------------------------------------------
# The logging system writes messages about what's happening to the console or a file
# This is much better than using print() statements for debugging
logging.basicConfig(
    level=logging.INFO,  # We'll see INFO level messages and above (INFO, WARNING, ERROR, CRITICAL)
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'  # Format for log messages
)
logger = logging.getLogger(__name__)  # Create a logger for this specific file

# Initialize Flask app - This creates our web application
# ------------------------------------------------------------------------------
app = Flask(__name__)  # Create a new Flask application

# Create a centralized error handler - Consistently handles errors across the app
# ------------------------------------------------------------------------------
def handle_api_error(error, context="API operation"):
    """Centralized error handler for API operations
    
    This function:
    1. Creates a standard error message with context
    2. Logs the error 
    3. Prints the full error traceback for debugging
    4. Returns a consistent JSON error response to the client
    """
    error_message = f"Error during {context}: {str(error)}"
    logger.error(error_message)  # Log the error message
    traceback.print_exc()        # Print detailed error information to the console/logs
    return jsonify({
        "status": "error",
        "message": "Internal server error",
        "detail": str(error) if app.debug else None  # Only show details in debug mode
    }), 500  # HTTP 500 = Internal Server Error

# Input validation helper - Checks if requests contain required data
# ------------------------------------------------------------------------------
def validate_request_data(data, required_fields):
    """Validate that request data contains all required fields
    
    This function:
    1. Checks if any data was provided
    2. Checks if all required fields are present
    3. Returns validation status and message
    """
    if not data:
        return False, "No data provided in request body"
    
    # Check each required field, collect any missing ones
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"
    return True, "Valid"  # All fields are present!

# ========================================================================
#                      SECTION 9: FLASK ROUTE DEFINITIONS (ENDPOINTS)
# ========================================================================

# --- 9.1: Root route - simple hello world for testing ---
# ------------------------------------------------------------------------------
# This is a basic endpoint to test if the server is running
@app.route('/', methods=['GET'])
def hello_world():
    """Basic test endpoint that shows the server is running"""
    logger.info(f"Root route accessed, DATABASE_URL configured: {bool(DATABASE_URL)}")
    return 'Hello, World! This is your Fly.io server with Postgres!'

# --- 9.2: /gemini_request route - main endpoint for AI requests from Roblox ---
# ------------------------------------------------------------------------------
# This is where the game sends player messages and gets AI responses
@app.route('/gemini_request', methods=['POST'])
def gemini_request():
    """Main endpoint for AI interactions
    
    This function:
    1. Receives input text from the game
    2. Validates the input and applies basic filtering
    3. Selects the appropriate AI prompt based on context
    4. Handles caching and rate limiting
    5. Calls the Gemini AI API
    6. Returns the AI response to the game
    """
    global last_request_time  # We need to track the last request time globally
    
    try:
        # Get and validate the JSON data from the request
        data = request.get_json()
        valid, message = validate_request_data(data, ['user_input'])
        if not valid:
            return message, 400, {'Content-Type': 'text/plain'}  # HTTP 400 = Bad Request

        # Extract the player's text input
        user_text = data['user_input'].strip()

        # INPUT FILTERING: Block empty or overly simple requests
        # ----------------------------------------------------------------------
        if not user_text:
            logger.info("Blocked empty query, no Gemini call.")
            return "", 200, {'Content-Type': 'text/plain'}
        if len(user_text) < 5 and user_text.lower() in ["hi", "hello", "hey"]:
            logger.info(f"Blocked short, generic query: '{user_text}', no Gemini call.")
            return "SERAPH: Greetings.", 200, {'Content-Type': 'text/plain'}

        logger.info(f"Received input from Roblox: {user_text}")

        # CONTEXT SELECTION: Choose the right system prompt and settings
        # ----------------------------------------------------------------------
        current_system_prompt = system_prompt  # Default to general prompt
        current_temperature = generation_config["temperature"]  # Default temperature

        # Check if this is a round start message - these get special treatment
        if user_text.startswith("Round start initiated"):
            # Use the special system prompt for round starts
            current_system_prompt = round_start_system_prompt
            current_temperature = 0.25  # Lower temperature = more focused, less random
            logger.info("Using ROUND START system prompt...")

            # CACHING: Check if we've answered this exact question recently
            # ------------------------------------------------------------------
            cache_key = user_text
            cached_response_data = response_cache.get(cache_key)

            # If we have a recent response in cache, use it instead of calling the API again
            if cached_response_data and (time.time() - cached_response_data['timestamp'] < CACHE_EXPIRY_SECONDS):
                logger.info(f"Serving cached response for: {user_text}")
                gemini_text_response = cached_response_data['response']
                return gemini_text_response, 200, {'Content-Type': 'text/plain'}

            # RATE LIMITING: Don't overwhelm the Gemini API
            # ------------------------------------------------------------------
            current_time = time.time()
            time_since_last_request = current_time - last_request_time
            if time_since_last_request < REQUEST_LIMIT_SECONDS:
                logger.info("Request throttled - waiting before Gemini API call.")
                time.sleep(REQUEST_LIMIT_SECONDS - time_since_last_request)
            last_request_time = current_time

            # API CALL: Send the request to Gemini AI
            # ------------------------------------------------------------------
            dynamic_model = create_dynamic_gemini_model(current_temperature)
            logger.info("gemini_request: Calling dynamic_model.generate_content...")
            try:
                # This is the actual call to the Gemini AI API
                response = dynamic_model.generate_content(
                    [
                        {"role": "user", "parts": [current_system_prompt, user_text]},
                    ]
                )
                logger.info("gemini_request: dynamic_model.generate_content call RETURNED.")
                logger.debug(f"gemini_request: Raw response.text: {response.text}")
                gemini_text_response = response.text.strip()
                logger.info(f"gemini_request: Gemini Response (Stripped): {gemini_text_response}")

                # CACHE: Save this response for future reuse
                # --------------------------------------------------------------
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
            # GENERAL CASE: Normal player messages (not round start)
            # ------------------------------------------------------------------
            logger.info("Using GENERAL system prompt...")
            dynamic_model = create_dynamic_gemini_model(current_temperature)
            try:
                # Call the Gemini API with the general system prompt
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
# ------------------------------------------------------------------------------
# This endpoint is called when a new game session starts in Roblox
@app.route('/game_start_signal', methods=['POST'])
def game_start_signal():
    """Handle signal that a new game has started in Roblox
    
    This function:
    1. Receives information about a new game session
    2. Creates a database record for the game
    3. Returns confirmation to Roblox with the game_id
    """
    try:
        # Get and validate the JSON data from the request
        data = request.get_json()
        valid, message = validate_request_data(data, ['user_input', 'player_usernames'])
        if not valid:
            logger.warning(f"game_start_signal: {message}")
            return jsonify({"status": "error", "message": message}), 400

        # Extract data from the request
        user_input = data['user_input'].strip()
        player_usernames_list_from_roblox = data.get('player_usernames', [])
        logger.info(f"Game Start Signal Received from Roblox. Usernames: {player_usernames_list_from_roblox}")

        # Create a unique ID for this game session
        server_instance_id = str(uuid.uuid4())
        # Create a record in the database
        game_id_created = create_game_record(server_instance_id, player_usernames_list_from_roblox)

        # Return success or failure to Roblox
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
# ------------------------------------------------------------------------------
# This endpoint simply returns whatever text is sent to it (for testing)
@app.route('/echo', methods=['POST'])
def echo_input():
    """Simple echo endpoint for testing
    
    This function:
    1. Receives text from the request
    2. Returns the same text back
    """
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
# ------------------------------------------------------------------------------
# This endpoint checks if the database is accessible and returns table info
@app.route('/test_db', methods=['GET'])
def test_db_connection():
    """Test the database connection and inspect schema
    
    This function:
    1. Connects to the database
    2. Queries table schema information
    3. Returns connection status and schema details
    """
    logger.info("Entering /test_db route... (schema inspection version)")
    conn = None
    try:
        # Get a database connection
        conn = get_db_connection()
        if conn:
            # Query the database for column information
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
        # Always release the connection when done
        if conn:
            release_db_connection(conn)

# --- 9.6: /hello_test_route - simple hello test route for Fly.io verification ---
# ------------------------------------------------------------------------------
# Another simple test endpoint
@app.route('/hello_test_route', methods=['GET'])
def hello_test_route():
    """Simple hello endpoint for testing deployment"""
    logger.info("Accessed /hello_test_route endpoint!")
    return "Hello from Fly.io! This is a test route.", 200, {'Content-Type': 'text/plain'}

# --- 9.7: /test_db_insert route - endpoint to test database INSERT operation ---
# ------------------------------------------------------------------------------
# This endpoint tests if we can write to the database
@app.route('/test_db_insert', methods=['GET'])
def test_db_insert():
    """Test database insert operations
    
    This function:
    1. Connects to the database
    2. Attempts to insert a test record
    3. Returns success or failure status
    """
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
# ------------------------------------------------------------------------------
# This endpoint updates information about an active game
@app.route('/game_status_update', methods=['POST'])
def game_status_update():
    """Update game status and player information
    
    This function:
    1. Updates a game record to 'active' status
    2. Updates the list of player usernames
    """
    try:
        data = request.get_json()
        valid, message = validate_request_data(data, ['game_id', 'player_usernames'])
        if not valid:
            return jsonify({"status": "error", "message": message}), 400

        game_id_str = data['game_id']
        player_usernames_list_from_roblox = data['player_usernames']

        # Call the database utility function to update the record
        success, message = update_game_status_and_usernames(game_id_str, player_usernames_list_from_roblox)

        if success:
            return jsonify({"status": "success", "message": message}), 200
        else:
            return jsonify({"status": "error", "message": message}), 500
    except Exception as e:
        return handle_api_error(e, "game status update")

# --- 9.9: /game_cleanup route - endpoint to handle game cleanup when a Roblox server shuts down ---
# ------------------------------------------------------------------------------
# This endpoint is called when a game session ends to clean up the database
@app.route('/game_cleanup', methods=['POST'])
def game_cleanup():
    """Clean up database records when a game ends
    
    This function:
    1. Receives a game_id from Roblox
    2. Deletes the corresponding database record
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
# ------------------------------------------------------------------------------
# This endpoint provides diagnostic information about the system
@app.route('/debug_info', methods=['GET'])
def debug_info():
    """Return diagnostic information about the system
    
    This function:
    1. Collects configuration information
    2. Tests database connectivity
    3. Returns a JSON object with system status
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

# --- 9.11: /team_quiz route - endpoint to receive team quiz data from Roblox ---
# ------------------------------------------------------------------------------
# This endpoint receives team quiz data from the Roblox game
@app.route('/team_quiz', methods=['POST'])
def team_quiz():
    """Handle team quiz data from Roblox
    
    This function:
    1. Receives team quiz data including game_id and teams information
    2. Validates the received data
    3. [Future] Will process this data and send it to Gemini AI
    4. [Future] Will return the AI's response back to Roblox
    
    Currently just acknowledges receipt of the data.
    """
    try:
        # Get and validate the JSON data from the request
        data = request.get_json()
        valid, message = validate_request_data(data, ['game_id', 'teams'])
        if not valid:
            logger.warning(f"team_quiz: {message}")
            return jsonify({"status": "error", "message": message}), 400

        # Extract data from the request
        game_id = data['game_id']
        teams = data['teams']
        
        logger.info(f"Team quiz data received for game ID: {game_id}")
        logger.debug(f"Teams data: {teams}")
        
        # For now, just acknowledge receipt of the data
        # Future implementation will process the data and use Gemini AI
        return jsonify({
            "status": "success",
            "message": "Team quiz data received successfully",
            "game_id": game_id
        }), 200
        
    except Exception as e:
        return handle_api_error(e, "team quiz data processing")

# ========================================================================
#                      SECTION 10: MAIN APPLICATION START
# ========================================================================

# This block only runs when this file is executed directly (not imported)
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