# SessionManager.py - ...
import threading
import time
import atexit
import sqlite3
import uuid

"""
# Minimum session table structure:
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT UNIQUE NOT NULL,
    starttime TEXT DEFAULT CURRENT_TIMESTAMP,
    endtime TEXT,
    PRIMARY KEY (id)
)
"""
class SessionManager:
    """
    Manages session lifecycle within a SQLite database. This includes creating new sessions,
    updating session end times in a background thread, and properly closing sessions on exit.

    Attributes:
        session_table_name (str): Name of the table storing session information.
        session_table_id_field (str): Field name for the session ID.
        session_table_endtime_field (str): Field name for the session end time.
        db_path (str): Path to the SQLite database file.
        update_thread (threading.Thread): Background thread for updating session end times.
        update_thread_running (bool): Flag indicating if the update thread is running.

    Parameters:
        db_path (str): Path to the database file where sessions will be stored.
        session_table_name (str): Optional; defaults to 'sessions'. Name of the database table for storing sessions.
        session_table_id_field (str): Optional; defaults to 'id'. Name of the ID field in the session table.
        session_table_endtime_field (str): Optional; defaults to 'endtime'. Name of the end time field in the session table.
    """
    def __init__(self, 
                 db_path, 
                 session_table_name = 'sessions', 
                 session_table_id_field = 'id', 
                 session_table_endtime_field = 'endtime'):
        """
        Initializes a new SessionManager instance.

        Parameters:
            db_path (str): Path to the database file where sessions will be stored.
            session_table_name (str): Optional. Name of the database table for storing sessions.
            session_table_id_field (str): Optional. Name of the ID field in the session table.
            session_table_endtime_field (str): Optional. Name of the end time field in the session table.
        """
        self.session_table_name = session_table_name
        self.session_table_id_field = session_table_id_field
        self.session_table_endtime_field = session_table_endtime_field
        self.db_path = db_path
        self.update_thread = None
        self.update_thread_running = False

    def get_new_connection(self):
        """
        Creates a new connection to the SQLite database, ensuring thread safety.

        Returns:
            sqlite3.Connection: A new database connection.
        """
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def create_new_session(self):
        """
        Creates a new session record in the database and starts a background thread to periodically update its end time.

        Returns:
            str: The unique ID of the newly created session.
        """
        session_id = str(uuid.uuid4())
        conn = self.get_new_connection()
        cursor = conn.cursor()
        cursor.execute(self.get_insert_new_session_sql(), (session_id,))
        conn.commit()
        conn.close()

        self.start_update_thread(session_id)
        atexit.register(self.close_session, session_id=session_id)

        return session_id
    
    def get_insert_new_session_sql(self):
        """
        Constructs the SQL query for inserting a new session into the database.

        Returns:
            str: SQL INSERT statement for creating a new session.
        """
        return f"INSERT INTO {self.session_table_name} ({self.session_table_id_field}) VALUES (?)"
    
    def get_update_endtime_sql(self):
        """
        Constructs the SQL query for updating a session's end time in the database.

        Returns:
            str: SQL UPDATE statement for updating a session's end time.
        """
        return f"UPDATE {self.session_table_name} SET {self.session_table_endtime_field}=CURRENT_TIMESTAMP WHERE {self.session_table_id_field}=?"

    def start_update_thread(self, session_id):
        """
        Starts a background thread that periodically updates the end time of the specified session.

        Parameters:
            session_id (str): The unique ID of the session to be updated.
        """
        if self.update_thread is not None:
            # If there's already an update thread running, stop it before starting a new one.
            self.close_session(session_id)

        self.update_thread_running = True

        def run():
            """
            Continuously updates the end time of the specified session in the database every minute.

            This function is intended to be run in a background thread, keeping the session's end time up-to-date until the session is explicitly closed or the thread is stopped.

            Parameters:
                session_id (str): The unique ID of the session whose end time is to be updated.
            """
            conn = self.get_new_connection()
            while self.update_thread_running:
                try:
                    cursor = conn.cursor()
                    cursor.execute(self.get_update_endtime_sql(), (session_id,))
                    conn.commit()
                except sqlite3.Error as e:
                    print(f"SQLite error during session update: {e}")
                except sqlite3.OperationalError as e:
                    print(f"SQLite error during session update: {e}")
                
                # Sleep for 1 minute
                time.sleep(60)
            conn.close()

        self.update_thread = threading.Thread(target=run)
        self.update_thread.daemon = True
        self.update_thread.start()

    def close_session(self, session_id):
        """
        Stops the background update thread and updates the end time of the specified session to mark it as closed.

        Parameters:
            session_id (str): The unique ID of the session to be closed.
        """
        self.update_thread_running = False
        if self.update_thread is not None:
            self.update_thread.join()

        conn = self.get_new_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(self.get_update_endtime_sql(), (session_id,))
            conn.commit()
        except sqlite3.Error as e:
            print(f"SQLite error during session update: {e}")
        except sqlite3.OperationalError as e:
            print(f"SQLite error during session update: {e}")
        conn.close()
