"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""
import os
import re
import json
import time
import html
import logging
import requests
import streamlit as st
import base64
import uuid
from io import BytesIO
from streamlit_local_storage import LocalStorage
import copy
import subprocess
from dotenv import load_dotenv
from urllib.parse import urlencode, parse_qs, urlparse
import boto3

load_dotenv() # load env vars from .env
API_KEY = os.environ.get("API_KEY")

logging.basicConfig(level=logging.INFO)
mcp_base_url = os.environ.get('MCP_BASE_URL')
mcp_command_list = ["uvx", "npx", "node", "python","docker","uv"]
COOKIE_NAME = "mcp_chat_user_id"
local_storage = LocalStorage()

# Get commit ID if available
try:
    commit_id = os.environ.get('COMMIT_ID', None)
    if not commit_id:
        # Try to get it from git if running locally
        try:
            result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE,
                                  text=True,
                                  timeout=1)
            if result.returncode == 0:
                commit_id = result.stdout.strip()
            else:
                commit_id = 'unknown'
        except Exception:
            commit_id = 'unknown'
except Exception:
    commit_id = 'unknown'

# NEW FUNCTION: Get Cognito client secret from Secrets Manager
def get_cognito_client_secret():
    """Get Cognito client secret from AWS Secrets Manager"""
    try:
        secret_name = os.environ.get('COGNITO_SECRET_NAME')
        if not secret_name:
            return None
            
        session = boto3.Session()
        client = session.client(
            service_name='secretsmanager',
            region_name=os.environ.get('AWS_REGION', 'us-east-1')
        )
        
        response = client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response['SecretString'])
        return secret.get('client_secret')
    except Exception as e:
        logging.error(f"Failed to get Cognito client secret: {e}")
        return None

