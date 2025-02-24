import psycopg2
import os
import traceback
import datetime

# ========================================================================
#                      SECTION 7: DATABASE HELPER FUNCTIONS
# ========================================================================

# Get the database URL from environment variables (for Neon Postgres)
DATABASE_URL = os.environ.get("DATABASE_URL")

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