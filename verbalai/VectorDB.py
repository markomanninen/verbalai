# VectorDB.py - A Python module for storing and searching vectors using SQLite and Annoy.
import sqlite3
from annoy import AnnoyIndex
from transformers import AutoTokenizer, AutoModel
import torch
import os
import pytz
from datetime import datetime, timezone

from .SessionManager import SessionManager
# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import log lonfig as a side effect only
from verbalai import log_config
import logging
logger = logging.getLogger(__name__)

def get_timezone_offset(tz_name):
    """
    Returns the timezone offset in minutes from UTC for a given timezone name.

    :param tz_name: String, the name of the timezone (e.g., 'Europe/Helsinki')
    :return: int, offset in minutes from UTC
    """
    tz = pytz.timezone(tz_name)
    # Using now() to get the current datetime might bring DST into consideration
    now_utc = datetime.now(timezone.utc)
    now_tz = now_utc.astimezone(tz)
    # Offset in minutes
    return int(now_tz.utcoffset().total_seconds() / 60)


def parse_condition(condition):
    """Parse a condition string into an operator and a value."""
    # Default operator and value
    operator = '='
    value = condition

    # Supported operators
    # Order of the items in a list makes difference!
    operators = ['>=', '<=', '>', '<', '=']
    
    # Find and separate the operator from the value
    for op in operators:
        if condition.startswith(op):
            operator = op
            # Extract the value after the operator
            value = condition.lstrip(op)
            break
    
    # Try converting the value part to a float
    try:
        value = float(value)
    except ValueError:
        # Handle or log error if the value is not a valid number
        print(f"Invalid condition value: {value}")
        raise
    
    return operator, 1.0 if value > 1.0 else (0.0 if value < 0.0 else value)

def parse_score_condition(condition):
    """Parse a score condition string into an operator and a value."""
    return parse_condition(condition)


def parse_cost_condition(condition):
    """Parse a cost condition string into an operator and a value."""
    return parse_condition(condition)

