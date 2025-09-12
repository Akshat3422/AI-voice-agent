import os
from groq import Groq
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from dotenv import load_dotenv
from helpers.Prompt import build_system_prompt

load_dotenv()

chat = ChatPromptTemplate(
    messages=[
        SystemMessagePromptTemplate.from_template("{system}"),
        HumanMessagePromptTemplate.from_template("{input}")
    ]
)

llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0.7)


def generate_response(system_prompt: str, user_input: str) -> str:
    try:
        messages = chat.format_messages(system=system_prompt, input=user_input)
        response = llm.invoke(messages)
        return response.content  
    except Exception as e:
        print("Error during response generation:", e)
        return "I'm sorry, I couldn't process that. Could you please repeat?"