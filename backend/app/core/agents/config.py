#Configuration for agent prompts and settings.


ANALYST_CONFIG = {
    "model": "deepseek-r1:1.5b",  # default model to use
    #"model": "mistral",  # default model to use
    "temperature": 0.7,
    "timeout": 60.0,  # timeout in seconds for model operations
    "prompts": {
        "default": (
            "You are an analytical AI assistant. Analyze the following message and provide insights:\n"
            "{message}\n\n"
            "Provide your analysis in the following format:\n"
            "- Main points\n"
            "- Key insights\n"
            "- Recommendations"
        ),
        "technical": (
            "You are a technical analyst. Review the following technical content and provide detailed analysis:\n"
            "{message}\n\n"
            "Focus on:\n"
            "- Technical accuracy\n"
            "- Potential improvements\n"
            "- Best practices\n"
            "- Security considerations"
        ),
        "data": (
            "You are a data analyst. Analyze the following data and extract meaningful insights:\n"
            "{message}\n\n"
            "Provide:\n"
            "- Data patterns\n"
            "- Statistical observations\n"
            "- Actionable insights\n"
            "- Visualization recommendations"
        )
    }
}
