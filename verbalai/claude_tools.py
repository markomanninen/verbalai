# claude_tools.py - Contains the schema for the function calling tools that can be used in 
# the Claude API (beta) from 4.4.2024 on.
#
# Schemas contain tools such as:
# - assign_category to assign a category to a discussion
# - modify_discussion to rename a discussion
# - remove_category to remove a category from a discussion
# - retrieve_dialogue_unit_by_id to query a database of conversation prompt-response entries 
#       using a specific dialogue unit entry ID
# - retrieve_discussion_by_id to query a database of conversations using a specific discussion ID
# - find_discussions to query a database of discussions based on various criteria, including title, 
#       featured, starttime, endtime, and category
# - find_dialogue_units to query a database of dialogue units based on various criteria, 
#       including phrase, topic, sentiment, intent, starttime, endtime, prompt, and response
#
# Each schema is used parse user prompts to choose the correct tool and return arguments for
# calling the tool. A typical user query for each tool would be:
# - assign_category: "Assign category 'name' with score 'score' to discussion 'discussion_id'"
# - modify_discussion: "Modify discussion 'discussion_id' with title 'title' and featured 'featured'"
# - remove_category: "Remove category 'name' from discussion 'discussion_id'"
# - retrieve_dialogue_unit_by_id: "Retrieve dialogue unit by ID 'dialogue_unit_id'"
# - retrieve_discussion_by_id: "Retrieve discussion by ID 'discussion_id'"
# - find_discussions: "Find discussions with title 'title', featured 'featured', starttime 'starttime',
#       endtime 'endtime', and category 'category'"
# - find_dialogue_units: "Find dialogue units with phrase 'phrase', limit 'limit', offset_page 'offset_page',
#       topic 'topic', sentiment 'sentiment', intent 'intent', starttime 'starttime', endtime 'endtime',
#       prompt 'prompt', response 'response', order_by 'order_by', and order_direction 'order_direction'"
#
# When used with a function calling in LLM, user prompt can be in natural human language, and the
# schema will parse the prompt to choose the correct tool and return arguments for calling the tool.
#
# For instance:
# - "Assign category 'Science Fiction' with score '0.93' to the current discussion, plase."
# - "Modify the discussion ID '1234' with the new name 'Tools are great!' and mark it featured."
# - "Eliminate the 'Solar Power' category from the previous thread discussing AI ethics."
# - "Retrieve the dialogue unit with id 3."
# - "I'm looking for the specifics of the first discussion in the system; can you pull up the information?"
# - "Locate any discussions that have 'Machine Learning' in their title, starting from 2023-01-01."
# - "Get the second discussion session we have had."

