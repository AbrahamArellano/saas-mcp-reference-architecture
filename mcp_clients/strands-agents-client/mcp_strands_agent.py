from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.tools.mcp import MCPClient
import traceback
import os
import json
from datetime import datetime

MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"
os.environ['AWS_REGION'] = 'us-east-1'

MCP_SERVER_URL = "http://infras-mcpse-3tf1shydmuay-2131978296.us-east-1.elb.amazonaws.com/mcp"
AUTH_TOKEN = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJ1c2VyMSIsIm5hbWUiOiJUZXN0IFVzZXIxIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwicm9sZXMiOlsidXNlciIsImFkbWluIl0sInBlcm1pc3Npb25zIjpbInJlYWQiXSwib3JnIjoidGVuYW50MSIsImN1c3RvbTp0ZW5hbnRJZCI6IkFCQzEyMyIsImlhdCI6MTc0NzEzMTcwMSwiZXhwIjoxNzQ3MTM1MzAxfQ."

system_prompt = """You are a travel assistant that helps customers find flights and book tickets.
                You can perform two main tasks:
                Search for flights — retrieve information such as routes, prices, schedules, and availability.
                Book and manage flights — handle reservations, confirm bookings, and manage customer itineraries"""

# This application uses Strand SDK to connect to the MCP Server and Bedrock to provide flight information based on
# the given prompt. The prompt is passed to the Bedrock model and the response is returned to the user.

def create_streamable_http_transport():
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}"
    }
    return streamablehttp_client(
        url=MCP_SERVER_URL,
        headers=headers)

def print_help():
    """Print available commands"""
    print("\nAvailable commands:")
    print("  /help - Show this help message")
    print("  /clear - Clear the conversation history")
    print("  /quit, /bye, /exit - End the conversation")

def main():
    print("\nInitializing MCP client...")
    try:
        mcp_client = MCPClient(create_streamable_http_transport)
        
        print("Getting tools list...")
        with mcp_client:
            tools = mcp_client.list_tools_sync()

            print("\nAvailable tools:")
            for tool in tools:
                print(f"- Name: {tool.tool_name}; Type: {tool.tool_type}")
            
            # Create a single agent instance to maintain conversation context
            booking_agent = Agent(
                model=MODEL_ID,
                system_prompt=system_prompt,
                tools=tools
            )
            
            print("\nTravel assistant initialized. You can now start your conversation.")
            print("Type /help to see available commands.")
            
            while True:
                try:
                    booking_prompt = input("\nEnter travel booking query in natural language. /help: ")
                    
                    # Handle special commands
                    if booking_prompt.lower() in ["/bye", "/quit", "/exit", "bye", "quit", "exit"]:
                        print("\nEnding current chat session. Now Go Build...")
                        break
                    elif booking_prompt.lower() == "/help":
                        print_help()
                        continue
                    elif booking_prompt.lower() == "/clear":
                        # Create a new agent instance to clear conversation history
                        booking_agent = Agent(
                            model=MODEL_ID,
                            system_prompt=system_prompt,
                            tools=tools
                        )
                        print("\nConversation history cleared.")
                        continue
                    
                    # Use the same agent instance for all interactions to maintain context
                    print(f"\nBooking prompt: {booking_prompt}")
                    print("\nResponse:")
                    
                  
                    response = booking_agent(booking_prompt)
                    if hasattr(response, 'message') and response.message:
                        content = response.message.get("content", [{}])
                        if content and isinstance(content, list) and len(content) > 0:
                            text = content[0].get("text", "No response")
                            print(text)
                        else:
                            print("No content in response")
                    else:
                        print("No message in response")
                    
                    print("\n")  # Add a newline after the response

                except KeyboardInterrupt:
                    print("\nChat session terminated by user.")
                    break
                except Exception as error:
                    print(f"\nError during chat session: {error}")
                    traceback.print_exc()
    
    except Exception as e:
        print("\nException Details:")
        print(f"Type: {type(e)}")
        print(f"Message: {str(e)}")
        print("\nTraceback:")
        traceback.print_exc()

if __name__ == "__main__":
    main()
