import json

# System message part for the GPT model
previous_context = """
## Summary of the previous discussions

You can use the context from the previous conversation with the user to generate more coherent responses.

<<summary>>
"""

# NOTE: Below to be removed after checking if the schemas are good now
"""
This system allows user and AI to interact with various external tools to augment, manage and analyze discussions and dialogue units history.

### Assigns a category to a specified discussion

Input Parameters:
  Identifier of the discussion (accepts specific keywords like 'current', 'latest', etc., or an integer).
  Category object containing name (string) and score (number between 0.0 and 1.0).

### Modify the name and featured status of a discussion

Input Parameters:
  Identifier of the discussion (same as above).
  New title of the discussion.
  Boolean flag to mark the discussion as featured.

### Remove a specified category from a discussion

Input Parameters:
  Identifier of the discussion (same as above).
  Name of the category to be removed.

### Retrieve details of a discussion by its ID

Input Parameters:
  Identifier of the discussion to be retrieved (same as above).

### Retrieve details of a dialogue unit by its ID.

Input Parameters:
  Integer ID of the dialogue unit to retrieve.

### Search discussions based on provided criteria and return a list of matching discussions

Input Parameters:
  Filters such as title, featured, time ranges (starttime_start, endtime_start, etc.), category (with subfilters for name and score), and sorting options (order_by, order_direction).
  Pagination controls (limit, offset_page).

### Search dialogue units based on specified criteria and return a list of matching units

Input Parameters:
  Filters such as phrase, topic, sentiment (with subfilters like positive_score), intent, time ranges (starttime, endtime), and content (prompt, response).
  Pagination controls and sorting options similar to those in the "Find Discussions" tool.
"""

system_message_tools_human_format = """
## Function calling tools
<<tools>>
Function calling tools enhanges LLM chat functionality with permanent memory, searchable archived discussions, and cognitive capabilities.
"""

# TODO: the following description makes LLM to produce [Voice acticated] indicators which are not wanted:
# "You are able to listen and understand user speaking to microphone with a voice-to-text recognition service and speak aloud responses to user via speakers by text-to-speech service."
system_message = """
You are VerbalAI chatbot implemented as a command-line tool.

VerbalAI persona description: <<persona_description>>

Modify all outputs to exclude asterisks, action indicators, tone indicators, and any other special formatting characters. Responses should strictly consist of plain text without any annotations or symbols that are not part of standard written English. Ensure that responses are clear and straightforward, relying solely on natural language without any additional formatting or markers.
<<tools>>
*****

You are speaking with a user (username): <<username>>
Date and time is now: <<datetime>>
The current session's discussion id is: <<discussion_id>>
The first discussion between you and the user happened at: <<first_discussion_date>>
The previous discussion details are: <<previous_discussion>>
<<previous_context>>
"""


# Generate a summary -prompt
summary_generator_prompt = """
Generate a brief summary of the conversation given below:

<<summary>>
"""


