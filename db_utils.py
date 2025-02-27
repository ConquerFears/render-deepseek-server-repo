###############################################################################
# DATABASE UTILITIES
###############################################################################

# Import required libraries
import psycopg2           # PostgreSQL database connector
import os                 # For accessing environment variables
import traceback          # For detailed error reporting
import datetime           # For working with dates and times
from psycopg2 import pool # Connection pooling (more efficient database connections)
import logging            # For logging errors and information

# Setup logging
logger = logging.getLogger(__name__)  # Create a logger for this module

# ========================================================================
#                      SECTION 7: DATABASE HELPER FUNCTIONS
# ========================================================================

# Get the database URL from environment variables (for Neon Postgres)
# This is stored in an environment variable for security reasons
DATABASE_URL = os.environ.get("DATABASE_URL")

# Create a connection pool instead of individual connections
# A connection pool maintains several database connections ready to use
# This is more efficient than creating a new connection for each request
connection_pool = None

def init_db_pool(min_conn=1, max_conn=10):
    """Initialize the database connection pool
    
    This function creates a pool of database connections that can be
    reused across requests, which is much more efficient than creating
    new connections for each database operation.
    
    Args:
        min_conn (int): Minimum number of connections to keep in the pool
        max_conn (int): Maximum number of connections allowed in the pool
    
    Returns:
        bool: True if successful, False if failed
    """
    global connection_pool
    try:
        # Check if we have a database URL configured
        if not DATABASE_URL:
            logger.error("DATABASE_URL is not set!")
            return False
            
        # Create the connection pool
        connection_pool = pool.ThreadedConnectionPool(
            min_conn, max_conn, DATABASE_URL
        )
        logger.info(f"Connection pool created with {min_conn}-{max_conn} connections")
        return True
    except Exception as e:
        # If anything goes wrong, log the error
        logger.error(f"Error creating connection pool: {e}")
        traceback.print_exc()
        return False

def get_db_connection():
    """Get a database connection
    
    This function:
    1. Tries to get a connection from the pool
    2. Falls back to a direct connection if the pool isn't working
    
    Returns:
        Connection: A PostgreSQL database connection, or None if failed
    """
    global connection_pool
    try:
        if connection_pool:
            # Get a connection from the pool
            conn = connection_pool.getconn()
            logger.debug("Got connection from pool")
            return conn
        else:
            # Fall back to creating a new connection if the pool isn't available
            logger.warning("Connection pool not initialized, creating direct connection")
            if not DATABASE_URL:
                logger.error("DATABASE_URL is not set!")
                return None
            return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        # If anything goes wrong, log the error
        logger.error(f"Error getting database connection: {e}")
        traceback.print_exc()
        return None

def release_db_connection(conn):
    """Return a connection to the pool when finished
    
    This function puts a connection back in the pool so it can be reused,
    or closes it if we're not using a pool.
    
    Args:
        conn: The database connection to release
    """
    global connection_pool
    try:
        if connection_pool and conn:
            # Return the connection to the pool
            connection_pool.putconn(conn)
        elif conn:
            # Close the connection if we're not using a pool
            conn.close()
    except Exception as e:
        # If anything goes wrong, log the error
        logger.error(f"Error releasing connection: {e}")
        traceback.print_exc()

# Function to create a new game record in the database
def create_game_record(server_instance_id, player_usernames_list):
    """Create a new game session record in the database
    
    This function:
    1. Gets a database connection
    2. Inserts a new record in the games table
    3. Returns the game_id if successful
    
    Args:
        server_instance_id (str): A unique ID for this game session
        player_usernames_list (list): List of player usernames
    
    Returns:
        str: The game_id if successful, None if failed
    """
    conn = None
    cur = None
    try:
        # Get a database connection
        conn = get_db_connection()
        if conn is None:
            logger.error("DB connection FAILED")
            return None
        cur = conn.cursor()

        # Convert the list of usernames to a comma-separated string
        player_usernames_str = ','.join(player_usernames_list)
        
        # The SQL query to insert a new game record
        sql = """
            INSERT INTO games (game_id, start_time, status, player_usernames)
            VALUES (%s, %s, %s, %s)
            RETURNING game_id;
        """
        # Get the current time in UTC
        current_time_utc = datetime.datetime.now(datetime.timezone.utc)
        
        # Parameters for the query
        values = (server_instance_id, current_time_utc, 'starting', player_usernames_str)

        # Execute the query
        cur.execute(sql, values)

        # Check if the query worked
        if cur.rowcount == 0:
            error_msg = f"INSERT failed, 0 rows affected. Status: {cur.statusmessage}"
            logger.error(error_msg)
            conn.rollback()
            return None

        # Get the game_id that was created
        game_id = cur.fetchone()[0]
        # Commit the transaction
        conn.commit()
        return game_id

    except (Exception, psycopg2.Error) as error:
        # If anything goes wrong, log the error
        error_msg = f"DB INSERT error: {error}"
        logger.error(error_msg)
        traceback.print_exc()
        if conn:
            # Rollback the transaction if there was an error
            conn.rollback()
        return None

    finally:
        # Always clean up resources
        if cur:
            cur.close()
        if conn:
            release_db_connection(conn)