# NEW FUNCTION: Exchange authorization code for tokens
def exchange_authorization_code_for_tokens(auth_code, redirect_uri):
    """Exchange authorization code for access and ID tokens"""
    try:
        # Get Cognito configuration from environment
        cognito_domain = os.environ.get('COGNITO_DOMAIN')
        client_id = os.environ.get('COGNITO_APP_CLIENT_ID')
        client_secret = get_cognito_client_secret()
        
        if not all([cognito_domain, client_id, client_secret, auth_code]):
            logging.error("Missing Cognito configuration for token exchange")
            return None
        
        # Prepare token exchange request
        token_url = f"https://{cognito_domain}/oauth2/token"
        
        # Prepare authentication header
        auth_string = f"{client_id}:{client_secret}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        headers = {
            'Authorization': f'Basic {auth_b64}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'authorization_code',
            'client_id': client_id,
            'code': auth_code,
            'redirect_uri': redirect_uri
        }
        
        # Make token exchange request
        response = requests.post(token_url, headers=headers, data=data, timeout=10)
        
        if response.status_code == 200:
            token_data = response.json()
            logging.info("Successfully exchanged authorization code for tokens")
            return {
                'access_token': token_data.get('access_token'),
                'id_token': token_data.get('id_token'),
                'refresh_token': token_data.get('refresh_token'),
                'expires_in': token_data.get('expires_in')
            }
        else:
            logging.error(f"Token exchange failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logging.error(f"Error exchanging authorization code: {e}")
        return None

# NEW FUNCTION: Handle authorization code flow
def get_cognito_token_from_url_with_auth_code():
    """Extract and handle Cognito tokens or authorization code from URL"""
    query_params = st.query_params
    
    # Check for authorization code (authorization code flow)
    if 'code' in query_params:
        auth_code = query_params['code']
        redirect_uri = os.environ.get('COGNITO_REDIRECT_URI', st.session_state.get('current_url', ''))
        
        logging.info(f"Found authorization code, exchanging for tokens")
        
        # Exchange code for tokens
        tokens = exchange_authorization_code_for_tokens(auth_code, redirect_uri)
        
        if tokens and tokens.get('id_token'):
            # Store tokens in session state
            st.session_state.cognito_tokens = tokens
            
            # Clean up URL by removing the code parameter
            clean_url = remove_query_params_from_url(['code', 'state'])
            if clean_url != dict(st.query_params):
                st.query_params.clear()
                for key, value in clean_url.items():
                    st.query_params[key] = value
                st.rerun()
            
            return tokens['id_token']
    
    # Check for direct ID token (fallback for implicit flow)
    elif 'id_token' in query_params:
        logging.info("Found ID token in URL parameters")
        return query_params['id_token']
    
    # Check for tokens in session state
    elif 'cognito_tokens' in st.session_state:
        tokens = st.session_state.cognito_tokens
        if tokens and tokens.get('id_token'):
            return tokens['id_token']
    
    return None

# NEW FUNCTION: Remove query parameters from URL
def remove_query_params_from_url(params_to_remove):
    """Remove specific query parameters from current URL"""
    try:
        current_params = dict(st.query_params)
        for param in params_to_remove:
            current_params.pop(param, None)
        return current_params
    except Exception as e:
        logging.error(f"Error cleaning URL parameters: {e}")
        return {}

# NEW FUNCTION: Build Cognito login URL
def get_cognito_login_url():
    """Build Cognito login URL with current page as redirect"""
    try:
        cognito_domain = os.environ.get('COGNITO_DOMAIN')
        client_id = os.environ.get('COGNITO_APP_CLIENT_ID')
        redirect_uri = os.environ.get('COGNITO_REDIRECT_URI')
        
        if not all([cognito_domain, client_id, redirect_uri]):
            return None
        
        params = {
            'client_id': client_id,
            'response_type': 'code',
            'scope': 'email openid profile',
            'redirect_uri': redirect_uri
        }
        
        login_url = f"https://{cognito_domain}/login?" + urlencode(params)
        return login_url
        
    except Exception as e:
        logging.error(f"Error building Cognito login URL: {e}")
        return None

# Cognito authentication handling (legacy functions for backward compatibility)
def get_cognito_token_from_url():
    """Extract Cognito token from URL parameters (legacy method)"""
    return get_cognito_token_from_url_with_auth_code()

def get_cognito_token_from_headers():
    """Extract Cognito token from ALB headers using st.context.header"""
    try:
        # Direct access to ALB Cognito headers using st.context.header (available in Streamlit v1.37.0+)
        oidc_data = st.context.header.get("x-amzn-oidc-data")
        oidc_identity = st.context.header.get("x-amzn-oidc-identity")
        access_token = st.context.header.get("x-amzn-oidc-accesstoken")
        
        if oidc_data:
            return oidc_data
        elif access_token:
            return access_token
    except Exception as e:
        st.debug(f"Error accessing ALB headers: {e}")
    
    return None

# FIXED FUNCTION: User session management - redirect BEFORE any MCP backend calls
def initialize_user_session():
    """Initialize user session with Cognito authentication and auto-redirect"""
    
    # Store current URL for redirect purposes
    if 'current_url' not in st.session_state:
        st.session_state.current_url = os.environ.get('COGNITO_REDIRECT_URI', 'https://localhost:8502/')
    
    # Check for authorization code or existing tokens FIRST
    query_params = st.query_params
    
    # First check for existing token in session state
    if 'cognito_token' in st.session_state:
        cognito_token = st.session_state.cognito_token
    else:
        # Try to get token from URL, headers, or authorization code
        cognito_token = get_cognito_token_from_url_with_auth_code() or get_cognito_token_from_headers()
        
        # Store the token in session state if found
        if cognito_token:
            st.session_state.cognito_token = cognito_token
    
    # PRIORITY: If no authentication found, redirect to Cognito login IMMEDIATELY
    if not cognito_token and 'code' not in query_params and 'id_token' not in query_params:
        # No authentication found, redirect to Cognito login
        login_url = get_cognito_login_url()
        if login_url:
            st.warning("🔐 Authentication required. Redirecting to login...")
            st.markdown(f'<meta http-equiv="refresh" content="2;url={login_url}">', unsafe_allow_html=True)
            st.markdown(f"If you're not redirected automatically, [click here to login]({login_url})")
            st.stop()
    
    # If we have a token, try to authenticate with it (ONLY if token exists)
    if cognito_token:
        try:
            response = requests.get(
                f"{mcp_base_url.rstrip('/')}/v1/user/info",
                headers={'Authorization': f'Bearer {cognito_token}'},
                timeout=5
            )
            if response.status_code == 200:
                user_info = response.json()
                st.session_state.user_id = user_info.get('user_id')
                st.session_state.user_info = user_info
                if local_storage:
                    local_storage.setItem(COOKIE_NAME, st.session_state.user_id)
                logging.info(f"Authenticated with Cognito: {st.session_state.user_id}")
                return
        except Exception as e:
            logging.error(f"Failed to authenticate with Cognito token: {e}")
            # Clear invalid token
            if 'cognito_token' in st.session_state:
                del st.session_state.cognito_token
            if 'cognito_tokens' in st.session_state:
                del st.session_state.cognito_tokens
    
    # If no Cognito token or authentication failed, fall back to local user ID
    if "user_id" not in st.session_state:
        if local_storage and local_storage.getItem(COOKIE_NAME):
            st.session_state.user_id = local_storage.getItem(COOKIE_NAME)
            logging.info(f"Retrieved user ID: {st.session_state.user_id}")
            return
        else:
            # Generate new user ID
            st.session_state.user_id = str(uuid.uuid4())[:8]
            # Save to LocalStorage
            if local_storage:
                local_storage.setItem(COOKIE_NAME, st.session_state.user_id)

# Function to generate random user ID
def generate_random_user_id():
    st.session_state.user_id = str(uuid.uuid4())[:8]
    # Update cookie
    if local_storage:
        local_storage.setItem(COOKIE_NAME, st.session_state.user_id)
    logging.info(f"Generated new random user ID: {st.session_state.user_id}")
    
# Save to cookie when user manually changes ID
def save_user_id():
    st.session_state.user_id = st.session_state.user_id_input
    if local_storage:
        local_storage.setItem(COOKIE_NAME, st.session_state.user_id)
    logging.info(f"Saved user ID: {st.session_state.user_id}")

# NEW FUNCTION: Logout functionality
def logout_user():
    """Logout user and clear authentication state"""
    # Clear Cognito tokens from session
    for key in ['cognito_token', 'cognito_tokens', 'user_info', 'user_id']:
        if key in st.session_state:
            del st.session_state[key]
    
    # Clear local storage
    if local_storage:
        local_storage.removeItem(COOKIE_NAME)
    
    # Build logout URL
    cognito_domain = os.environ.get('COGNITO_DOMAIN')
    client_id = os.environ.get('COGNITO_APP_CLIENT_ID')
    redirect_uri = os.environ.get('COGNITO_REDIRECT_URI')
    
    if cognito_domain and client_id and redirect_uri:
        logout_url = f"https://{cognito_domain}/logout?" + urlencode({
            'client_id': client_id,
            'logout_uri': redirect_uri
        })
        st.query_params.clear()
        st.markdown(f'<meta http-equiv="refresh" content="1;url={logout_url}">', unsafe_allow_html=True)
    
    st.rerun()

# CALL AUTHENTICATION FIRST - BEFORE ANY MCP BACKEND CALLS
initialize_user_session()
    
# MODIFIED FUNCTION: Build authentication headers with token refresh handling
def get_auth_headers():
    """Build authentication headers with token refresh handling"""
    # If we have Cognito tokens, use them
    if 'cognito_tokens' in st.session_state:
        tokens = st.session_state.cognito_tokens
        if tokens and tokens.get('id_token'):
            return {
                'Authorization': f'Bearer {tokens["id_token"]}'
            }
    
    # Fallback to stored cognito_token
    if 'cognito_token' in st.session_state:
        return {
            'Authorization': f'Bearer {st.session_state.cognito_token}'
        }
    
    # Otherwise fall back to API key with X-User-ID
    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'X-User-ID': st.session_state.get('user_id', 'anonymous')
    }
    return headers

