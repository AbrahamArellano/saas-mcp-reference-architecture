import boto3
import traceback
import asyncio
import json
from mcp_client_stream import McpClient

bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-east-1'
)

system_prompt = [
    {
        "text": "You are a retail assistant that can help customers find products and place orders. "
                "You have access to two MCP tools: \n"
                "1. product-server: Use this to get product information from the retail catalog\n"
                "2. order-server: Use this to place and manage orders for products\n\n"
                "When asked about products, ALWAYS use the product-server tool.\n"
                "When asked to place orders, ALWAYS use the order-server tool.\n"
                "Show your work by explaining what tools you're using and why."
    }
]

messages_for_model = []
initial_prompt = {
    "role": "user",
    "content": [
        {
            "text": "Could I book my flight from Munich to NewJork on 26.05?"
        }
    ]
}
messages_for_model.append(
    initial_prompt
)

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

async def run_model_with_mcp():
    client = None
    try:
        client = McpClient(
            url="http://infras-mcpse-3tf1shydmuay-2131978296.us-east-1.elb.amazonaws.com/mcp",
            auth_token="xxx"
        )

        print("\nStep 1 ********************")
        print("\nInitializing MCP client...")
        await client.init()

        print("\nStep 2 ********************")
        print("Getting tools...")
        tools = await client.get_tools()
        print("\nAvailable tools:")
        print(tools)

        tools_spec = transform_tools_to_bedrock_format(tools)
        print(tools_spec)

        print("\nStep 3 ********************")
        print("\nFirst call of Bedrock model using converse...")
        response = bedrock_runtime.converse(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            messages=messages_for_model,
            system=system_prompt,
            inferenceConfig={
                "maxTokens": 4096,
                "temperature": 0.7
            },
            toolConfig=tools_spec
        )

        print("\nModel response:")
        print(json.dumps(response, indent=2))

        parsed_response = parse_model_response(response)
        print("\nParsed Response:")
        print(f"Stop Reason: {parsed_response['stopReason']}")
        print(f"Tool use Id: {parsed_response['toolUseId']}")
        print(f"Tool Name: {parsed_response['toolName']}")
        print(f"Tool Input: {parsed_response['toolInput']}")


        if parsed_response['stopReason'] == 'tool_use':
            print("\nStep 4 ********************")
            print("\nCalling MCP tools")
            mcpResponse = await client.call_tool(parsed_response['toolName'], parsed_response['toolInput'])
            print("\nMCP response:" + mcpResponse)

            try:
                mcp_json = json.loads(mcpResponse)
                mcp_json = mcp_json[0]

            except json.JSONDecodeError as e:
                print(f"\nError deserializing JSON: {e}")
                print("Raw response type:", type(mcpResponse))
                print("Raw response:", mcpResponse)
                # If deserialization fails, use the raw response as a fallback
                mcp_json = {"error": "Failed to parse JSON", "raw_response": mcpResponse}

            tool_result = {
                "toolUseId": parsed_response['toolUseId'],
                "content": [{"json": mcp_json}]
            }

            # Create a tool result message following AWS documentation pattern
            tool_result_message = {
                "role": "user",
                "content": [
                    {
                        "toolResult": tool_result
                    }
                ]
            }
            messages_for_model.append(tool_result_message)

        messages = [
            initial_prompt,
            {
                "role": "assistant",
                "content": response["output"]["message"]["content"]
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": parsed_response['toolUseId'],
                            "content": [
                                {
                                    "json": mcp_json
                                }
                            ]
                        }
                    }
                ]
            }
        ]
        print("\nBuilt messages:" + json.dumps(messages, indent=2))
        print("\nStep 5 ********************")
        print("\nSecond model call with MCP tools")
        response = bedrock_runtime.converse(
                modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                messages=messages,
                system=system_prompt,
                inferenceConfig={
                "maxTokens": 4096,
                "temperature": 0.7
                },
            toolConfig=tools_spec
            )
        print("Final response: " + json.dumps(response, indent=2))


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