class VectorDB:
    """ A Python class for storing and searching vectors using SQLite and Annoy. """
    
    def __init__(self, db_path='verbalai_db.sqlite', index_path='verbalai_db.ann', model_name='sentence-transformers/all-MiniLM-L6-v2', embedding_dim=384, timezone="Europe/Helsinki"):
        """ Initialize the VectorDB class. """
        self.db_path = db_path
        # Vector db (annay) attributes
        self.index_path = index_path
        self.embedding_dim = embedding_dim
        self.model_name = model_name
        # SQLite is not so good with timezones
        # We need to adjust datetimes in each relevant query
        self.timezone = timezone
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModel.from_pretrained(self.model_name)
        self.index = AnnoyIndex(self.embedding_dim, 'angular')
        # To determine, if dialogue unit indexing should be done in the clean up process
        self.new_data_added = False
        # Discussion / session related attributes
        self.session_id = None
        self.previous_discussion = None
        self.current_discussion_id = None
        self.latest_discussion_id = None
        self.first_discussion_date = None
        self.load_or_initialize_index()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        if not self.check_tables_exist():
            self._init_db()
    
    def set_first_discussion_date(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT starttime FROM discussions ORDER BY starttime ASC LIMIT 1")
        row = cursor.fetchone()
        self.first_discussion_date = row[0]

    def set_latest_discussion_id(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT MAX(id) FROM discussions")
        row = cursor.fetchone()
        self.latest_discussion_id = row[0] if row else 0
        try:
            self.previous_discussion = self.retrieve_discussion_by_id(self.latest_discussion_id)
        except ValueError:
            self.previous_discussion = {}
    
    def set_current_session_discussion_id(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM discussions WHERE session_id = ?", (self.session_id,))
        row = cursor.fetchone()
        self.current_discussion_id = row[0] if row else 0
    
    def get_latest_featured_discussion_id(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM discussions WHERE featured = 1 ODER BY starttime DESC LIMIT 1")
        row = cursor.fetchone()
        return row[0] if row else 0
    
    def get_random_discussion_id(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM discussions ORDER BY RANDOM() LIMIT 1")
        row = cursor.fetchone()
        return row[0] if row else 0
    
    def retrieve_data_entry(self, field, value):
        """ Retrieve a data entry from the database. """
        cursor = self.conn.cursor()
        if field in ["id", "key", "key_group"]:
            cursor.execute(f'SELECT key, value FROM data WHERE {field} = ?', (value,))
        else:
            raise ValueError("Invalid field provided. Use 'id', 'key', or 'key_group'.")
        return [{"key": row[0], "value": row[1]} for row in cursor.fetchall()]
    
    def upsert_data_entry(self, key, value, key_group):
        """ Insert or update a data entry in the database. """
        cursor = self.conn.cursor()
        # Update is done via primary key (id) or unique key (key, key_group) conflict check
        cursor.execute('INSERT OR REPLACE INTO data (key, value, key_group, updated) VALUES (?, ?, ?, CURRENT_TIMESTAMP)', (key, value, key_group))
        self.conn.commit()
    
    def update_discussion_cost(self, cost):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE discussions SET cost = ? WHERE id = ?", (cost, self.current_discussion_id))
        self.conn.commit()
    
    def retrieve_last_discussion_summaries(self, max_results=3):
        # SQL to retrieve last three dialogues with 'summary' intent
        cursor = self.conn.cursor()
        sql_query = '''
            SELECT du.prompt
            FROM dialogue_units AS du
            WHERE du.intent = 'create_summary'
            ORDER BY du.timestamp DESC
            LIMIT ?
        '''
        params = (max_results, )
        cursor.execute(sql_query, params)
        return "\n\n".join([row[0] for row in cursor.fetchall()])
    
    def check_tables_exist(self):
        """Check if the key tables exist in the database to determine if initialization is needed."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='discussions'")
        return bool(cursor.fetchone())

    def create_new_session(self):
        
        # Set the latest/previous discussion ID before creating a new session
        self.set_latest_discussion_id()
        
        self.session_id = SessionManager(
            self.db_path, 
            session_table_name="discussions",
            session_table_id_field="session_id", 
            session_table_endtime_field="endtime").create_new_session()
        
        self.set_first_discussion_date()
        # Set the current discussion ID after creating a new session
        self.set_current_session_discussion_id()
        
        return self.session_id
    
    def load_or_initialize_index(self):
        """ Load an existing index or initialize a new one. """
        if os.path.exists(self.index_path):
            logger.info("Loading existing index.")
            self.index.load(self.index_path)
        else:
            # File will be created only after the first insert to the index
            logger.info("Creating a new vector index.")

    def _init_db(self):
        """ Initialize the SQLite database. """
        cursor = self.conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS data (
            id INTEGER PRIMARY KEY,
            key TEXT NOT NULL,
            value TEXT,
            key_group TEXT,
            updated TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (key, key_group)
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS discussions (
            id INTEGER PRIMARY KEY,
            session_id TEXT UNIQUE NOT NULL,
            title TEXT,
            starttime TEXT DEFAULT CURRENT_TIMESTAMP,
            endtime TEXT,
            featured INTEGER default 0,
            cost REAL default 0.0
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS dialogue_units (
            id INTEGER PRIMARY KEY,
            prompt TEXT,
            response TEXT,
            intent TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            discussion_id TEXT,
            FOREIGN KEY (discussion_id) REFERENCES discussions(id)
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS dialogue_unit_topics (
            dialogue_unit_id INTEGER,
            topic_id INTEGER,
            FOREIGN KEY (dialogue_unit_id) REFERENCES dialogue_units(id),
            FOREIGN KEY (topic_id) REFERENCES topics(id),
            PRIMARY KEY (dialogue_unit_id, topic_id)
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY,
            name TEXT,
            score REAL,
            discussion_id INTEGER,
            FOREIGN KEY (discussion_id) REFERENCES discussions(id)
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS sentiment_scores (
            dialogue_unit_id INTEGER,
            positive_score REAL,
            negative_score REAL,
            FOREIGN KEY (dialogue_unit_id) REFERENCES dialogue_units(id),
            PRIMARY KEY (dialogue_unit_id)
        )''')
        self.conn.commit()

    def vectorize_text(self, text):
        """ Vectorize the input text using the model. """
        inputs = self.tokenizer(text, return_tensors='pt', max_length=512, truncation=True, padding=True)
        with torch.no_grad():
            outputs = self.model(**inputs)
            embeddings = outputs.pooler_output
            embeddings = embeddings.squeeze().numpy()
        return embeddings

    def add_dialogue_unit(self, prompt, response, topics=[], sentiment={}, intent=None):
        """ Index a new entry to the current discussion. """
        cursor = self.conn.cursor()
        cursor.execute('INSERT INTO dialogue_units (prompt, response, intent, discussion_id) VALUES (?, ?, ?, ?)', (prompt, response, intent, self.current_discussion_id))
        dialogue_unit_id = cursor.lastrowid
        
        # Insert sentiment scores
        if sentiment and any([sentiment.get('positive_score', False), sentiment.get('negative_score', False)]):
            cursor.execute('INSERT INTO sentiment_scores (dialogue_unit_id, positive_score, negative_score) VALUES (?, ?, ?)', 
                (dialogue_unit_id, sentiment.get('positive_score', 0), sentiment.get('negative_score', 0)))
        
        self.conn.commit()
        
        # It is expensive to build index everytime new dialogue init is created
        # Thats why, if self.new_data_added is set true, on clean-up process index is rebuilt.
        #self.rebuild_index()
        
        # Insert topics
        for topic in topics:
            self.add_topic(topic)
            self.link_topic_to_dialogue_unit(dialogue_unit_id, topic)
        
        self.new_data_added = True
    
    def extract_discussion_id(self, discussion_id, include_random=False):
        
        if not discussion_id:
            raise ValueError("Discussion ID is required.")
        
        if isinstance(discussion_id, int):
            return discussion_id
        
        if discussion_id.isdigit():
            return int(discussion_id)
        
        # Validate or resolve the discussion_id if it's a special keyword
        enum = ["current", "latest", "previous", "last", "first", "earliest", "newest", "oldest", "active", "featured"]
        
        if include_random:
            enum.append("random")
        
        discussion_id = discussion_id.lower()
        
        if discussion_id in enum:
            if discussion_id == "random":
                return self.get_random_discussion_id()
            elif discussion_id == "featured":
                return self.get_latest_featured_discussion_id()
            else:
                switcher = {
                    "current": self.current_discussion_id,
                    "active": self.current_discussion_id,
                    
                    "latest": self.latest_discussion_id,
                    "previous": self.latest_discussion_id,
                    "last": self.latest_discussion_id,
                    "newest": self.latest_discussion_id,
                    
                    "first": 1,
                    "earliest": 1,
                    "oldest": 1
                }
                return switcher.get(discussion_id)
        else:
            raise ValueError("Invalid discussion ID provided.")
    
    def discussion_exists(self, discussion_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT id FROM discussions WHERE id = ?', (discussion_id,))
        return bool(cursor.fetchone())
    
    def modify_discussion(self, discussion_id, title=None, featured=None):
        
        if not self.discussion_exists(discussion_id):
            raise ValueError(f"No discussion found with ID: {discussion_id}")
        
        if title is None and featured is None:
            raise ValueError("At least one of the following arguments should be provided: title, featured")
        
        # Construct the SQL update statement based on provided arguments
        updates = []
        params = []
        
        if title is not None:
            # It is possible to reset the title to empty string
            updates.append("title = ?")
            params.append(title)
        
        if featured is not None:
            updates.append("featured = ?")
            # SQLite uses integers for boolean values
            params.append(1 if featured else 0)
        
        params.append(discussion_id)
        sql_query = f"UPDATE discussions SET {', '.join(updates)} WHERE id = ?"
        
        cursor = self.conn.cursor()
        cursor.execute(sql_query, params)
        self.conn.commit()

    def assign_category(self, discussion_id, category):
        cursor = self.conn.cursor()
        cursor.execute('INSERT INTO categories (name, score, discussion_id) VALUES (?, ?, ?)', 
            (category['name'].lower().title(), round(float(category['score']), 2), discussion_id))
        self.conn.commit()
    
    def remove_category(self, discussion_id, name):
        cursor = self.conn.cursor()
        # First, check if the category exists
        cursor.execute('SELECT * FROM categories WHERE discussion_id = ? AND name = ?', (discussion_id, name))
        category = cursor.fetchone()
        
        if category is None:
            # If the category does not exist, raise ValueError
            raise ValueError(f"Category named '{name}' for discussion_id {discussion_id} not found.")
        
        cursor.execute('DELETE FROM categories WHERE discussion_id = ? AND name = ?', 
            (discussion_id, name))
        self.conn.commit()
    
    def retrieve_categories(self, discussion_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT name, score FROM categories WHERE discussion_id = ?', (discussion_id,))
        return [{"name": row[0], "score": row[1]} for row in cursor.fetchall()]
        
    def add_topic(self, topic_name):
        """ Add a new topic to the topics table. """
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO topics (name) VALUES (?)", (topic_name,))
        self.conn.commit()

    def link_topic_to_dialogue_unit(self, dialogue_unit_id, topic_name):
        """ Link a topic to a conversation in the conversation_topics table. """
        cursor = self.conn.cursor()
        # Retrieve topic id by unique name
        cursor.execute('SELECT id FROM topics WHERE name = ?', (topic_name,))
        topic_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO dialogue_unit_topics (dialogue_unit_id, topic_id) VALUES (?, ?)", (dialogue_unit_id, topic_id))
        self.conn.commit()

    def rebuild_index(self, force_build_all=False):
        """ Rebuild the Annoy index with all entries from the database. """
        if self.new_data_added or force_build_all:
            # Reinitialize the index to start fresh
            self.index = AnnoyIndex(self.embedding_dim, 'angular')
            
            # Fetch all entries from the database
            cursor = self.conn.cursor()
            cursor.execute('SELECT id, prompt, response FROM dialogue_units')
            entries = cursor.fetchall()
            
            # Iterate over all entries and add their vectors to the index
            for entry_id, prompt, response in entries:
                vector_prompt = self.vectorize_text(prompt)
                vector_response = self.vectorize_text(response)
                # Using entry_id * 2 and entry_id * 2 + 1 to distinguish between prompt and response
                # See decode_id in find_similar_within_ids
                self.index.add_item(entry_id * 2, vector_prompt)
                self.index.add_item(entry_id * 2 + 1, vector_response)
            
            # Build the index with a specified number of trees
            # Adjust the number of trees if necessary
            self.index.build(10)
            self.index.save(self.index_path)
            logger.info("Rebuilt and saved the index.")
    
    def find_similar_within_ids(self, vector, limit, allowed_ids):
        # Perform the unrestricted search
        all_ids, distances = self.index.get_nns_by_vector(vector, n=limit*10, include_distances=True)  # Increase n if needed
        logger.info("find_similar_within_ids: %s distances: %s" % (all_ids, list(map(lambda x: round(x, 3), distances))))
        
        # Rebuild_index uses special indexing to separate prompt and response
        # But is requires to decode indices back to dialogue unit ids
        def decode_id(id):
            if id % 2 == 0:  # Even, representing a prompt
                return id // 2
            else:  # Odd, representing a response
                return (id - 1) // 2
        
        if allowed_ids:
            # Filter the results based on allowed_ids
            filtered_ids = []
            filtered_distances = []
            allowed_ids_set = set(allowed_ids)
            for id, distance in zip(all_ids, distances):
                id = decode_id(id)
                if id in allowed_ids_set and id not in filtered_ids:
                    filtered_ids.append(id)
                    filtered_distances.append(distance)
                    #if len(filtered_ids) >= limit:
                    #    break

            return filtered_ids, filtered_distances
        else:
            filtered_ids = []
            filtered_distances = []
            for id, distance in zip(all_ids, distances):
                id = decode_id(id)
                if id not in filtered_ids:
                    filtered_ids.append(id)
                    filtered_distances.append(distance)
                    #if len(filtered_ids) >= limit:
                    #    break
            return filtered_ids, filtered_distances

    def find_discussions(self, title=None, starttime_start=None, endtime_start=None, starttime_end=None, endtime_end=None, category=None, limit=5, offset_page=0, order_by="starttime", order_direction="ASC", featured=None, cost=None):
        """
        Finds discussions based on specified filters such as title, time range, and category.
        Allows for independent specification of start and end times.
        """
        if limit > 10:
            raise ValueError("The number of discussions to retrieve should be less than or equal to 10.")

        sql_query = "SELECT DISTINCT d.id FROM discussions d "
        params = []
        conditions = []

        # Title filter
        if title:
            conditions.append("d.title LIKE ?")
            params.append(f"%{title}%")

        # Featured filter
        if featured is not None:
            conditions.append("d.featured = ?")
            params.append(1 if featured else 0)

        # Time range filters - allowing for independent specification
        if starttime_start:
            conditions.append("d.starttime >= ?")
            params.append(starttime_start.replace("T", " "))
        if endtime_start:
            conditions.append("d.starttime <= ?")
            params.append(endtime_start.replace("T", " "))
        if starttime_end:
            conditions.append("d.endtime >= ?")
            params.append(starttime_end.replace("T", " "))
        if endtime_end:
            conditions.append("d.endtime <= ?")
            params.append(endtime_end.replace("T", " "))

        # Category filter
        if category and any(["name" in category, "score" in category]):
            sql_query += "JOIN categories c ON d.id = c.discussion_id "
            if "name" in category:
                conditions.append("c.name = ?")
                params.append(category["name"])
            if "score" in category:
                condition, value = parse_score_condition(category["score"])
                conditions.append(f"c.score {condition} ?")
                params.append(value)
        
        # Cost filter
        if cost:
            condition, value = parse_cost_condition(cost)
            conditions.append(f"d.cost {condition} ?")
            params.append(value)

        # Adding WHERE conditions
        if conditions:
            sql_query += " WHERE " + " AND ".join(conditions)

        # Ordering
        order_by_valid_fields = ["title", "starttime", "endtime", "featured", "cost"]
        if order_by in order_by_valid_fields:
            sql_query += f" ORDER BY d.{order_by} {order_direction.upper()}"

        # Pagination
        sql_query += " LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset_page * limit)

        # Execute query
        cursor = self.conn.cursor()
        cursor.execute(sql_query, params)
        logger.info(sql_query)
        logger.info(params)
        return [row[0] for row in cursor.fetchall()]

    def find_dialogue_units(self, phrase=None, limit=5, offset_page=0, **filters):
        """
        Find similar entries based on the input text or other attributes.
        The filters include topic, sentiment, intent, prompt, response, starttime, endtime, order_by, and order_direction.
        """
        if limit > 10:
            raise ValueError("The number of similar entries to retrieve should be less than or equal to 10.")
        
        sql_query, params = self.construct_sql_query(**filters)
        
        ids = []
            
        if not phrase:
            sql_query += " LIMIT ? OFFSET ?"
            params.append(limit)
            params.append(offset_page * limit)
        
        logger.info(sql_query)
        logger.info(params)
        
        cursor = self.conn.cursor()
        logger.info(sql_query)
        cursor.execute(sql_query, params)
        ids = [row[0] for row in cursor.fetchall()]
        
        if phrase:
            
            vector = self.vectorize_text(phrase)
            ids, distances = self.find_similar_within_ids(vector, limit, ids)
            
            if not ids:
                return [], []
            
            # Assuming order_direction is passed as a parameter to find_similar and defaults to 'ASC'
            reverse_order = ("order_direction" in filters and filters["order_direction"] == 'ASC')
            
            # Apply offset and limit
            offset = offset_page * limit
            
            if reverse_order:
            
                # Sort based on distances (no need for the redundant check)
                sorted_results = sorted(zip(ids, distances), key=lambda x: x[1], reverse=reverse_order)

                sorted_results = sorted_results[offset:offset + limit]
                
                if not sorted_results:  # Check if the slicing resulted in an empty list
                    return [], []
                
                # Unzip the results for final output
                return zip(*sorted_results)
            
            else:
                return ids[offset:offset + limit], distances[offset:offset + limit]
            
        else:
            # Directly use IDs from SQL query if no text is provided
            distances = [None for _ in ids]
            return ids, distances
    
    def construct_sql_query(self, topic=None, sentiment=None, intent=None, prompt=None, response=None, discussion_id=None, starttime=None, endtime=None, order_by="timestamp", order_direction="DESC"):
        """
        Constructs a single SQL query to fetch conversation IDs based on provided filters, including order and limit.
        """
        query = """
        SELECT DISTINCT du.id 
        FROM dialogue_units du
        """
        params = []
        conditions = []
        # Topic filter
        if topic:
            query += """
            JOIN dialogue_unit_topics dut ON du.id = dut.dialogue_unit_id
            JOIN topics t ON dut.topic_id = t.id
            """
            conditions.append("t.name = ?")
            params.append(topic)
        
        # Sentiment filter
        if sentiment:
            query += """
            JOIN sentiment_scores ss ON du.id = ss.dialogue_unit_id
            """
            # Assuming sentiment is a dictionary with 'positive' and 'negative' as possible keys
            # and values are conditions like '> 0.5'
            for key, value in sentiment.items():
                key = key.lower().replace("_score", "")
                condition, value = parse_score_condition(value)
                conditions.append(f"ss.{key}_score {condition} ?")
                params.append(value)

        # Default session value is False because we dont want to return entries that are possibly in the
        # message context window
        if discussion_id is not None:
            query += """
            JOIN discussions d ON du.discussion_id = d.id
            """
            discussion_id = self.extract_discussion_id(discussion_id, include_random=True)
            # Assume session id
            conditions.append(f"d.id = ?")
            params.append(discussion_id)
        else:
            
            # Additional filters
            if intent:
                conditions.append("du.intent = ?")
                params.append(intent)
            
            if prompt:
                conditions.append("du.prompt LIKE ?")
                params.append('%' + prompt + '%')
            
            if response:
                conditions.append("du.response LIKE ?")
                params.append('%' + response + '%')

            # Timestamps
            if starttime and endtime:
                conditions.append("du.timestamp BETWEEN ? AND ?")
                params.extend([starttime.replace("T", " "), endtime.replace("T", " ")])
            elif starttime:
                conditions.append("du.timestamp >= ?")
                params.append(starttime.replace("T", " "))
            elif endtime:
                conditions.append("du.timestamp <= ?")
                params.append(endtime.replace("T", " "))

        # Adding WHERE conditions
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        order_direction = order_direction.upper()
        order_direction = "ASC" if order_direction != "DESC" else "DESC"
        # Ordering
        if order_by in ["timestamp", "intent", "prompt", "response"]:
            query += f" ORDER BY du.{order_by} {order_direction}"
        elif topic and order_by == "topic":
            query += f" ORDER BY t.name {order_direction}"

        return query, params

    def retrieve_discussion_by_id(self, discussion_id):
        """Retrieve discussion by ID along with the count of associated dialogue units."""
        cursor = self.conn.cursor()
        # Retrieve the main discussion details
        cursor.execute('SELECT starttime, title, endtime, featured, cost FROM discussions WHERE id = ?', (discussion_id,))
        discussion = cursor.fetchone()

        if discussion:
            # Retrieve the count of associated dialogue units
            cursor.execute('SELECT COUNT(*) FROM dialogue_units WHERE discussion_id = ?', (discussion_id,))
            dialogue_unit_count = cursor.fetchone()[0]

            # Retrieve categories associated with the discussion
            categories = self.retrieve_categories(discussion_id)

            return {
                "discussion_id": discussion_id,
                "starttime": discussion[0],
                "title": discussion[1],
                "endtime": discussion[2],
                "featured": bool(discussion[3]),
                "cost": discussion[4],
                "dialogue_unit_count": dialogue_unit_count,
                "categories": categories
            }
        else:
            raise ValueError(f"No discussion found with ID: {discussion_id}")

    
    def retrieve_dialogue_unit_by_id(self, dialogue_unit_id):
        """Retrieve an entry by ID along with its topics."""
        cursor = self.conn.cursor()

        # Retrieve the main entry details
        cursor.execute('SELECT timestamp, prompt, response, intent, discussion_id FROM dialogue_units WHERE id = ?', (dialogue_unit_id,))
        dialogue_unit = cursor.fetchone()

        if dialogue_unit:
            # Retrieve the associated topics for the entry
            cursor.execute('''
            SELECT t.name FROM topics t
            JOIN dialogue_unit_topics dut ON t.id = dut.topic_id
            WHERE dut.dialogue_unit_id = ?
            ''', (dialogue_unit_id,))
            topics = [row[0] for row in cursor.fetchall()]
            
            # Retrieve sentiment scores
            cursor.execute('SELECT positive_score, negative_score FROM sentiment_scores WHERE dialogue_unit_id = ?', (dialogue_unit_id,))
            sentiment_scores = cursor.fetchone()
            
            # Initialize sentiment dictionary
            sentiment = {}
            if sentiment_scores:
                sentiment = {
                    "positive_score": sentiment_scores[0],
                    "negative_score": sentiment_scores[1]
                }
            
            # Retrieve discussion
            discussion_id = dialogue_unit[4]
            cursor.execute('SELECT starttime, title, endtime, featured, cost FROM discussions WHERE id = ?', (discussion_id,))
            discussion_row = cursor.fetchone()
            discussion = { 
                "discussion_id": discussion_id, 
                "starttime": discussion_row[0], 
                "title": discussion_row[1], 
                "endtime": discussion_row[2],
                "featured": discussion_row[3],
                "cost": discussion_row[4],
                "categories": self.retrieve_categories(discussion_id)
            }

            return {
                "dialogue_unit_id": dialogue_unit_id,
                "timestamp": dialogue_unit[0],
                "prompt": dialogue_unit[1],
                "response": dialogue_unit[2],
                "intent": dialogue_unit[3],
                "topics": topics,
                "sentiment": sentiment,
                "discussion": discussion
            }
        else:
            raise ValueError(f"No dialogue unit found with ID: {dialogue_unit_id}")

    def retrieve_statistics(self, aggregation_type="count", aggregation_entity="topic", aggregation_grouping=None, **filters):
        try:
            # Validate input parameters
            valid_dimensions = ["topic", "intent", "timestamp", "sentiment", "category", "cost", "discussion_id", "dialogue_unit_id"]
            valid_stats = ["count", "average", "sum", "minimum", "maximum"]
            valid_filters = ["topic", "intent", "starttime", "endtime", "category"]

            # Valid groups are valid dimensions
            if not all([aggregation_entity in valid_dimensions, aggregation_type.lower() in valid_stats, aggregation_grouping in valid_dimensions or aggregation_grouping is None]):
                raise ValueError("Invalid aggregation type, entity, or group provided")
            
            if not all(k.lower() in valid_filters for k in filters.keys()):
                raise ValueError("Invalid filters provided")

            # Setup database cursor and initial SQL components
            cursor = self.conn.cursor()
            base_query = "SELECT {}{} FROM dialogue_units e"
            join_clause = " JOIN discussions d ON e.discussion_id = d.id"
            where_clause = " WHERE 1=1"
            group_by_clause = " GROUP BY {}"
            params = []
            
            # Timezone corrected timestamp field for datetime fields
            offset_minutes = get_timezone_offset(self.timezone)
            timestamp_field = f"strftime('%Y-%m-%dT%H:%M:%S', datetime(e.timestamp, '{int(offset_minutes)} minutes'))"
            
            aggregation_and_group_fields = {
                "dialogue_unit_id": "e.id",
                "cost": "d.cost",
                "intent": "e.intent",
                "discussion_id": "e.discussion_id",
                "timestamp": f"DATE({timestamp_field})",
                "sentiment": "(ss.positive_score - ss.negative_score)",
                "category": "c.name",
                "topic": "t.name"
            }
            # Determine the field for aggregation
            aggregation_field = aggregation_and_group_fields[aggregation_entity]

            # Set group by field, default to aggregation field if group_by is not specified
            group_by_field = aggregation_and_group_fields[aggregation_grouping] if aggregation_grouping and aggregation_field != aggregation_entity else None
            
            # Adjust joins based on required dimensions
            # NOTE: None checks (filters["sentiment"] != None) prevents limiting
            # results in joined tables in which there exists discussions/dialogue units
            if aggregation_entity == "sentiment" or ("sentiment" in filters and filters["sentiment"]):
                join_clause += " JOIN sentiment_scores ss ON e.id = ss.dialogue_unit_id"
            if aggregation_entity == "category" or ("category" in filters and filters["category"]):
                join_clause += " JOIN categories c ON d.id = c.discussion_id"
            if aggregation_entity == "topic" or ("topic" in filters and filters["topic"]):
                join_clause += " JOIN dialogue_unit_topics dut ON e.id = dut.dialogue_unit_id JOIN topics t ON dut.topic_id = t.id"

            # Construct SQL aggregation function
            aggregation_function = {
                "count": "COUNT(DISTINCT {})",
                "average": "AVG({})",
                "sum": "SUM({})",
                "minimum": "MIN({})",
                "maximum": "MAX({})"
            }[aggregation_type.lower()].format(aggregation_field)

            # Apply filters
            # NOTE: starttime and endtime filter fileds in discussions table are not supported
            if "starttime" in filters and filters["starttime"]:
                where_clause += f" AND {timestamp_field} >= ?"
                params.append(filters["starttime"])
            if "endtime" in filters and filters["endtime"]:
                where_clause += f" AND {timestamp_field} <= ?"
                params.append(filters["endtime"])
            if "topic" in filters and filters["topic"]:
                where_clause += " AND t.name = ?"
                params.append(filters["topic"])
            if "category" in filters and filters["category"]:
                where_clause += " AND c.name = ?"
                params.append(filters["category"])
            if "intent" in filters and filters["intent"]:
                where_clause += " AND e.intent = ?"
                params.append(filters["intent"])

            # Construct full SQL query
            query = base_query.format((f"{group_by_field}, " if group_by_field else ""), aggregation_function) + join_clause + where_clause + (group_by_clause.format(group_by_field) if group_by_field else "")
            # Logging the final query and parameters
            logging.info("Executing SQL Query: %s", query)
            logging.info("With parameters: %s", params)

            # Execute the query and return results
            cursor.execute(query, params)
            #statistics = {row[0]: row[1] for row in cursor.fetchall()}
            return cursor.fetchall()
        except Exception as e:
            logging.error("Failed to retrieve statistics: %s", str(e))
            raise