def request_list_models():
    url = mcp_base_url.rstrip('/') + '/v1/list/models'
    models = []
    try:
        response = requests.get(url, headers=get_auth_headers(), timeout=10)
        data = response.json()
        models = data.get('models', [])
    except Exception as e:
        logging.error('request list models error: %s' % e)
    return models

def request_list_mcp_servers():
    url = mcp_base_url.rstrip('/') + '/v1/list/mcp_server'
    mcp_servers = []
    try:
        response = requests.get(url, headers=get_auth_headers(), timeout=10)
        data = response.json()
        mcp_servers = data.get('servers', [])
    except Exception as e:
        logging.error('request list mcp servers error: %s' % e)
    return mcp_servers

def request_list_mcp_server_config(mcp_server_id: str):
    url = mcp_base_url.rstrip('/') + '/v1/list/mcp_server_config/' + mcp_server_id
    server_config = {}
    try:
        response = requests.get(url, headers=get_auth_headers(), timeout=10)
        data = response.json()
        server_config = data.get('server_config', [])
    except Exception as e:
        logging.error('request list server tools error: %s' % e)
    return server_config

def request_list_mcp_server_tools(mcp_server_id: str):
    url = mcp_base_url.rstrip('/') + '/v1/list/mcp_server_tools/' + mcp_server_id
    tools_config = {}
    try:
        response = requests.get(url, headers=get_auth_headers(), timeout=10)
        data = response.json()
        tools_config = data.get('tools_config', [])
        logging.info(f'Server ID: {mcp_server_id}, tools_config: {tools_config}')
    except Exception as e:
        logging.error('request list server tools error: %s' % e)
    return tools_config

def request_add_mcp_server(server_id, server_name, command, args=[], env=None, config_json={}):
    url = mcp_base_url.rstrip('/') + '/v1/add/mcp_server'
    status = False
    try:
        payload = {
            "server_id": server_id,
            "server_desc": server_name,
            "command": command,
            "args": args,
            "config_json": config_json
        }
        if env:
            payload["env"] = env
        response = requests.post(url, json=payload, headers=get_auth_headers(), timeout=10)
        data = response.json()
        status = data['errno'] == 0
        msg = data['msg']
    except Exception as e:
        msg = "Add MCP server occurred errors!"
        logging.error('request add mcp servers error: %s' % e)
    return status, msg
        
def request_delete_mcp_server(server_id):
    """
    Send a request to delete an MCP server
    
    Args:
        server_id (str): The ID of the server to delete
        
    Returns:
        tuple: (success, message) where success is a boolean and message is a string
    """
    url = mcp_base_url.rstrip('/') + f'/v1/remove/mcp_server/{server_id}'
    status = False
    try:
        response = requests.delete(url, headers=get_auth_headers(), timeout=10)
        data = response.json()
        status = data['errno'] == 0
        msg = data['msg']
    except Exception as e:
        msg = f"Delete MCP server error: {str(e)}"
        logging.error(f'request delete mcp server error: {e}')
    return status, msg