schemas = {
    # You can add multiple tools under the same tool name
    # but they all use tokens when used in the tool chain
    "assign_category": [
        {
            "name": "assign_category",
            "description": "Assign Category to Discussion - Arguments to assign a category to a discussion.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "discussion_id": {
                        "description": "The unique identifier of the discussion to which a category is being assigned.",
                        "oneOf": [
                            {
                                "type": "string",
                                "enum": ["current", "latest", "previous", "last", "first", "earliest", "newest", "oldest", "active", "featured"]
                            },
                            {
                                "type": "integer"
                            }
                        ]
                    },
                    "category": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "The name of the category."
                            },
                            "score": {
                                "type": "number",
                                "description": "The score or relevance of the category to the discussion. Must be between 0.0 and 1.0."
                            }
                        },
                        "required": ["name"],
                        "additionalProperties": False
                    }
                },
                "required": ["discussion_id", "category"],
                "additionalProperties": False
            }
        }
    ],
    "modify_discussion": [
        {
            "name": "modify_discussion",
            "description": "Modify Discussion Name and Feature Flag - Arguments to rename a discussion.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "discussion_id": {
                        "description": "The unique identifier of the discussion for which the name is modified.",
                        "oneOf": [
                            {
                                "type": "string",
                                "enum": ["current", "latest", "previous", "last", "first", "earliest", "newest", "oldest", "active", "featured"]
                            },
                            {
                                "type": "integer"
                            }
                        ]
                    },
                    "title": {
                        "type": "string",
                        "description": "The title of the discussion."
                    },
                    "featured": {
                        "type": "boolean",
                        "description": "The featured flag of the discussion."
                    }
                },
                # Required fields (either title or featured) are not definable here because the schema
                # does not allow for conditional requirements like anyOf, oneOf, or allOf at this level.
                "required": ["discussion_id"],
                "additionalProperties": False
            }
        }
    ],
    "remove_category": [
        {
            "name": "remove_category",
            "description": "Remove Category from Discussion - Arguments to remove a category from a discussion.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "discussion_id": {
                        "description": "The unique identifier of the discussion from which a category is being removed.",
                        "oneOf": [
                            {
                                "type": "string",
                                "enum": ["current", "latest", "previous", "last", "first", "earliest", "newest", "oldest", "active", "featured"]
                            },
                            {
                                "type": "integer"
                            }
                        ]
                    },
                    "name": {
                        "type": "string",
                        "description": "The name of the category to remove."
                    }
                },
                "required": ["discussion_id", "name"],
                "additionalProperties": False
            }
        }
    ],
    "retrieve_dialogue_unit_by_id": [
        {
            "name": "retrieve_dialogue_unit_by_id",
            "description": "Retrieve Dialogue Unit by ID - Arguments to query a database of conversation prompt-response entries using a specific dialogue unit entry ID. Entries are topical prompt-response pairs assigned to discussion sessions. Synonyms for dialogue unit are for instance prompt-response pair, conversation piece, chat fragment, discussion element, and interaction record.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "dialogue_unit_id": {
                        "type": "integer",
                        "description": "The unique identifier of the dialogue unit to retrieve."
                    }
                },
                "required": ["dialogue_unit_id"],
                "additionalProperties": False
            }
        }
    ],
    "retrieve_discussion_by_id": [
        {
            "name": "retrieve_discussion_by_id",
            "description": "Retrieve Discussion by ID - Arguments to query a database of conversations using a specific discussion ID. Synonyms for conversation are for instance: session, discussion, and chat.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "discussion_id": {
                        "description": "The unique identifier of the discussion to be retrieved. Special strings like current, latest, previous, last, and first are interpreted internally.",
                        "oneOf": [
                            {
                                "type": "string",
                                "enum": ["current", "latest", "previous", "last", "first", "earliest", "newest", "oldest", "random", "active", "featured"]
                            },
                            {
                                "type": "integer"
                            }
                        ]
                    }
                },
                "additionalProperties": False,
                "required": ["discussion_id"]
            }
        }
    ],
    "find_discussions": [
        {
            "name": "find_discussions",
            "description": "Find Discussions - Arguments to query a database of discussions based on various criteria, including title, featured, starttime, endtime, and category. Synonyms for discussion are for instance session, conversation, and chat. Discussion entries are distinct from dialogue unit entries. In a tool chain find_discussions usually folowed by a retrieve_discussion_by_id tool, which is followed by a find_dialogue_units tool, and finally retrieve_dialogue_unit_by_id tool.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": ["string", "null"],
                        "description": "Title for filtering discussions using a LIKE operator, which allows for partial matches. Distinct from category name. Might be referenced to by name or title."
                    },
                    "featured": {
                        "type": ["boolean", "null"],
                        "description": "Featured flag for filtering discussions."
                    },
                    "starttime_start": {
                        "type": ["string", "null"],
                        "description": "Start of the start time range for filtering discussions, in ISO 8601 format.",
                        #"pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}$"
                    },
                    "endtime_start": {
                        "type": ["string", "null"],
                        "description": "End of the start time range for filtering discussions, in ISO 8601 format.",
                        #"pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}$"
                    },
                    "starttime_end": {
                        "type": ["string", "null"],
                        "description": "Start of the end time range for filtering discussions, in ISO 8601 format.",
                        #"pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}$"
                    },
                    "endtime_end": {
                        "type": ["string", "null"],
                        "description": "End of the end time range for filtering discussions, in ISO 8601 format.",
                        #"pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}$"
                    },
                    "category": {
                        "type": "object",
                        "description": "Filter discussions by a specific category, including its name and score. Might be referenced by category name or tag. Distinct from discussion title and dialogue unit topic. Allows filtering category by score. Use '> 0.5', '< 0.5', '= 0.5', '>= 0.5', '<= 0.5' to filter categories by score conditions.",
                        "properties": {
                            "name": {
                                "type": ["string", "null"],
                                "description": "The name of the category."
                            },
                            "score": {
                                "type": ["string", "null"],
                                # >=, <=, >, <, = 0.0 - 1.0
                                "pattern": "^(>=|<=|>|<|=)\\s*\\d+(\\.\\d+)?$",
                                "description": "Condition for filtering discussions by category score. Number must be between 0.0 and 1.0 and must be prefixed by equality operator. Specify conditions using '>= X', '<= X', '> X', '< X', or '= X'."
                            }
                        },
                        "required": ["name"],
                        "additionalProperties": False
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of discussions to return. Can be 10 at most. Use offset_page to paginate the results.",
                        "default": 3
                    },
                    "offset_page": {
                        "type": "integer",
                        "description": "Paging offset to paginate the results.",
                        "default": 0
                    },
                    "order_by": {
                        "type": "string",
                        "description": "Order the results by a specific field.",
                        "enum": ["title", "starttime", "endtime", "category", "featured"],
                        "default": "starttime"
                    },
                    "order_direction": {
                        "type": "string",
                        "description": "Order direction for the results.",
                        "enum": ["ASC", "DESC"],
                        "default": "ASC"
                    }
                },
                # Required fields are not definable here because the schema
                # does not allow for conditional requirements like anyOf, oneOf, or allOf at this level.
                "additionalProperties": False
            }
        }
    ],
    "find_dialogue_units": [
        {
            "name": "find_dialogue_units",
            "description": "Find Dialogue Units - Arguments to query a database of dialogue units based on various criteria, including phrase, topic, sentiment, intent, starttime, endtime, prompt, and response. Note: Synonyms for dialogue unit are for instance prompt-response pair, conversation piece, chat fragment, discussion element, and interaction record. Dialogue units are distinct from discussion session entries. In a tool chain find_dialogue_units usually followed by a retrieve_dialogue_unit_by_id tool.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "discussion_id": {
                        "description": "The unique identifier of the discussion to be retrieved. Special strings like current, latest, previous, last, and first are interpreted internally.",
                        "oneOf": [
                            {
                                "type": "string",
                                "enum": ["current", "latest", "previous", "last", "first", "earliest", "newest", "oldest", "random", "active", "featured"]
                            },
                            {
                                "type": "integer"
                            }
                        ]
                    },
                    "phrase": {
                        "type": ["string", "null"],
                        "description": "The query phrase will be compared/matched against dialogue units for semantic similarity of prompt-response texts in the vector storage."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of dialogue units to return. Can be 10 at most. Use offset_page to paginate the results.",
                        "default": 3
                    },
                    "offset_page": {
                        "type": "integer",
                        "description": "Paging offset to paginate the results.",
                        "default": 0
                    },
                    "topic": {
                        "type": ["string", "null"],
                        "description": "Filter dialogue units with a specific topic using an exact match. Topic name must be specified as a single-word identifier in Titlecase (e.g., 'Topic1')."
                    },
                    "sentiment": {
                        "type": "object",
                        "description": "Filter dialogue units based on sentiment scores. Allows filtering by specifying conditions for positive, negative, and neutral scores. Use '> 0.5', '< 0.5', '= 0.5', '>= 0.5', '<= 0.5' to filter dialogue units by score conditions.",
                        "properties": {
                        "positive_score": {
                            "type": ["string", "null"],
                            # >=, <=, >, <, = 0.0 - 1.0
                            "pattern": "^(>=|<=|>|<|=)\\s*\\d+(\\.\\d+)?$",
                            "description": "Condition for filtering dialogue units by score. Number must be between 0.0 and 1.0 and must be prefixed by equality operator. Specify conditions using '>= X', '<= X', '> X', '< X', or '= X'."
                        },
                        "negative_score": {
                            "type": ["string", "null"],
                            # >=, <=, >, <, = 0.0 - 1.0
                            "pattern": "^(>=|<=|>|<|=)\\s*\\d+(\\.\\d+)?$",
                            "description": "Condition for filtering dialogue units by score. Number must be between 0.0 and 1.0 and must be prefixed by equality operator. Specify conditions using '>= X', '<= X', '> X', '< X', or '= X'."
                        }
                        },
                        "anyOf": [
                            {"required": ["positive_score"]},
                            {"required": ["negative_score"]}
                        ],
                        "additionalProperties": False
                    },
                    "intent": {
                        "type": ["string", "null"],
                        "description": "Filter dialogue units with a specific intent using an exact match. Intents are lowercase single-word identifiers."
                    },
                    "starttime": {
                        "type": ["string", "null"],
                        "description": "Start of the timestamp range for filtering dialogue units, in ISO 8601 format.",
                        #"pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}$"
                    },
                    "endtime": {
                        "type": ["string", "null"],
                        "description": "End of the timestamp range for filtering dialogue units, in ISO 8601 format.",
                        #"pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}$"
                    },
                    "prompt": {
                        "type": ["string", "null"],
                        "description": "Filter dialogue units by a specific phrase from the user's prompt/input using a LIKE operator, which allows for partial matches."
                    },
                    "response": {
                        "type": ["string", "null"],
                        "description": "Filter dialogue units by a specific phrase from a response to the user's prompt using a LIKE operator, which allows for partial matches."
                    },
                    "order_by": {
                        "type": "string",
                        "description": "Order the results by a specific field.",
                        "enum": ["phrase", "timestamp", "topic", "intent", "prompt", "response"],
                        "default": "timestamp"
                    },
                    "order_direction": {
                        "type": "string",
                        "description": "Order direction for the results.",
                        "enum": ["ASC", "DESC"],
                        "default": "DESC"
                    }
                },
                # Required fields are not definable here because the schema
                # does not allow for conditional requirements like anyOf, oneOf, or allOf at this level.
                "additionalProperties": False
            }
        }
    ]
}
