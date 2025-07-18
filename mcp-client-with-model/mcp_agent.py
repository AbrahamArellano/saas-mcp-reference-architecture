import boto3
import traceback
import asyncio
import json
from mcp_client_http_stream import McpClient

MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"
MAX_TOKENS = 4096
TEMPERATURE = 0.7

MCP_SERVER_URL = "http://infras-mcpse-3tf1shydmuay-2131978296.us-east-1.elb.amazonaws.com/mcp"
AUTH_TOKEN = "xxx"

bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-east-1'
)

system_prompt = [
    {
        "text": "You are a travel assistant that helps customers find flights and book tickets."
                "You can perform two main tasks:\n"
                "Search for flights — retrieve information such as routes, prices, schedules, and availability.\n"
                "Book and manage flights — handle reservations, confirm bookings, and manage customer itineraries\n"
    }
]

initial_prompt = {
    "role": "user",
    "content": [
        {
            "text": "Could I book my flight from Munich to NewJork on 26.10?"
        }
    ]
}

async def run_model_with_mcp():
    client = None
    try:
        client = McpClient(
            url=MCP_SERVER_URL,
            auth_token=AUTH_TOKEN
        )

        print("\nStep 1 ********************")
        print("\nInitializing MCP client...")
        await client.init()

        print("\nStep 2 ********************")
        print("Getting tools list...")
        tools = await client.get_tools()
        print("\nAvailable tools:")
        print(tools)

        print("\nStep 3 ********************")
        tools_spec = transform_tools_to_bedrock_format(tools)
        print("\nConverted tools list to Bedrock API toolSpec:")
        print(tools_spec)

        print("\nFirst call of Bedrock model with toolSpec using converse...")
        messages_model_first_call = [initial_prompt]

        first_model_response = bedrock_runtime.converse(
            modelId=MODEL_ID,
            messages=messages_model_first_call,
            system=system_prompt,
            inferenceConfig={
                "maxTokens": MAX_TOKENS,
                "temperature": TEMPERATURE
            },
            toolConfig=tools_spec
        )

        print("\nModel raw first_model_response:")
        print(json.dumps(first_model_response, indent=2))

        parsed_response = parse_model_response(first_model_response)
        print("\nModel parsed Response:")
        print(f"Stop Reason: {parsed_response['stopReason']}")
        print(f"Tool use Id: {parsed_response['toolUseId']}")
        print(f"Tool Name: {parsed_response['toolName']}")
        print(f"Tool Input: {parsed_response['toolInput']}")

        if parsed_response['stopReason'] == 'tool_use':
            print("\nStep 4 ********************")
            print("\nCalling MCP tools with parameters from model...")
            mcp_response = await client.call_tool(parsed_response['toolName'], parsed_response['toolInput'])
            print("\nMCP server first_model_response:" + mcp_response)

            try:
                mcp_json = json.loads(mcp_response)
                mcp_json = mcp_json[0]

            except json.JSONDecodeError as e:
                print(f"\nError deserializing JSON: {e}")
                print("Raw first_model_response type:", type(mcp_response))
                print("Raw first_model_response:", mcp_response)
                # If deserialization fails, use the raw first_model_response as a fallback
                mcp_json = {"error": "Failed to parse JSON", "raw_response": mcp_response}

            print("\nStep 5 ********************")
            tool_result = {
                "toolUseId": parsed_response['toolUseId'],
                "content": [{"json": mcp_json}]
            }

            # Compose a model message with tools assist and tools results
            messages_model_final_call = await compose_tools_result_message(first_model_response, tool_result)

            print("\nComposed messages with user prompt, tools assistant and tools result:\n" + json.dumps(messages_model_final_call, indent=2))

            print("\nSecond model call with MCP tools")
            first_model_response = bedrock_runtime.converse(
                modelId=MODEL_ID,
                messages=messages_model_final_call,
                system=system_prompt,
                inferenceConfig={
                    "maxTokens": MAX_TOKENS,
                    "temperature": TEMPERATURE
                },
                toolConfig=tools_spec
            )
            print("Final first_model_response: " + json.dumps(first_model_response, indent=2))
        else:
            print("\nNo tool use detected. Exiting...")

    except Exception as e:
        print("\nException Details:")
        print(f"Type: {type(e)}")
        print(f"Message: {str(e)}")
        print("\nTraceback:")
        traceback.print_exc()
    finally:
        if client:
            try:
                await client.cleanup()
                print("\nClient cleanup completed")
            except Exception as cleanup_error:
                print(f"\nError during cleanup: {cleanup_error}")


def transform_tools_to_bedrock_format(tools_list):
    tool_config = {
        "tools": []
    }

    for tool in tools_list:
        tool_spec = {
            "toolSpec": {
                "name": tool.name,
                "description": tool.description or f"Tool for {tool.name}",
                "inputSchema": {
                    "json": tool.inputSchema
                }
            }
        }
        tool_config["tools"].append(tool_spec)

    return tool_config


def parse_model_response(response):
    tool_content = next(
        (item for item in response['output']['message']['content']
         if 'toolUse' in item),
        None
    )

    return {
        'stopReason': response['stopReason'],
        'toolUseId': tool_content['toolUse']['toolUseId'] if tool_content else None,
        'toolName': tool_content['toolUse']['name'] if tool_content else None,
        'toolInput': tool_content['toolUse']['input'] if tool_content else None
    }


async def compose_tools_result_message(first_model_response, tool_result):
    tool_assistant_message = first_model_response['output']['message']
    tool_result_message = {
        "role": "user",
        "content": [
            {
                "toolResult": tool_result
            }
        ]
    }
    return [initial_prompt, tool_assistant_message, tool_result_message]


def main():
    try:
        asyncio.run(run_model_with_mcp())
    except KeyboardInterrupt:
        print("\nOperation interrupted by user")
    except Exception as e:
        print(f"\nError in main: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