def process_stream_response(response):
    """Process streaming response and yield content chunks"""
    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data = line[6:]  # Remove 'data: ' prefix
                if data == '[DONE]':
                    break
                try:
                    json_data = json.loads(data)
                    delta = json_data['choices'][0].get('delta', {})
                    if 'role' in delta:
                        continue
                    if 'content' in delta:
                        yield delta['content']
                    
                    message_extras = json_data['choices'][0].get('message_extras', {})
                    if "tool_use" in message_extras:
                        yield f"<tool_use>{message_extras['tool_use']}</tool_use>"

                except json.JSONDecodeError:
                    logging.error(f"Failed to parse JSON: {data}")
                except Exception as e:
                    logging.error(f"Error processing stream: {e}")

def request_chat(messages, model_id, mcp_server_ids, stream=False, max_tokens=1024, temperature=0.6, extra_params={}):
    url = mcp_base_url.rstrip('/') + '/v1/chat/completions'
    msg, msg_extras = 'something is wrong!', {}
    try:
        payload = {
            'messages': messages,
            'model': model_id,
            'mcp_server_ids': mcp_server_ids,
            'extra_params': extra_params,
            'stream': stream,
            'temperature': temperature,
            'max_tokens': max_tokens
        }
        logging.info(f'User {st.session_state.user_id} request payload: %s' % payload)
        
        if stream:
            # Streaming request
            headers = get_auth_headers()
            headers['Accept'] = 'text/event-stream'  
            response = requests.post(url, json=payload, stream=True, headers=headers, timeout=30)
            
            if response.status_code == 200:
                return response, {}
            else:
                msg = 'An error occurred when calling the Converse operation: The system encountered an unexpected error during processing. Try your request again.'
                logging.error(f'User {st.session_state.user_id} chat request error: %d' % response.status_code)
        else:
            # Regular request
            response = requests.post(url, json=payload, headers=get_auth_headers(), timeout=30)
            data = response.json()
            msg = data['choices'][0]['message']['content']
            msg_extras = data['choices'][0]['message_extras']

    except Exception as e:
        msg = 'An error occurred when calling the Converse operation: The system encountered an unexpected error during processing. Try your request again.'
        logging.error(f'User {st.session_state.user_id} chat request error: %s' % e)
    
    logging.info(f'User {st.session_state.user_id} response message: %s' % msg)
    return msg, msg_extras

# MOVED AFTER AUTHENTICATION: Initialize session state with error handling
try:
    if not 'model_names' in st.session_state:
        st.session_state.model_names = {}
        models = request_list_models()  # Now called AFTER authentication
        for x in models:
            st.session_state.model_names[x['model_name']] = x['model_id']
except Exception as e:
    logging.error(f"Failed to load models: {e}")
    st.session_state.model_names = {"Amazon Nova Lite v1": "us.amazon.nova-lite-v1:0"}  # Fallback

try:
    if not 'mcp_servers' in st.session_state:
        st.session_state.mcp_servers = {}
        servers = request_list_mcp_servers()  # Now called AFTER authentication
        for x in servers:
            st.session_state.mcp_servers[x['server_name']] = x['server_id']
except Exception as e:
    logging.error(f"Failed to load MCP servers: {e}")
    st.session_state.mcp_servers = {}  # Fallback

if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = "You are a helpful assistant"

if "messages" not in st.session_state:
    st.session_state.messages = []
    
# Message list always stays in sync with current system_prompt
if not st.session_state.messages or st.session_state.messages[0]["role"] != "system":
    st.session_state.messages.insert(0, {"role": "system", "content": st.session_state.system_prompt})
else:
    st.session_state.messages[0]["content"] = st.session_state.system_prompt 

if "enable_stream" not in st.session_state:
    st.session_state.enable_stream = True
    
if "enable_thinking" not in st.session_state:
    st.session_state.enable_thinking = False

# Function to clear conversation history
def clear_conversation():
    st.session_state.messages = [
        {"role": "system", "content": st.session_state.system_prompt},
    ]
    st.session_state.should_rerun = True

# Check if we need to rerun the app
if "should_rerun" not in st.session_state:
    st.session_state.should_rerun = False
if st.session_state.should_rerun:
    st.session_state.should_rerun = False
    st.rerun()