# Function to update the game status and player usernames in the database
def update_game_status_and_usernames(game_id_str, player_usernames_list):
    """Update an existing game record with active status and player list
    
    This function:
    1. Updates a game record to 'active' status 
    2. Updates the player_usernames field
    
    Args:
        game_id_str (str): The ID of the game to update
        player_usernames_list (list): Updated list of player usernames
    
    Returns:
        tuple: (success, message) where success is a boolean and message is a string
    """
    conn = None
    cur = None
    try:
        # Get a database connection
        conn = get_db_connection()
        if conn is None:
            logger.error("DB connection FAILED in update_game_status_and_usernames")
            return False, "Database connection failed"

        cur = conn.cursor()
        
        # Convert the list of usernames to a comma-separated string
        player_usernames_str = ','.join(player_usernames_list)
        
        # The SQL query to update the game record
        sql_update = """
            UPDATE games
            SET status = 'active', player_usernames = %s
            WHERE game_id = %s::TEXT;
        """
        # Execute the query
        cur.execute(sql_update, (player_usernames_str, game_id_str))
        # Commit the transaction
        conn.commit()

        # Check if the query affected any rows
        if cur.rowcount > 0:
            logger.info(f"Game status updated to 'active' and usernames updated for game_id: {game_id_str}")
            return True, f"Game status updated to 'active' and usernames updated for game_id: {game_id_str}"
        else:
            # If no rows were affected, the game_id probably doesn't exist
            error_msg = f"Game status update failed: game_id '{game_id_str}' not found or no update performed."
            logger.error(error_msg)
            conn.rollback()
            return False, error_msg

    except (Exception, psycopg2.Error) as error:
        # If anything goes wrong, log the error
        error_message = f"Database error updating game status and usernames: {error}"
        logger.error(error_message)
        traceback.print_exc()
        if conn:
            # Rollback the transaction if there was an error
            conn.rollback()
        return False, error_message

    finally:
        # Always clean up resources
        if cur:
            cur.close()
        if conn:
            release_db_connection(conn)

# Function to create a new round record in the database (currently not used in game start)
def create_round_record(game_id, round_number, round_type):
    """Create a new round record for an existing game
    
    This function:
    1. Creates a new record in the rounds table
    2. Links it to the specified game_id
    
    Args:
        game_id (str): The ID of the game this round belongs to
        round_number (int): The sequence number of this round
        round_type (str): The type of round (e.g., 'standard', 'bonus')
    
    Returns:
        str: The round_id if successful, None if failed
    """
    conn = None
    cur = None
    try:
        # Get a database connection
        conn = get_db_connection()
        if conn is None:
            logger.error("DB connection FAILED in create_round_record")
            return None

        cur = conn.cursor()
        # The SQL query to insert a new round record
        sql = """
            INSERT INTO rounds (game_id, round_number, round_type, start_time, status)
            VALUES (%s, %s, %s, NOW()::TIMESTAMP, 'starting')
            RETURNING round_id;
        """
        # Execute the query
        cur.execute(sql, (game_id, round_number, round_type))
        # Get the round_id that was created
        round_id = cur.fetchone()[0]
        # Commit the transaction
        conn.commit()
        return round_id

    except (Exception, psycopg2.Error) as error:
        # If anything goes wrong, log the error
        logger.error(f"Error in create_round_record: {error}")
        traceback.print_exc()
        if conn:
            # Rollback the transaction if there was an error
            conn.rollback()
        return None

    finally:
        # Always clean up resources
        if cur:
            cur.close()
        if conn:
            release_db_connection(conn)