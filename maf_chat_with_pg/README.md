
## Q: What does this exercise teach me?
### A: How to use the latest (as of Jan 2026) Microsoft Agent Framework to chat with an Azure PostgreSQL database in natural language. It contains examples of single agent and multi-agent solutions.

### Requirements

- An Azure PostgreSQL database (you can populate it with tables and data of your choice.)
- An Azure OpenAI model (you can use other llms as well, in that case you need to modify your .env file and figure out the right params to connect to it.)
- Python (3.11.9 or higher)

### Set up your Python environment: 

In the current folder, run below in a terminal window (for Windows):

```
python3 -m venv venv
.\venv\Scripts\activate # this activates the environment you just created. 
pip install -r requirements.txt # installs required packages
```

### Populate your environment variables
- Make a copy of the .env.sample file, and rename it to .env
- Populate the required variables for connecting to your llm endpoint and Azure postgreSQL database.

### Run the notebook.

1. Open the notebook
2. Ensure the kernel (upper right hand side) is pointing at the environment you just set up
3. In a terminal window, run **az login** 
4. Start running your notebook cells in order.