# add new mcp UI and handle
def add_new_mcp_server_handle():
    status, msg = True, "The server already been added!"
    server_name = st.session_state.new_mcp_server_name
    server_id = st.session_state.new_mcp_server_id
    server_cmd = st.session_state.new_mcp_server_cmd
    server_args = st.session_state.new_mcp_server_args
    server_env = st.session_state.new_mcp_server_env
    server_config_json = st.session_state.new_mcp_server_json_config
    config_json = {}
    if not server_name:
        status, msg = False, "The server name is empty!"
    elif server_name in st.session_state.mcp_servers:
        status, msg = False, "The server name exists, try another name!"

    # If server_config_json is configured, use it as the source of truth
    if server_config_json:
        try:
            config_json = json.loads(server_config_json)
            if not all([isinstance(k, str) for k in config_json.keys()]):
                raise ValueError("env key must be str.")
            if "mcpServers" in config_json:
                config_json = config_json["mcpServers"]
            # Use ID directly from JSON config
            logging.info(f'User {st.session_state.user_id} adding new MCP server: {config_json}')
            server_id = list(config_json.keys())[0]
            server_cmd = config_json[server_id]["command"]
            server_args = config_json[server_id]["args"]
            server_env = config_json[server_id].get('env')
        except Exception as e:
            status, msg = False, "The config must be a valid JSON."

    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', server_id):
        status, msg = False, "The server id must be a valid variable name!"
    elif server_id in st.session_state.mcp_servers.values():
        status, msg = False, "The server id exists, try another one!"
    elif not server_cmd or server_cmd not in mcp_command_list:
        status, msg = False, "The server command is invalid!"
    if server_env:
        try:
            server_env = json.loads(server_env) if not isinstance(server_env, dict) else server_env
            if not all([isinstance(k, str) for k in server_env.keys()]):
                raise ValueError("env key must be str.")
            if not all([isinstance(v, str) for v in server_env.values()]):
                raise ValueError("env value must be str.")
        except Exception as e:
            server_env = {}
            status, msg = False, "The server env must be a JSON dict[str, str]."
    if isinstance(server_args, str):
        server_args = [x.strip() for x in server_args.split(' ') if x.strip()]

    logging.info(f'User {st.session_state.user_id} adding new MCP server: {server_id}:{server_name}')
    
    with st.spinner('Add the server...'):
        status, msg = request_add_mcp_server(server_id, server_name, server_cmd, 
                                             args=server_args, env=server_env, config_json=config_json)
    if status:
        st.session_state.mcp_servers[server_name] = server_id

    st.session_state.new_mcp_server_fd_status = status
    st.session_state.new_mcp_server_fd_msg = msg

def show_delete_confirmation():
    """Set flag to show delete confirmation dialog and update selected server ID"""
    if 'server_to_delete' in st.session_state and st.session_state.server_to_delete:
        server_name = st.session_state.server_to_delete
        if server_name in st.session_state.mcp_servers:
            st.session_state.selected_server_id = st.session_state.mcp_servers[server_name]
        st.session_state.show_delete_confirmation = True
        # Set a flag to trigger rerun after the callback completes
        st.session_state.should_rerun = True

def cancel_delete():
    """Cancel the delete operation"""
    st.session_state.show_delete_confirmation = False
    # Set a flag to trigger rerun after the callback completes
    st.session_state.should_rerun = True

def confirm_delete():
    """Confirm and execute the delete operation"""
    st.session_state.show_delete_confirmation = False
    delete_mcp_server_handle()
    st.session_state.should_rerun = True

def delete_mcp_server_handle():
    """Handle the deletion of an MCP server"""
    if 'server_to_delete' in st.session_state and st.session_state.server_to_delete:
        server_name = st.session_state.server_to_delete
        server_id = st.session_state.mcp_servers[server_name]
        
        logging.info(f'User {st.session_state.user_id} deleting MCP server: {server_id}:{server_name}')
        
        with st.spinner('Deleting the server...'):
            status, msg = request_delete_mcp_server(server_id)
        
        if status:
            # Remove from the dictionary
            if server_name in st.session_state.mcp_servers:
                del st.session_state.mcp_servers[server_name]
        
        st.session_state.delete_server_status = status
        st.session_state.delete_server_msg = msg
        
        if status:
            st.session_state.should_rerun = True


@st.dialog('MCP Server Tools')
def explore_edit_mcp_server():
    # Select server from dropdown outside the form
    mcp_server_name_explore_edit = st.selectbox(
        'Available MCP servers',
        list(st.session_state.mcp_servers),
        key="dialog_server_selector"
    )
    
    # Get server details based on the selected server
    server_name = mcp_server_name_explore_edit
    server_id = st.session_state.mcp_servers[server_name]
    server_config_raw_json = request_list_mcp_server_config(server_id)
    server_tools_raw_json = request_list_mcp_server_tools(server_id)
    
    # Format JSON with proper indentation for better readability
    server_config_formatted_json = ""
    try:
        if server_config_raw_json:
            server_config_formatted_json = json.dumps(server_config_raw_json, indent=2)
    except:
        server_config_formatted_json = server_config_raw_json
    
    server_tools_formatted_json = ""
    try:
        if server_tools_raw_json:
            server_tools_formatted_json = json.dumps(server_tools_raw_json, indent=2)
    except:
        server_tools_formatted_json = server_tools_raw_json
    
    st.markdown("### Server id")
    st.markdown(server_id)

    # Display server configuration with syntax highlighting
    st.markdown("### Server Configuration")
    st.code(json.dumps(server_config_raw_json, indent=2), language="json")

    # Display server tools configuration with syntax highlighting
    st.markdown("### Server Tools Configuration")
    st.code(json.dumps(server_tools_raw_json, indent=2), language="json")


