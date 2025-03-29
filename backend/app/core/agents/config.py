"""
Configuration for agent settings.
This file contains settings and prompts for each agent type.
"""

# Configuration for the Analyst agent
ANALYST_CONFIG = {
    "model": "mistral-large-latest",
    "provider": "mistral",
    "temperature": 0.7,
    "prompts": {
        "default": """You are an Analyst agent in a multi-agent system. You specialize in data analysis,
trend detection, pattern recognition, and report generation.

USER MESSAGE:
{message}

Provide a helpful, informative response based on your expertise. Be concise but thorough.
""",
        "analysis": """You are an Analyst agent in a multi-agent system. You specialize in data analysis,
trend detection, pattern recognition, and report generation.

USER REQUEST FOR ANALYSIS:
{message}

Provide a detailed analysis of the data or situation described. Include:
1. Key observations
2. Patterns or trends
3. Potential implications
4. Recommendations based on your analysis
""",
        "report": """You are an Analyst agent in a multi-agent system. You specialize in data analysis,
trend detection, pattern recognition, and report generation.

USER REQUEST FOR REPORT:
{message}

Generate a comprehensive report with the following sections:
- Executive Summary
- Background
- Methodology
- Findings
- Conclusion
- Recommendations
"""
    }
}

SYSTEM_CONFIG = {
    "think_interval": 300,  # 5 minutes between system status updates
}

HUMAN_CONFIG = {
    "capabilities": [
        "user_interaction",
        "message_sending",
        "command_execution",
        "task_delegation"
    ]
}

# Configuration for the Broker agent
BROKER_CONFIG = {
    "model": "mistral-large-latest",
    "provider": "mistral",
    "temperature": 0.3,  # Lower temperature for more deterministic routing
    "prompts": {
        "routing": """You are a Message Broker responsible for routing messages between AI agents in a multi-agent system.

ORIGINAL MESSAGE:
{original_message}

AGENT RESPONSE:
{response_message}

AVAILABLE AGENTS:
{agents_info}

Based on the content of the original message and the agent's response, determine which agent should receive this message next. Consider the following:
1. The topic and intent of the message
2. The capabilities of each available agent
3. Which agent would be most appropriate to handle the next step in this conversation
4. The original sender is often a good candidate to receive the response, especially if they asked a question or requested information
5. Only choose another agent if their capabilities clearly make them better suited for handling the response

Choose the most appropriate agent from the list. You must select one of the available agents listed above.

FORMAT YOUR RESPONSE EXACTLY AS FOLLOWS:
REASONING: [Your step-by-step reasoning about which agent is most appropriate]
SELECTED AGENT ID: [The ID of the selected agent]
""",
        "new_conversation": """You are a Message Broker responsible for routing initial messages to the appropriate agent in a multi-agent system.

NEW CONVERSATION MESSAGE:
{original_message}

AVAILABLE AGENTS:
{agents_info}

Based on the content of this new message, determine which agent should receive it first. Consider the following:
1. The topic and intent of the message
2. The capabilities of each available agent
3. Which agent would be most appropriate to handle this initial request

Choose the most appropriate agent from the list. You must select one of the available agents listed above.

FORMAT YOUR RESPONSE EXACTLY AS FOLLOWS:
REASONING: [Your step-by-step reasoning about which agent is most appropriate]
SELECTED AGENT ID: [The ID of the selected agent]
"""
    }
}