tool_schemas = {
  "general": {
    "header": "You may control key-value properties such as user profile data in the storage with a function calling tool and arguments defined in the following schema. Prompts in human language, such as 'Update my location in user settings: Oberon.' would utilize these tools.",
    "schemas": {
      "upsert_data_entry": {
        "description": "Insert or update data entry including key, value, key_group (user_profile, general).",
        "arguments": {
          "type": "object",
          "properties": {
            "key": {
              "type": "string",
              "description": "Data property key."
            },
            "value": {
              "type": "string",
              "description": "Data property value."
            },
            "key_group": {
              "type": "string",
              "description": "Data key group property value.",
              "enum": ["user_profile", "general"]
            }
          },
          "required": ["key", "value", "key_group"],
          "additionalProperties": False
        }
      },
      "retrieve_data_entry": {
        "description": "Retrieve data entry/entries by key or key_group name corresponding given value.",
        "arguments": {
          "type": "object",
          "properties": {
            "field": {
              "type": "string",
              "description": "Data field name, key or key_group.",
              "enum": ["key", "key_group"]
            },
            "value": {
              "type": "string",
              "description": "Data field value, key or key_group."
            }
          },
          "required": ["field", "value"],
          "additionalProperties": False
        }
      }
    }
  },
  "discussion": {
    "header": "You can retrieve discussion memory entries with via function calling tools and arguments defined in the following schema. Prompts in human language, such as 'Find all discussions that we had yesterday.' would utilize these tools.",
    "definitions": {
      "discussionId": {
        "description": "The unique identifier of the discussion, supporting specific strings or integer IDs.",
        "oneOf": [
          {
            "type": "string",
            "enum": ["current", "previous", "first", "featured"]
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
      },
      "categorySearch": {
        "type": "object",
        "properties": {
          "name": {
            "type": ["string", "null"],
            "description": "The name of the category."
          },
          "score": {
            "type": ["string", "null"],
            "pattern": "^(>=|<=|>|<|=)\\s*\\d+(\\.\\d+)?$",
            "description": "Condition for filtering discussions by category score. Number must be between 0.0 and 1.0 and must be prefixed by equality operator. Specify conditions using '>= X', '<= X', '> X', '< X', or '= X'."
          }
        },
        "additionalProperties": False,
        "anyOf": [
          {"required": ["name"]},
          {"required": ["score"]}
        ]
      },
      "startTime": {
        "type": "string",
        "description": "Start of the timestamp range for filtering, in ISO 8601 format."
      },
      "endTime": {
        "type": "string",
        "description": "End of the timestamp range for filtering, in ISO 8601 format."
      },
      "limit": {
        "type": "integer",
        "description": "Maximum number of results to return. Must be a positive integer. Can be 10 at most. offsetPage must be used to paginate the results.",
        "default": 10
      },
      "offsetPage": {
        "type": "integer",
        "description": "Paging offset to paginate the results. Must be a non-negative integer.",
        "default": 0
      },
      "orderDirection": {
        "type": "string",
        "description": "Order direction for the results.",
        "enum": ["ASC", "DESC"],
        "default": "ASC"
      },
      "sentimentScore": {
        "type": ["string", "null"],
        "pattern": "^(>=|<=|>|<|=)\\s*\\d+(\\.\\d+)?$",
        "description": "Condition for filtering by score. Number must be between 0.0 and 1.0 and must be prefixed by equality operator. Specify conditions using '>= X', '<= X', '> X', '< X', or '= X'."
      }
    },
    "schemas": {
      "assign_category":
        {
          "description": "Assign a category to a discussion.",
          "arguments": {
            "type": "object",
            "properties": {
              "discussion_id": {
                "$ref": "#/definitions/discussionId"
              },
              "category": {
                "$ref": "#/definitions/category"
              }
            },
            "required": ["discussion_id", "category"],
            "additionalProperties": False
          }
        },
      "modify_discussion":
        {
          "description": "Rename and feature a discussion.",
          "arguments": {
            "type": "object",
            "properties": {
              "discussion_id": {
                "$ref": "#/definitions/discussionId"
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
            "required": ["discussion_id"],
            "additionalProperties": False
          }
        },
      "remove_category":
        {
          "description": "Remove a category from a discussion.",
          "arguments": {
            "type": "object",
            "properties": {
              "discussion_id": {
                "$ref": "#/definitions/discussionId"
              },
              "name": {
                "type": "string",
                "description": "The name of the category to remove."
              }
            },
            "required": ["discussion_id", "name"],
            "additionalProperties": False
          }
        },
      "retrieve_dialogue_unit_by_id":
        {
          "description": "Query a conversation prompt-response entries in database table using a specific dialogue unit entry id.",
          "arguments": {
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
        },
      "retrieve_discussion_by_id":
        {
          "description": "Retrieve entries in discussion database table using a specific discussion entry id.",
          "arguments": {
            "type": "object",
            "properties": {
              "discussion_id": {
                "$ref": "#/definitions/discussionId"
              }
            },
            "required": ["discussion_id"],
            "additionalProperties": False
          }
        },
      "find_discussions":
        {
          "description": "Query a discussion database table based on various criteria.",
          "arguments": {
            "type": "object",
            "properties": {
              "title": {
                "type": ["string", "null"],
                "description": "Title for filtering discussions using a LIKE operator."
              },
              "featured": {
                "type": ["boolean", "null"],
                "description": "Featured flag for filtering discussions."
              },
              "starttime_start": {
                "$ref": "#/definitions/startTime"
              },
              "endtime_start": {
                "$ref": "#/definitions/endTime"
              },
              "starttime_end": {
                "$ref": "#/definitions/startTime"
              },
              "endtime_end": {
                "$ref": "#/definitions/endTime"
              },
              "category": {
                "$ref": "#/definitions/categorySearch"
              },
              "cost": {
                "type": ["string", "null"],
                "pattern": "^(>=|<=|>|<|=)\\s*\\d+(\\.\\d+)?$",
                "description": "Condition for filtering by cost. Cost refers to token cost of the LLM API calls. Number must be 0.0 or more and must be prefixed by equality operator. Specify conditions using '>= X', '<= X', '> X', '< X', or '= X'."
              },
              "limit": {
                "$ref": "#/definitions/limit"
              },
              "offset_page": {
                "$ref": "#/definitions/offsetPage"
              },
              "order_by": {
                "type": "string",
                "description": "Order the results by a specific field.",
                "enum": ["title", "starttime", "endtime", "category", "featured", "cost"],
                "default": "starttime"
              },
              "order_direction": {
                "$ref": "#/definitions/orderDirection"
              }
            },
            "additionalProperties": False,
            "anyOf": [
              {"required": ["title"]},
              {"required": ["featured"]},
              {"required": ["starttime_start"]},
              {"required": ["endtime_start"]},
              {"required": ["starttime_end"]},
              {"required": ["endtime_end"]},
              {"required": ["category"]},
              {"required": ["cost"]}
            ]
          }
        },
      "find_dialogue_units":
        {
          "description": "Query a dialogue units database table based on various criteria.",
          "arguments": {
            "type": "object",
            "properties": {
              "discussion_id": {
                "$ref": "#/definitions/discussionId"
              },
              "phrase": {
                "type": ["string", "null"],
                "description": "The query phrase will be compared/matched against dialogue units."
              },
              "topic": {
                "type": ["string", "null"],
                "description": "Filter dialogue units with a specific topic using an exact match."
              },
              "sentiment": {
                "type": "object",
                "description": "Filter dialogue units based on sentiment scores.",
                "properties": {
                  "positive_score": {
                    "$ref": "#/definitions/sentimentScore"
                  },
                  "negative_score": {
                    "$ref": "#/definitions/sentimentScore"
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
                "description": "Filter dialogue units with a specific intent using an exact match."
              },
              "starttime": {
                "$ref": "#/definitions/startTime"
              },
              "endtime": {
                "$ref": "#/definitions/endTime"
              },
              "prompt": {
                "type": ["string", "null"],
                "description": "Filter dialogue units by a specific phrase from the user's prompt."
              },
              "response": {
                "type": ["string", "null"],
                "description": "Filter dialogue units by a specific phrase from a response."
              },
              "limit": {
                "$ref": "#/definitions/limit"
              },
              "offset_page": {
                "$ref": "#/definitions/offsetPage"
              },
              "order_by": {
                "type": "string",
                "description": "Order the results by a specific field.",
                "enum": ["phrase", "timestamp", "topic", "intent", "prompt", "response"],
                "default": "timestamp"
              },
              "order_direction": {
                "$ref": "#/definitions/orderDirection"
              }
            },
            "additionalProperties": False,
            "oneOf": [
              {"anyOf": [
                {"required": ["phrase"]},
                {"required": ["topic"]},
                {"required": ["sentiment"]},
                {"required": ["intent"]},
                {"required": ["starttime"]},
                {"required": ["endtime"]},
                {"required": ["prompt"]},
                {"required": ["response"]}
              ]},
              {"required": ["discussion_id"]}
            ]
          }
        },
      "retrieve_discussion_statistics": 
        {
          # Example prompt added to help Claude Haiku model on selecting correct arguments.
          "description": "Retrieve statistics about discussions (sessions) and dialogues (prompt-response pairs). Aggregation type (one of: count, average, sum, minimum, maximum) and aggregation entity (one of: topic, intent, timestamp, sentiment, category, cost, discussion_id, dialogue_unit_id) are mandatory arguments for aggregation. The 'discussion_id' entity type refers to the overall discussion or session, while the 'dialogue_unit_id' entity type refers to the individual prompt-response pairs, or dialogue units within a discussion. Use 'dialogue_unit_id' when you want to analyze the statistics of the individual dialogue units, and 'discussion_id' when you want to analyze the statistics of the overall discussions. Optionally, you may bin statistics by aggregation grouping argument, which is independent from the aggregation entity argument. Topic, intent, category, starttime, and endtime are optional arguments to filter results. For instance, a prompt 'count all dialogues grouped by discussions' should return aggregation type 'count', entity 'dialogue_unit_id', and grouping 'discussion_id'.",
          "arguments": {
            "aggregation_type": {
              "type": "string",
              "description": "The aggregation type for calculating statistic. Default is count.",
              "enum": ["count", "average", "sum", "minimum", "maximum"],
              "default": "count"
            },
            "aggregation_entity": {
              "type": "string",
              "description": "The aggregation entity field to calculate the statistic on. 'discussion_id' refers to the overall discussion or session, while 'dialogue_unit_id' refers to the individual prompt-response pairs within a discussion. Choose the appropriate entity based on your use case. Cost refers to the token cost of the LLM API calls.",
              "enum": ["topic", "intent", "timestamp", "sentiment", "category", "cost", "discussion_id", "dialogue_unit_id"],
              "default": "dialogue_unit_id"
            },
            "aggregation_grouping": {
              "type": ["string", "null"],
              "description": "Optional aggregation grouping field to bin the aggregated data. Use only if it is different from the selected aggregation entity.",
              "enum": ["topic", "intent", "timestamp", "sentiment", "category", "cost", "discussion_id", "dialogue_unit_id"]
            },
            # FILTERS
            # Only a single topic name is supported
            "topic": {
              "type": ["string", "null"],
              "description": "Filter entries with a specific topic name using a lowercase exact match."
            },
            # Only a single category name suported, category by score is not supported
            "category": {
              "type": ["string", "null"],
              "description": "Filter entries with a specific category name using a lowercase exact match."
            },
            # NOTE: Sentiment filter and cost filters are not supported
            "intent": {
              "type": ["string", "null"],
              "description": "Filter entries with a specific intent name using a lowercase exact match."
            },
            "starttime": {
              "type": ["string", "null"],
              "description": "The start of the timestamp range for filtering entries, in ISO 8601 format."
            },
            "endtime": {
              "type": ["string", "null"],
              "description": "The end of the timestamp range for filtering entries, in ISO 8601 format."
            }
          },
          "additionalProperties": False,
          "required": ["aggregation_type", "aggregation_entity"]
        }
    }
  }
}


# If tools are used, append epilogue to provide extra information how to use tools
system_message_metadata_tools_epilogue = """
Tools can be multiple and chained for a more complex data retrieval. In chained tools, arguments may rely on the previous tool results. In that case, skip arguments until the previous tool results are retrieved.

Do not define function calling tools to the response, if only partial information is provided in the context window. Rather, ask user for more information and confirmation, if the intent to use a tool is not clear, or details are missing.

Use the tool_name only if the direct intent of the user is apparent from the context. If the same information is asked consequently, and information has already been retrieved to the current context window, do not use the function calling tool again, but rather use the information provided in the already existing context window.
"""


system_message_metadata = f"""
Deduce topics, sentiment, and intent of the user's input as well as function calling tools, if relevant.

Response format:
<<response_schema>>
Always provide the whole schema in the given format.
<<tools>><<tools_epilogue>>
Respond with a JSON string only. Property names must be enclosed in double quotes. Do not generate intros, outros, explanations, etc.

*****

Date and time is now: <<datetime>>
"""


# Append to system_message_metadata_schema, if any of the tools are used
system_message_metadata_schema_tools_part = """,
    "system_requires_more_information_to_use_tools": <<bool>>,
    "skip_tools_due_to_unsatisfied_preconditions_found_from_previous_tool_results_and_user_specifications": <<bool>>,
    "tools": [
      {
        "tool": "<<tool_name>>",
        "arguments": {<<arguments>>},
        "details_are_missing": <<bool>>,
        "arguments_relies_on_previous_tool_results": <<bool>>
      },
    ]"""


# Metadata schema to retrieve basic conversation details for saving dialogue units
# and activating function calling tools when necessary
system_message_metadata_schema = """
{
    "topics": ["<<Topic>>",],
    "sentiment": {
        "positive_score": <<positive_score_from_0.0_to_1.0>>,
        "negative_score": <<negative_score_from_0.0_to_1.0>>
    },
    "intent": "<<intent>>"<<tools_part>>
}
"""


def render_selected_schemas(tool_args):
    """Render selected schemas based on tool arguments"""
    global tool_schemas
    result, human_format = "", ""
    for group, content in collect_schemas(tool_args, tool_schemas).items():
        # Print the header
        result += "\n" + content['header'] + "\n"
        human_format += "\n" + content['header'] + "\n"
        # Convert the schemas dictionary for this group to a JSON string and print it
        if "definitions" in content:
            data = {
              "definitions": content["definitions"],
              "schemas": content['schemas']
            }
        else:
            data = content['schemas']
        for tool, schema in content['schemas'].items():
            human_format += f"\n- {tool}: " + schema['description'] + "\n"
        result += "\n" + json.dumps(data) + "\n"
    # Return both machine targeted json string and human readable text
    return result, human_format


def collect_schemas(tool_args, tool_schemas):
    """Collect schemas specified in tool_args from tool_schemas"""
    
    selected_schemas = {}
    definitions = []
    
    def find_definition_references(schema):
        # Iterate dictionary recursively if type is object and find out all keys that are "$ref"
        # then split the value #/definitions/orderDirection by slashed and field add to definitions list
        if isinstance(schema, dict):
            # Check for a direct $ref and add its target to the definitions list if it's new
            if '$ref' in schema:
                ref = schema['$ref'].split('/')[-1]
                if ref not in definitions:
                    definitions.append(ref)
            
            # Recursively search in each dictionary entry
            for key, value in schema.items():
                find_definition_references(value)
        elif isinstance(schema, list):
            # Recursively search each item in the list
            for item in schema:
                find_definition_references(item)
    
    # Add all specified schemas or entire groups first
    for arg in tool_args:
        if "~" not in arg:
            parts = arg.split(".")
            if len(parts) == 1:  # Include entire group
                group = parts[0]
                if group in tool_schemas:
                    selected_schemas[group] = {
                        "header": tool_schemas[group]["header"],
                        "schemas": tool_schemas[group]["schemas"].copy()
                    }
                    if "definitions" in tool_schemas[group] and not "definitions" in selected_schemas[group]:
                        selected_schemas[group]["definitions"] = tool_schemas[group]["definitions"].copy()
                else:
                    print(f"Provided tool group '{group}' not found, skipping...")
            elif len(parts) == 2:  # Include specific schema
                main_group, sub_group = parts
                if main_group not in tool_schemas:
                    print(f"Provided tool group '{main_group}' not found, skipping...")
                    continue
                if not sub_group in tool_schemas[main_group]["schemas"]:
                    print(f"Provided tool '{sub_group}' not defined, skipping...")
                    continue
                if main_group in tool_schemas and sub_group in tool_schemas[main_group]["schemas"]:
                    if main_group not in selected_schemas:
                        selected_schemas[main_group] = {
                            "header": tool_schemas[main_group]["header"],
                            "schemas": {}
                        }
                    selected_schemas[main_group]["schemas"][sub_group] = tool_schemas[main_group]["schemas"][sub_group]
                if "definitions" in tool_schemas[main_group] and not "definitions" in selected_schemas[main_group]:
                    selected_schemas[main_group]["definitions"] = tool_schemas[main_group]["definitions"]
    
    # Then process exclusions
    for arg in tool_args:
        if "~" in arg:
            parts = arg.split("~")
            main_group, sub_group = parts[1].split(".")
            if main_group in selected_schemas and sub_group in selected_schemas[main_group]["schemas"]:
                del selected_schemas[main_group]["schemas"][sub_group]
    
    # Find definiition references for all schemas
    for main_group, schema in selected_schemas.items():
        for tool, schema in schema["schemas"].items():
            find_definition_references(schema["arguments"])
    
    # Remove unused definitions
    for tool, schema in selected_schemas.copy().items():
        if "definitions" in schema:
            for field, definition in schema["definitions"].copy().items():
                if field not in definitions:
                    del selected_schemas[tool]["definitions"][field]
      
    # Return filtered schemas
    return selected_schemas