@st.dialog('MCP Server Configuration')
def add_new_mcp_server():
    # Initialize session state variables for deletion if they don't exist
    if 'delete_server_status' not in st.session_state:
        st.session_state.delete_server_status = False
    if 'delete_server_msg' not in st.session_state:
        st.session_state.delete_server_msg = ""
    
    # Create tabs with Explore tab first, followed by Add and Delete
    explore_tab, add_tab, delete_tab = st.tabs(["Explore MCP Server Details", "Add New MCP Server", "Delete MCP Server"])
    
    # Explore MCP Server Details tab (now first)
    with explore_tab:
        # Select server from dropdown
        mcp_server_name_explore = st.selectbox(
            'Select MCP server to explore',
            list(st.session_state.mcp_servers),
            key="explore_server_selector"
        )
        
        if mcp_server_name_explore:
            # Get server details based on the selected server
            server_id = st.session_state.mcp_servers[mcp_server_name_explore]
            server_config_raw_json = request_list_mcp_server_config(server_id)
            server_tools_raw_json = request_list_mcp_server_tools(server_id)
            
            # Display server ID
            st.markdown("### Server ID")
            st.markdown(server_id)
            
            # Display server configuration with syntax highlighting
            st.markdown("### Server Configuration")
            st.code(json.dumps(server_config_raw_json, indent=2), language="json")
            
            # Display server tools configuration with syntax highlighting
            st.markdown("### Server Tools Configuration")
            st.code(json.dumps(server_tools_raw_json, indent=2), language="json")
    
    # Add New MCP Server tab
    with add_tab:
        if 'new_mcp_server_fd_status' in st.session_state:
            if st.session_state.new_mcp_server_fd_status:
                succ1 = st.success(st.session_state.new_mcp_server_fd_msg, icon="✅")
                succ2 = st.success("Please **refresh** the page to display it.", icon="📒")
                time.sleep(3)
                succ1.empty()
                succ2.empty()
                st.session_state.new_mcp_server_fd_msg = ""
                st.session_state.new_mcp_server_id = ""
                st.session_state.new_mcp_server_name = ""
                st.session_state.new_mcp_server_args = ""
                st.session_state.new_mcp_server_env = ""
                st.session_state.new_mcp_server_json_config = ""
                st.session_state.should_rerun = True
            else:
                if st.session_state.new_mcp_server_fd_msg:
                    st.error(st.session_state.new_mcp_server_fd_msg, icon="🚨")

        # Create a form for adding a new MCP server
        with st.form("add_mcp_server_form"):
            new_mcp_server_name = st.text_input("Server Name", 
                                            value="", placeholder="Name description of server", key="new_mcp_server_name")
            
            new_mcp_server_config_json = st.text_area("Use JSON Configuration", 
                                        height=128,
                                        value="", key="new_mcp_server_json_config",
                                        placeholder="Need to provide a valid JSON dictionary")
            
            # Add JSON preview with syntax highlighting if valid JSON is entered
            if new_mcp_server_config_json:
                try:
                    parsed_json = json.loads(new_mcp_server_config_json)
                    st.markdown("### JSON Preview")
                    st.code(json.dumps(parsed_json, indent=2), language="json")
                except json.JSONDecodeError:
                    st.error("Invalid JSON format")
                    
            with st.expander(label='Input Field Configuration', expanded=False):
                new_mcp_server_id = st.text_input("Server ID", 
                                                value="", placeholder="server id", key="new_mcp_server_id")

                new_mcp_server_cmd = st.selectbox("Run Command", 
                                                mcp_command_list, key="new_mcp_server_cmd")
                new_mcp_server_args = st.text_area("Run Arguments", 
                                                value="", key="new_mcp_server_args",
                                                placeholder="mcp-server-git --repository path/to/git/repo")
                new_mcp_server_env = st.text_area("Environment Variables", 
                                                value="", key="new_mcp_server_env",
                                                placeholder="Need to provide a valid JSON dictionary")
            
            # Add button inside the form
            add_button = st.form_submit_button("Add Server", 
                                        on_click=add_new_mcp_server_handle,
                                        disabled=False)
    with delete_tab:
        # Display status messages for deletion
        if 'delete_server_status' in st.session_state:
            if st.session_state.delete_server_status:
                st.success(st.session_state.delete_server_msg, icon="✅")
            else:
                if 'delete_server_msg' in st.session_state and st.session_state.delete_server_msg:
                    st.error(st.session_state.delete_server_msg, icon="🚨")
        
        # Initialize selected_server_id if not present
        if 'selected_server_id' not in st.session_state:
            st.session_state.selected_server_id = ""
        
        # Initialize confirmation dialog flag if not present
        if 'show_delete_confirmation' not in st.session_state:
            st.session_state.show_delete_confirmation = False
        
        # Create a form for deletion
        with st.form("delete_form"):
            st.write("**Delete MCP Server**")
            
            # Add a dropdown to select which server to delete
            if 'mcp_servers' in st.session_state and st.session_state.mcp_servers:
                server_to_delete = st.selectbox(
                    'Select server to delete',
                    list([server for server in st.session_state.mcp_servers if "Built-in" not in server]),
                    key="server_to_delete"
                )
                
                # Request confirmation button
                delete_button = st.form_submit_button(
                    "Request Deletion", 
                    on_click=show_delete_confirmation,
                    disabled=False
                )
            else:
                st.info("No MCP servers available to delete.")
                st.form_submit_button("Request Deletion", 
                                     disabled=True
                                     )
        
        # Show confirmation dialog outside the form
        if st.session_state.get('show_delete_confirmation', False):
            with st.container():
                st.warning(f"⚠️ Are you sure you want to delete the server '{st.session_state.server_to_delete}'? This action cannot be undone.")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Yes, Delete Server", key="confirm_delete", type="primary", use_container_width=True):
                        confirm_delete()
                with col2:
                    if st.button("Done", key="cancel_delete", use_container_width=True):
                        cancel_delete()

