import datetime

import psycopg2
from typing import TypedDict, Annotated, List, Optional
from pandas import DataFrame
import json
from get_conn import get_connection_uri
from azure.identity import AzureCliCredential
import dotenv
dotenv.load_dotenv()

from agent_framework.azure import AzureOpenAIChatClient
from typing import Annotated
from pydantic import Field
from agent_framework import tool

import psycopg2
from typing import Optional
from pandas import DataFrame
from get_conn import get_connection_uri

class PG_LimitedPlugin:

    def __init__(self, db_uri: str):
        self.db_uri = db_uri
        conn = psycopg2.connect(db_uri)
        conn.close()
        print("Connected to company's database successfully.")
    def _get_connection(self):
        """Create a new connection for each operation."""
        return psycopg2.connect(self.db_uri)
    async def get_product_info(self, product_name: Optional[str] = None, product_id: Optional[int] = None) -> list[dict]:
        """Gets all product information from the database given the name or ID of the product."""
        query = """SELECT 
                    product_id,                   
                    name,
                    inventory,
                    price,
                    refurbished,
                    category
                FROM products
                WHERE (LOWER(name) = LOWER(%(product_name)s) AND %(product_name)s IS NOT NULL)
                   OR (product_id = %(product_id)s AND %(product_id)s IS NOT NULL)
                   """
        conn = self._get_connection()
        cursor = conn.cursor()
        if not product_name and not product_id:
            print("No product name or ID provided.")
            return None
        elif product_id:
            cursor.execute(query, {"product_name": None, "product_id": product_id})
        else:
            cursor.execute(query, {"product_name": product_name, "product_id": None})

            
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        cursor.close()
        conn.close()
        try:
            products= DataFrame(rows, columns=columns)
            products.to_dict(orient="records")  # <-- JSON serializabl
            
            return products.to_dict(orient="records")  # <-- JSON serializabl
        except Exception as e:
            print(f"Error fetching product information: {e}")
            return None


class PG_Plugin:

    def __init__(self, db_uri: str):
        self.db_uri = db_uri  # Store URI instead of connection
        # Test connection
        conn = psycopg2.connect(db_uri)
        conn.close()
        print("Connected to company's database successfully.")

    def _get_connection(self):
        """Create a new connection for each operation."""
        return psycopg2.connect(self.db_uri)

    async def execute_query(self, query: str) -> list:
        conn = self._get_connection()
        try:
            query_cursor = conn.cursor()
            query_cursor.execute(query)
            if query.strip().upper().startswith("SELECT"):
                result = query_cursor.fetchall()
            else:
                result = ["Only read-only SELECT queries are allowed."]
                conn.commit()     
        except psycopg2.Error as e:
            conn.rollback()
            result = [str(e)]
        finally:
            query_cursor.close()
            conn.close()
        return result

    async def get_schema_info(self) -> str:
        print("Getting schema")
        conn = self._get_connection()
        try:
            query = """
            SELECT
                cols.table_schema,
                cols.table_name,
                cols.column_name,
                cols.data_type,
                cols.is_nullable,
                cons.constraint_type,
                cons.constraint_name,
                fk.references_table AS referenced_table,
                fk.references_column AS referenced_column
            FROM information_schema.columns cols
            LEFT JOIN information_schema.key_column_usage kcu
                ON cols.table_schema = kcu.table_schema
                AND cols.table_name = kcu.table_name
                AND cols.column_name = kcu.column_name
            LEFT JOIN information_schema.table_constraints cons
                ON kcu.table_schema = cons.table_schema
                AND kcu.table_name = cons.table_name
                AND kcu.constraint_name = cons.constraint_name
            LEFT JOIN (
                SELECT
                    rc.constraint_name,
                    kcu.table_name AS references_table,
                    kcu.column_name AS references_column
                FROM information_schema.referential_constraints rc
                JOIN information_schema.key_column_usage kcu
                    ON rc.unique_constraint_name = kcu.constraint_name
            ) fk
                ON cons.constraint_name = fk.constraint_name
            WHERE cols.table_schema = 'public'
            ORDER BY cols.table_schema, cols.table_name, cols.ordinal_position;
            """
            schema_cur = conn.cursor()
            schema_cur.execute(query)
            columns = [desc[0] for desc in schema_cur.description]
            rows = schema_cur.fetchall()
            schema_cur.close()
            schema_info = [dict(zip(columns, row)) for row in rows]
            return json.dumps(schema_info, indent=2)
        finally:
            conn.close()

def init_agents():
    conn_uri = get_connection_uri()
    plugin = PG_Plugin(conn_uri)

    chat_client=AzureOpenAIChatClient(credential=AzureCliCredential())
    support_agent = AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions=(
                "You are a support agent. Analyze the user's request and route to the appropriate specialist:\n"
                "- For getting databsase schema: call handoff_to_schema_agent\n"
                "- For querying database: call handoff_to_service_agent"
                "- If not able to help, let the user know of the reason."
            ),
        name = "support_agent"
    )
    schema_agent = AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions="You are responsible for providing database schema information.",
        tools=[plugin.get_schema_info],
        name = "schema_agent"
    )
    service_agent = AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions="You are a read-only agent for company's product database. Use the schema information provided by the schema agent to answer user questions about the database. You can not add any new data to the database.",
        tools=[plugin.execute_query],
        name="service_agent"
    )
    return support_agent, schema_agent, service_agent

from agent_framework.orchestrations import SequentialBuilder
from agent_framework import Message
from typing import cast

async def run_agent(question):
    conn_uri = get_connection_uri()
    plugin = PG_LimitedPlugin(conn_uri)
 
    agent = AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions="You are a read-only agent for company's product database.",
        tools = [plugin.get_product_info],
        name="product_info_agent")
    try:
        result = await agent.run(question)
        stream_dict = {"event_time":datetime.datetime.now().isoformat(),
                        "user_msg": question,
                       "status": "Healthy",
                        "response": result.text,
                        "total_tokens": result.to_dict()['usage_details']['total_token_count']}
        return result, stream_dict
    except Exception as e:
        print(f"Error running agent: {e}")
        return e, {"event_time": datetime.datetime.now().isoformat(),
                    "user_msg": question,
                    "status": "Error",
                    "response": str(e),
                    "total_tokens": 0}


async def run_seq_agent_framework(question) -> None:

    support_agent, schema_agent, service_agent = init_agents()
    seq_workflow = SequentialBuilder(participants=[schema_agent, service_agent]).build()
    print("[Agent Framework] Group chat conversation:")
    outputs: list[list[Message]] = []
    async for event in seq_workflow.run(question, stream=True):
        print("**********:", event, event.type)
        if event.type == "output" or event.type == "executor_invoked":
            outputs.append(cast(list[Message], event.data))
            print(event.type, "********** Event Data:", event.data)

    if outputs:
        print("===== Final Conversation =====")
        for i, msg in enumerate(outputs[-1], start=1):
            name = msg.author_name or ("assistant" if msg.role == "assistant" else "user")
            print(f"{'-' * 60}\n{i:02d} [{name}]\n{msg.text}")
    return outputs