def on_system_prompt_change():
    if st.session_state.messages[0]["role"] == "system":
        st.session_state.messages[0]["content"] = st.session_state.system_prompt
        
# UI
with st.sidebar:
    # Show user information
    if 'user_info' in st.session_state and st.session_state.user_info:
        st.write("### User Information")
        st.write(f"Username: {st.session_state.user_info.get('username', 'Unknown')}")
        st.write(f"Email: {st.session_state.user_info.get('email', 'Unknown')}")
        if st.session_state.user_info.get('groups'):
            st.write(f"Groups: {', '.join(st.session_state.user_info.get('groups', []))}")
        
        # Add logout button for authenticated users
        if st.button("🔓 Logout"):
            logout_user()
    else:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.session_state.user_id = st.text_input('User ID', key='user_id_input',value=st.session_state.user_id,on_change=save_user_id, max_chars=32)
        with col2:
            st.button("🔄", on_click=generate_random_user_id, help="Generate random user ID")

    llm_model_name = st.selectbox('Model List',
                                  list(st.session_state.model_names.keys()))
                                  
    # Hide advanced settings in an expander
    with st.expander("Model Settings", expanded=False):
        st.session_state.max_tokens = st.number_input('Max output token',
                                    min_value=1, max_value=64000, value=8000)
        st.session_state.budget_tokens = st.number_input('Max thinking token',
                                    min_value=1024, max_value=128000, value=8192,step=1024)
        st.session_state.temperature = st.number_input('Temperature',
                                    min_value=0.0, max_value=1.0, value=0.6, step=0.1)
                                    
    with st.expander("Conversation Settings", expanded=False):
        st.session_state.system_prompt = st.text_area('System prompt',
                                    value=st.session_state.system_prompt,
                                    height=100,
                                    on_change=on_system_prompt_change,
                                    )
        st.session_state.only_n_most_recent_images = st.number_input('N most recent images',
                                    min_value=0, value=1)
        st.session_state.enable_thinking = st.toggle('Thinking', value=False)
        st.session_state.enable_stream = st.toggle('Stream', value=True)
    
    st.button("🗑️ Reset chat conversation", on_click=clear_conversation, key="clear_button")

    # MCP Tool Discovery
    st.sidebar.title("MCP Server Tools")

    st.button("Explore/Add/Delete MCP Servers", 
              on_click=add_new_mcp_server)

    # Display existing MCP servers with status indicators
    st.write("### Enable MCP Servers in chat")
    for i, server_name in enumerate(st.session_state.mcp_servers):
        st.checkbox(label=server_name, value=False, key=f'mcp_server_{server_name}')

st.title("💬 Bedrock Chatbot with MCP")

# Add pre-filled server suggestion
st.info("""
💡 **Tip:** To add MCP servers, use the formats below
""")
with st.expander("MCP Servers examples"):
    st.markdown("##### Remote Server example")
    st.code("""{
  "mcpServers": {
    "your_server_name": {
      "server_url": "http://your-mcp-server.com/mcp",
      "http_headers": {"Authorization": "Bearer eyJhbG...AxfQ"}
    }
  }
}""", language="json")
    
    st.markdown("##### Local Server example")
    st.code("""{
  "mcpServers": {
    "rijksmuseum-server": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-server-rijksmuseum"
      ],
      "env": {
        "RIJKSMUSEUM_API_KEY": "your_api_key_here"
      }
    }
  }
}""", language="json")

# Display version information
st.markdown(f"<div style='position: fixed; right: 10px; bottom: 10px; font-size: 12px; color: gray;'>Version: {commit_id}</div>", unsafe_allow_html=True)

# Display chat messages
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

# Handle user input
if prompt := st.chat_input():
    # Update system message
    st.session_state.messages[0] = {"role": "system", "content": st.session_state.system_prompt}
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    model_id = st.session_state.model_names[llm_model_name]
    mcp_server_ids = []
    for server_name in st.session_state.mcp_servers:
        server_key = f'mcp_server_{server_name}'
        if st.session_state.get(server_key):
            mcp_server_ids.append(st.session_state.mcp_servers[server_name])

    # Create a placeholder for the assistant's response
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        response, msg_extras = request_chat(st.session_state.messages, model_id, 
                        mcp_server_ids, stream=st.session_state.enable_stream,
                        max_tokens=st.session_state.max_tokens,
                        temperature=st.session_state.temperature, extra_params={
                            "only_n_most_recent_images": st.session_state.only_n_most_recent_images,
                            "budget_tokens": st.session_state.budget_tokens,
                            "enable_thinking": st.session_state.enable_thinking
                        }
                    )
        # Get streaming response
        if st.session_state.enable_stream:
            if isinstance(response, requests.Response):
                # Process streaming response
                tool_count = 1
                content_block_idx = 0
                thinking_content = ""  # Add variable to store accumulated thinking content
                thinking_expander = None  # For storing thinking expander object
                for content in process_stream_response(response):
                    # logging.info(f"content block idx:{content_block_idx}")
                    content_block_idx += 1
                    full_response += content
                    thk_msg, res_msg, tool_msg = "", "", ""
                    thk_regex = r"<thinking>(.*?)</thinking>"
                    tooluse_regex = r"<tool_use>(.*?)</tool_use>"
                    thk_m = re.search(thk_regex, full_response, re.DOTALL)
                    if thk_m:
                        thk_msg = thk_m.group(1)
                        full_response = re.sub(thk_regex, "", full_response,flags=re.DOTALL)
                        # If there's new thinking content, append to existing content
                        if thk_msg != thinking_content:
                            thinking_content = thk_msg  # Update thinking content
                            # Create expander if it doesn't exist, otherwise update existing one
                            if thinking_expander is None:
                                thinking_expander = st.expander("Thinking")
                            with thinking_expander:
                                st.write(thinking_content)

                    tool_m = re.search(tooluse_regex, full_response, re.DOTALL)
                    if tool_m:
                        tool_msg = tool_m.group(1)
                        full_response = re.sub(tooluse_regex, "", full_response)
                    if tool_msg:
                        with st.container(border=True):
                            tool_blocks = json.loads(tool_msg)
                            for i,tool_block in enumerate(tool_blocks):
                                if i%2 == 0:
                                    with st.expander(f"Tool Call:{tool_count}"):
                                        st.code(json.dumps(tool_block, ensure_ascii=False, indent=2), language="json")
                                else:
                                    with st.expander(f"Tool Result:{tool_count}"):
                                         # Process image data
                                        images_data = []
                                        display_tool_block = copy.deepcopy(tool_block)  # Create copy for modification
                                        
                                        # If there's a content field, process images within it
                                        if 'content' in display_tool_block:
                                            for j, block in enumerate(display_tool_block['content']):
                                                if 'image' in block and 'source' in block['image'] and 'base64' in block['image']['source']:
                                                    # Save image data for later display
                                                    images_data.append(BytesIO(base64.b64decode(block['image']['source']['base64'])))
                                                    # Replace base64 string with info message
                                                    display_tool_block['content'][j]['image']['source']['base64'] = "[BASE64 IMAGE DATA - NOT DISPLAYED]"
                                        
                                        # Display processed JSON
                                        st.code(json.dumps(display_tool_block, ensure_ascii=False, indent=2), language="json")
                
                                        # Display images
                                        tool_count += 1
                                        for image_data in images_data:
                                            st.image(image_data)

                    # Update response in real-time
                    response_placeholder.markdown(full_response + "▌")
                
                # Update final response without cursor
                response_placeholder.markdown(full_response)
            else:
                # Handle error case
                response_placeholder.markdown(response)
                full_response = response
        else:
            tool_msg = ""
            if msg_extras.get('tool_use', []):
                tool_msg = f"```\n{json.dumps(msg_extras.get('tool_use', []), indent=4,ensure_ascii=False)}\n```"
            thk_msg, res_msg = "", ""
            thk_regex = r"<thinking>(.*?)</thinking>"
            thk_m = re.search(thk_regex, response, re.DOTALL)
            if thk_m:
                thk_msg = thk_m.group(1)

            res_msg = re.sub(thk_regex, "", response)
            st.write(res_msg)

            if thk_msg:
                with st.expander("Thinking"):
                    st.write(thk_msg)
            if tool_msg:
                with st.expander("Tool Used"):
                    st.json(tool_msg)

            full_response = response 

    # Add assistant's response to chat history
    st.session_state.messages.append({"role": "assistant", "content": full_response})