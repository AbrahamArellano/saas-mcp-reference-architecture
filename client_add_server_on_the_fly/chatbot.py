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
import jwt  # Only for token display
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from typing import Dict, List, Optional, Any, Tuple
import threading
from functools import wraps
import hashlib

load_dotenv()  # load environment variables from .env
API_KEY = os.environ.get("API_KEY")

logging.basicConfig(level=logging.INFO)
mcp_base_url = os.environ.get('MCP_BASE_URL')
mcp_command_list = ["uvx", "npx", "node", "python","docker","uv"]
local_storage = LocalStorage()

# Phase 4: Production-Ready Enhancements (Simplified Validation)

# Global state management
if 'session_lock' not in st.session_state:
    st.session_state.session_lock = threading.RLock()

# Performance optimization: Cache for API responses
if 'api_cache' not in st.session_state:
    st.session_state.api_cache = {}

# Memory management: Track large objects
if 'memory_tracker' not in st.session_state:
    st.session_state.memory_tracker = {
        'large_responses': [],
        'image_count': 0,
        'total_size_mb': 0
    }

def performance_monitor(func):
    """Decorator to monitor function performance"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            if execution_time > 1.0:  # Log slow operations
                logging.warning(f"Slow operation: {func.__name__} took {execution_time:.2f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logging.error(f"Error in {func.__name__} after {execution_time:.2f}s: {e}")
            raise
    return wrapper

def safe_api_call(func):
    """Decorator for robust API error handling"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.ConnectionError as e:
                if attempt == max_retries - 1:
                    st.error("🌐 **Connection Error**: Unable to reach the MCP service. Please check your connection and try again.")
                    logging.error(f"Connection error after {max_retries} attempts: {e}")
                    return None
                time.sleep(retry_delay * (attempt + 1))
            except requests.exceptions.Timeout as e:
                if attempt == max_retries - 1:
                    st.error("⏱️ **Timeout Error**: The request took too long. Please try again.")
                    logging.error(f"Timeout error after {max_retries} attempts: {e}")
                    return None
                time.sleep(retry_delay * (attempt + 1))
            except requests.exceptions.RequestException as e:
                st.error(f"🚨 **Request Error**: {str(e)}")
                logging.error(f"Request error: {e}")
                return None
            except Exception as e:
                st.error(f"❌ **Unexpected Error**: {str(e)}")
                logging.error(f"Unexpected error in {func.__name__}: {e}")
                return None
        return None
    return wrapper

class CacheManager:
    """Smart caching for API responses"""
    
    @staticmethod
    def get_cache_key(endpoint: str, params: Dict = None) -> str:
        """Generate cache key for API requests"""
        key_data = f"{endpoint}_{json.dumps(params or {}, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    @staticmethod
    def get_cached_response(cache_key: str, max_age_seconds: int = 300) -> Optional[Any]:
        """Get cached response if still valid"""
        cache = st.session_state.api_cache
        if cache_key in cache:
            timestamp, data = cache[cache_key]
            if time.time() - timestamp < max_age_seconds:
                return data
            else:
                # Remove expired cache entry
                del cache[cache_key]
        return None
    
    @staticmethod
    def cache_response(cache_key: str, data: Any) -> None:
        """Cache API response with timestamp"""
        st.session_state.api_cache[cache_key] = (time.time(), data)
        
        # Prevent cache from growing too large
        if len(st.session_state.api_cache) > 100:
            # Remove oldest entries
            sorted_cache = sorted(st.session_state.api_cache.items(), 
                                key=lambda x: x[1][0])
            for old_key, _ in sorted_cache[:50]:
                del st.session_state.api_cache[old_key]

class MemoryManager:
    """Memory management for large objects"""
    
    @staticmethod
    def track_large_object(obj_type: str, size_mb: float) -> None:
        """Track memory usage of large objects"""
        tracker = st.session_state.memory_tracker
        tracker['large_responses'].append({
            'type': obj_type,
            'size_mb': size_mb,
            'timestamp': time.time()
        })
        tracker['total_size_mb'] += size_mb
        
        # Clean up old entries
        current_time = time.time()
        tracker['large_responses'] = [
            obj for obj in tracker['large_responses']
            if current_time - obj['timestamp'] < 3600  # Keep for 1 hour
        ]
        
        # Recalculate total
        tracker['total_size_mb'] = sum(obj['size_mb'] for obj in tracker['large_responses'])
        
        # Warn if memory usage is high
        if tracker['total_size_mb'] > 100:  # 100MB threshold
            st.warning("⚠️ High memory usage detected. Consider clearing conversation history.")
    
    @staticmethod
    def track_image(image_size_kb: float) -> None:
        """Track image memory usage"""
        tracker = st.session_state.memory_tracker
        tracker['image_count'] += 1
        MemoryManager.track_large_object('image', image_size_kb / 1024)

def cleanup_session_state():
    """Clean up session state to prevent memory leaks"""
    try:
        # Clean up large responses older than 1 hour
        if 'memory_tracker' in st.session_state:
            current_time = time.time()
            tracker = st.session_state.memory_tracker
            old_count = len(tracker['large_responses'])
            tracker['large_responses'] = [
                obj for obj in tracker['large_responses']
                if current_time - obj['timestamp'] < 3600
            ]
            if old_count > len(tracker['large_responses']):
                logging.info(f"Cleaned up {old_count - len(tracker['large_responses'])} old memory entries")
        
        # Clean up old cache entries
        if 'api_cache' in st.session_state:
            current_time = time.time()
            old_cache = dict(st.session_state.api_cache)
            st.session_state.api_cache = {
                k: v for k, v in old_cache.items()
                if current_time - v[0] < 1800  # Keep for 30 minutes
            }
            
    except Exception as e:
        logging.error(f"Error during session cleanup: {e}")

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

# NEW: Function to get ALB user info
def get_alb_user_info():
    """Extract ALB user information from environment or headers"""
    # In actual ALB deployment, these would come from ALB headers
    # For now, simulate with environment variables for testing
    user_identity = os.environ.get('ALB_USER_IDENTITY')
    user_data = os.environ.get('ALB_USER_DATA')
    
    if user_identity and user_data:
        return {
            'user_identity': user_identity,
            'user_data': user_data
        }
    return None

# Phase 3: Advanced Chat Processing Functions (Enhanced with Phase 4)

def format_thinking_content(thinking_text, start_time=None):
    """Enhanced thinking content formatting with statistics"""
    if not thinking_text:
        return None
        
    # Calculate statistics
    word_count = len(thinking_text.split())
    char_count = len(thinking_text)
    
    # Estimate reading time (average 200 words per minute)
    reading_time = max(1, round(word_count / 200))
    
    # Format timestamp
    timestamp = datetime.now().strftime("%H:%M:%S") if not start_time else start_time
    
    # Track memory usage
    MemoryManager.track_large_object('thinking_content', len(thinking_text) / 1024 / 1024)
    
    return {
        "content": thinking_text,
        "word_count": word_count,
        "char_count": char_count,
        "reading_time": reading_time,
        "timestamp": timestamp
    }

def display_enhanced_thinking(thinking_data):
    """Display thinking content with enhanced formatting"""
    if not thinking_data:
        return
        
    with st.expander(f"🧠 Reasoning Process ({thinking_data['word_count']} words, ~{thinking_data['reading_time']}min read)", expanded=False):
        # Stats header
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Words", thinking_data['word_count'])
        with col2:
            st.metric("Characters", thinking_data['char_count'])
        with col3:
            st.metric("Time", thinking_data['timestamp'])
        
        st.markdown("---")
        
        # Content with better formatting
        st.markdown("**Model's Internal Reasoning:**")
        st.markdown(f'<div style="background-color: #f0f2f6; padding: 1rem; border-radius: 0.5rem; border-left: 4px solid #1f77b4;">{thinking_data["content"]}</div>', unsafe_allow_html=True)

def extract_image_metadata(image_data):
    """Extract metadata from image data with enhanced error handling"""
    try:
        # Get image size
        size_kb = len(image_data.getvalue()) / 1024
        
        # Track image memory usage
        MemoryManager.track_image(size_kb)
        
        # Try to get image dimensions (basic check)
        image_data.seek(0)
        header = image_data.read(24)
        image_data.seek(0)
        
        # Basic format detection with enhanced validation
        if header.startswith(b'\xff\xd8\xff'):
            format_type = "JPEG"
        elif header.startswith(b'\x89PNG\r\n\x1a\n'):
            format_type = "PNG"
        elif header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):
            format_type = "GIF"
        elif header.startswith(b'RIFF') and b'WEBP' in header:
            format_type = "WebP"
        else:
            format_type = "Unknown"
            
        return {
            "size_kb": round(size_kb, 1),
            "format": format_type,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "valid": format_type != "Unknown"
        }
    except Exception as e:
        logging.error(f"Error extracting image metadata: {e}")
        return {"size_kb": 0, "format": "Unknown", "timestamp": "N/A", "valid": False}

def display_enhanced_tool_results(tool_blocks, tool_count):
    """Enhanced tool results display with better formatting and image handling"""
    try:
        for i, tool_block in enumerate(tool_blocks):
            if i % 2 == 0:
                # Tool Call
                tool_use = tool_block.get('toolUse', {})
                tool_name = tool_use.get('name', 'Unknown Tool')
                tool_id = tool_use.get('toolUseId', 'N/A')
                
                with st.expander(f"🔧 Tool Call {tool_count}: {tool_name}", expanded=False):
                    # Tool metadata
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**Tool:** {tool_name}")
                        st.markdown(f"**ID:** `{tool_id[:12]}...`")
                    with col2:
                        st.markdown(f"**Time:** {datetime.now().strftime('%H:%M:%S')}")
                        if tool_use.get('input'):
                            param_count = len(tool_use.get('input', {}))
                            st.markdown(f"**Parameters:** {param_count}")
                    
                    st.markdown("**Request:**")
                    st.code(json.dumps(tool_block, ensure_ascii=False, indent=2), language="json")
            else:
                # Tool Result
                tool_result = tool_block.get('toolResult', {})
                result_id = tool_result.get('toolUseId', 'N/A')
                status = tool_result.get('status', 'success')
                
                # Determine status icon and color
                if status == 'success':
                    status_icon = "✅"
                    status_color = "green"
                elif status == 'error':
                    status_icon = "❌"
                    status_color = "red"
                else:
                    status_icon = "⚠️"
                    status_color = "orange"
                
                with st.expander(f"{status_icon} Tool Result {tool_count}", expanded=False):
                    # Result metadata
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**Status:** <span style='color: {status_color}'>{status.upper()}</span>", unsafe_allow_html=True)
                        st.markdown(f"**Result ID:** `{result_id[:12]}...`")
                    with col2:
                        st.markdown(f"**Time:** {datetime.now().strftime('%H:%M:%S')}")
                    
                    # Process and display content
                    images_data = []
                    display_tool_block = copy.deepcopy(tool_block)
                    
                    # Enhanced image processing with error handling
                    if 'content' in display_tool_block:
                        image_count = 0
                        for j, block in enumerate(display_tool_block['content']):
                            if isinstance(block, dict) and 'image' in block:
                                image_info = block['image']
                                if 'source' in image_info and 'base64' in image_info['source']:
                                    try:
                                        # Decode and process image with validation
                                        image_bytes = base64.b64decode(image_info['source']['base64'])
                                        if len(image_bytes) > 10 * 1024 * 1024:  # 10MB limit
                                            st.warning(f"Image {image_count + 1} is very large ({len(image_bytes)/1024/1024:.1f}MB). Display may be slow.")
                                        
                                        image_data = BytesIO(image_bytes)
                                        
                                        # Extract metadata with validation
                                        metadata = extract_image_metadata(BytesIO(image_bytes))
                                        
                                        if metadata['valid']:
                                            images_data.append({
                                                'data': image_data,
                                                'metadata': metadata,
                                                'format': image_info.get('format', 'unknown')
                                            })
                                            
                                            # Replace base64 with metadata in display
                                            display_tool_block['content'][j]['image']['source']['base64'] = f"[IMAGE {image_count + 1}: {metadata['format']}, {metadata['size_kb']}KB]"
                                        else:
                                            display_tool_block['content'][j]['image']['source']['base64'] = "[INVALID IMAGE FORMAT]"
                                        
                                        image_count += 1
                                    except Exception as e:
                                        logging.error(f"Error processing image {j}: {e}")
                                        display_tool_block['content'][j]['image']['source']['base64'] = f"[ERROR: {str(e)}]"
                    
                    # Display JSON response
                    st.markdown("**Response Data:**")
                    st.code(json.dumps(display_tool_block, ensure_ascii=False, indent=2), language="json")
                    
                    # Enhanced image display with error handling
                    if images_data:
                        st.markdown("**Generated Images:**")
                        for idx, img_info in enumerate(images_data):
                            try:
                                col1, col2 = st.columns([2, 1])
                                with col1:
                                    st.image(img_info['data'], caption=f"Image {idx + 1}")
                                with col2:
                                    st.markdown("**Image Info:**")
                                    st.markdown(f"**Format:** {img_info['metadata']['format']}")
                                    st.markdown(f"**Size:** {img_info['metadata']['size_kb']} KB")
                                    st.markdown(f"**Generated:** {img_info['metadata']['timestamp']}")
                                    
                                    # Download button for images with error handling
                                    try:
                                        img_info['data'].seek(0)
                                        file_extension = img_info['metadata']['format'].lower()
                                        if file_extension == 'unknown':
                                            file_extension = 'bin'
                                        
                                        st.download_button(
                                            label="💾 Download",
                                            data=img_info['data'].getvalue(),
                                            file_name=f"tool_result_image_{idx + 1}.{file_extension}",
                                            mime=f"image/{file_extension}" if file_extension != 'bin' else 'application/octet-stream'
                                        )
                                    except Exception as e:
                                        st.error(f"Download error: {str(e)}")
                            except Exception as e:
                                st.error(f"Error displaying image {idx + 1}: {str(e)}")
    except Exception as e:
        logging.error(f"Error displaying tool results: {e}")
        st.error(f"Error displaying tool results: {str(e)}")

class StreamingProgress:
    """Enhanced streaming progress tracking with performance monitoring"""
    def __init__(self):
        self.start_time = time.time()
        self.token_count = 0
        self.thinking_tokens = 0
        self.tool_calls = 0
        self.last_update = time.time()
        self.error_count = 0
        
    def update_tokens(self, new_content):
        # Rough token estimation (1 token ≈ 4 characters)
        self.token_count += len(new_content) // 4
        self.last_update = time.time()
        
    def update_thinking(self, thinking_content):
        self.thinking_tokens += len(thinking_content) // 4
        
    def increment_tools(self):
        self.tool_calls += 1
        
    def increment_errors(self):
        self.error_count += 1
        
    def get_stats(self):
        elapsed = time.time() - self.start_time
        tokens_per_second = self.token_count / elapsed if elapsed > 0 else 0
        
        return {
            "elapsed": elapsed,
            "tokens": self.token_count,
            "thinking_tokens": self.thinking_tokens,
            "tool_calls": self.tool_calls,
            "error_count": self.error_count,
            "tokens_per_second": tokens_per_second,
            "efficiency": "Good" if tokens_per_second > 10 else "Slow" if tokens_per_second > 5 else "Very Slow"
        }

def display_streaming_stats(progress):
    """Display real-time streaming statistics with performance indicators"""
    stats = progress.get_stats()
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Response Tokens", stats["tokens"])
    with col2:
        st.metric("Thinking Tokens", stats["thinking_tokens"])
    with col3:
        st.metric("Tool Calls", stats["tool_calls"])
    with col4:
        color = "🟢" if stats["tokens_per_second"] > 10 else "🟡" if stats["tokens_per_second"] > 5 else "🔴"
        st.metric("Speed", f"{color} {stats['tokens_per_second']:.1f} t/s")
    with col5:
        if stats["error_count"] > 0:
            st.metric("Errors", stats["error_count"], delta=stats["error_count"])
        else:
            st.metric("Status", "✅ Good")

def get_auth_headers():
    """Build authentication headers containing user identity"""
    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'X-User-ID': 'unknown'  # Keep as fallback
    }
    return headers

# NEW: Function to build query parameters with ALB info
def get_query_params():
    """Build query parameters with ALB user info"""
    params = {}
    alb_info = get_alb_user_info()
    if alb_info:
        params['user_identity'] = alb_info['user_identity']
        params['user_data'] = alb_info['user_data']
    return params

@safe_api_call
@performance_monitor
def request_list_models():
    """Get list of available models with caching"""
    cache_key = CacheManager.get_cache_key('models')
    cached = CacheManager.get_cached_response(cache_key, 600)  # Cache for 10 minutes
    if cached:
        return cached
    
    url = mcp_base_url.rstrip('/') + '/v1/list/models'
    models = []
    try:
        response = requests.get(url, headers=get_auth_headers(), params=get_query_params(), timeout=10)
        response.raise_for_status()
        data = response.json()
        models = data.get('models', [])
        CacheManager.cache_response(cache_key, models)
    except Exception as e:
        logging.error('request list models error: %s' % e)
        raise
    return models

@safe_api_call
@performance_monitor
def request_list_mcp_servers():
    """Get list of MCP servers with caching"""
    cache_key = CacheManager.get_cache_key('mcp_servers')
    cached = CacheManager.get_cached_response(cache_key, 300)  # Cache for 5 minutes
    if cached:
        return cached
    
    url = mcp_base_url.rstrip('/') + '/v1/list/mcp_server'
    mcp_servers = []
    try:
        response = requests.get(url, headers=get_auth_headers(), params=get_query_params(), timeout=10)
        response.raise_for_status()
        data = response.json()
        mcp_servers = data.get('servers', [])
        CacheManager.cache_response(cache_key, mcp_servers)
    except Exception as e:
        logging.error('request list mcp servers error: %s' % e)
        raise
    return mcp_servers

# NEW: Function to get user info from backend
@safe_api_call
@performance_monitor
def request_user_info():
    """Get user information from backend"""
    url = mcp_base_url.rstrip('/') + '/v1/user/info'
    try:
        response = requests.get(url, headers=get_auth_headers(), params=get_query_params(), timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error('request user info error: %s' % e)
        return None

@safe_api_call
@performance_monitor
def request_list_mcp_server_config(mcp_server_id: str):
    """Get MCP server configuration"""
    cache_key = CacheManager.get_cache_key('server_config', {'server_id': mcp_server_id})
    cached = CacheManager.get_cached_response(cache_key, 300)
    if cached:
        return cached
    
    url = mcp_base_url.rstrip('/') + '/v1/list/mcp_server_config/' + mcp_server_id
    server_config = {}
    try:
        response = requests.get(url, headers=get_auth_headers(), params=get_query_params(), timeout=10)
        response.raise_for_status()
        data = response.json()
        server_config = data.get('server_config', {})
        CacheManager.cache_response(cache_key, server_config)
    except Exception as e:
        logging.error('request list server config error: %s' % e)
        raise
    return server_config

@safe_api_call
@performance_monitor
def request_list_mcp_server_tools(mcp_server_id: str):
    """Get MCP server tools"""
    cache_key = CacheManager.get_cache_key('server_tools', {'server_id': mcp_server_id})
    cached = CacheManager.get_cached_response(cache_key, 300)
    if cached:
        return cached
    
    url = mcp_base_url.rstrip('/') + '/v1/list/mcp_server_tools/' + mcp_server_id
    tools_config = {}
    try:
        response = requests.get(url, headers=get_auth_headers(), params=get_query_params(), timeout=15)
        response.raise_for_status()
        data = response.json()
        tools_config = data.get('tools_config', {})
        CacheManager.cache_response(cache_key, tools_config)
        logging.info(f'Server ID: {mcp_server_id}, tools_config: {tools_config}')
    except Exception as e:
        logging.error('request list server tools error: %s' % e)
        raise
    return tools_config

@safe_api_call
@performance_monitor
def request_delete_mcp_server(server_id):
    """Send a request to delete an MCP server"""
    url = mcp_base_url.rstrip('/') + f'/v1/remove/mcp_server/{server_id}'
    status = False
    try:
        response = requests.delete(url, headers=get_auth_headers(), params=get_query_params(), timeout=15)
        response.raise_for_status()
        data = response.json()
        status = data['errno'] == 0
        msg = data['msg']
        
        # Clear related cache entries
        cache_keys_to_clear = ['mcp_servers', f'server_config_{server_id}', f'server_tools_{server_id}']
        for key_pattern in cache_keys_to_clear:
            keys_to_remove = [k for k in st.session_state.api_cache.keys() if key_pattern in k]
            for k in keys_to_remove:
                del st.session_state.api_cache[k]
                
    except Exception as e:
        msg = f"Delete MCP server error: {str(e)}"
        logging.error(f'request delete mcp server error: {e}')
        raise
    return status, msg

@safe_api_call
@performance_monitor
def request_add_mcp_server(server_id, server_name, command, args=[], env=None, config_json={}):
    """Add MCP server with simplified validation"""
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
            
        response = requests.post(url, json=payload, headers=get_auth_headers(), params=get_query_params(), timeout=30)
        response.raise_for_status()
        data = response.json()
        status = data['errno'] == 0
        msg = data['msg']
        
        # Clear cache to reflect new server
        cache_keys_to_clear = ['mcp_servers']
        for key_pattern in cache_keys_to_clear:
            keys_to_remove = [k for k in st.session_state.api_cache.keys() if key_pattern in k]
            for k in keys_to_remove:
                del st.session_state.api_cache[k]
                
    except Exception as e:
        msg = "Add MCP server occurred errors!"
        logging.error('request add mcp servers error: %s' % e)
        raise
    return status, msg

def process_stream_response(response, progress_tracker=None):
    """Enhanced streaming response processing with robust error handling"""
    try:
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
                            content = delta['content']
                            if progress_tracker:
                                progress_tracker.update_tokens(content)
                            yield content
                        
                        message_extras = json_data['choices'][0].get('message_extras', {})
                        if "tool_use" in message_extras:
                            if progress_tracker:
                                progress_tracker.increment_tools()
                            yield f"<tool_use>{message_extras['tool_use']}</tool_use>"

                    except json.JSONDecodeError as e:
                        logging.error(f"Failed to parse JSON: {data}")
                        if progress_tracker:
                            progress_tracker.increment_errors()
                    except Exception as e:
                        logging.error(f"Error processing stream: {e}")
                        if progress_tracker:
                            progress_tracker.increment_errors()
    except Exception as e:
        logging.error(f"Stream processing error: {e}")
        if progress_tracker:
            progress_tracker.increment_errors()

@safe_api_call
@performance_monitor
def request_chat(messages, model_id, mcp_server_ids, stream=False, max_tokens=1024, temperature=0.6, extra_params={}):
    """Enhanced chat request with robust error handling"""
    url = mcp_base_url.rstrip('/') + '/v1/chat/completions'
    msg, msg_extras = 'Something went wrong!', {}
    
    # Track large request
    request_size = len(json.dumps(messages)) / 1024 / 1024  # MB
    if request_size > 1:  # 1MB threshold
        MemoryManager.track_large_object('chat_request', request_size)
    
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
        logging.info(f'Request payload: %s' % payload)
        
        if stream:
            # Streaming request
            headers = get_auth_headers()
            headers['Accept'] = 'text/event-stream'  
            response = requests.post(url, json=payload, stream=True, headers=headers, params=get_query_params(), timeout=60)
            response.raise_for_status()
            return response, {}
        else:
            # Regular request
            response = requests.post(url, json=payload, headers=get_auth_headers(), params=get_query_params(), timeout=60)
            response.raise_for_status()
            data = response.json()
            msg = data['choices'][0]['message']['content']
            msg_extras = data['choices'][0]['message_extras']

    except requests.exceptions.Timeout:
        msg = '⏱️ **Request Timeout**: The request took too long. Try reducing max tokens or simplifying your request.'
        logging.error('Chat request timeout')
        raise
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else 'Unknown'
        msg = f'🚨 **Server Error** ({status_code}): The server encountered an error. Please try again.'
        logging.error(f'Chat request HTTP error: {e}')
        raise
    except Exception as e:
        msg = f'❌ **Unexpected Error**: {str(e)}'
        logging.error(f'Chat request error: %s' % e)
        raise
    
    logging.info(f'Response message: %s' % msg)
    return msg, msg_extras

# Initialize session state with enhanced error handling
try:
    if not 'model_names' in st.session_state:
        st.session_state.model_names = {}
        models = request_list_models()
        if models:
            for x in models:
                st.session_state.model_names[x['model_name']] = x['model_id']

    if not 'mcp_servers' in st.session_state:
        st.session_state.mcp_servers = {}
        servers = request_list_mcp_servers()
        if servers:
            for x in servers:
                st.session_state.mcp_servers[x['server_name']] = x['server_id']
except Exception as e:
    st.error(f"Failed to initialize application: {str(e)}")
    st.info("Please check your connection and refresh the page.")
    st.stop()

if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = "You are a deep researcher"

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

# Function to clear conversation history with cleanup
def clear_conversation():
    st.session_state.messages = [
        {"role": "system", "content": st.session_state.system_prompt},
    ]
    # Clean up memory
    cleanup_session_state()
    st.session_state.should_rerun = True

# Check if we need to rerun the app
if "should_rerun" not in st.session_state:
    st.session_state.should_rerun = False
if st.session_state.should_rerun:
    st.session_state.should_rerun = False
    st.rerun()

# Enhanced MCP Server Management Functions (Simplified Validation)

def show_delete_confirmation():
    """Set flag to show delete confirmation dialog and update selected server ID"""
    if 'server_to_delete' in st.session_state and st.session_state.server_to_delete:
        server_name = st.session_state.server_to_delete
        if server_name in st.session_state.mcp_servers:
            st.session_state.selected_server_id = st.session_state.mcp_servers[server_name]
        st.session_state.show_delete_confirmation = True
        st.session_state.should_rerun = True

def cancel_delete():
    """Cancel the delete operation"""
    st.session_state.show_delete_confirmation = False
    st.session_state.should_rerun = True

def confirm_delete():
    """Confirm and execute the delete operation"""
    st.session_state.show_delete_confirmation = False
    delete_mcp_server_handle()
    st.session_state.should_rerun = True

def delete_mcp_server_handle():
    """Handle the deletion of an MCP server with enhanced error handling"""
    if 'server_to_delete' in st.session_state and st.session_state.server_to_delete:
        server_name = st.session_state.server_to_delete
        server_id = st.session_state.mcp_servers[server_name]
        
        logging.info(f'Deleting MCP server: {server_id}:{server_name}')
        
        try:
            with st.spinner('Deleting the server...'):
                result = request_delete_mcp_server(server_id)
                if result:
                    status, msg = result
                    if status:
                        # Remove from the dictionary
                        if server_name in st.session_state.mcp_servers:
                            del st.session_state.mcp_servers[server_name]
                    st.session_state.delete_server_status = status
                    st.session_state.delete_server_msg = msg
                    
                    if status:
                        st.session_state.should_rerun = True
                else:
                    st.session_state.delete_server_status = False
                    st.session_state.delete_server_msg = "Failed to delete server"
        except Exception as e:
            st.session_state.delete_server_status = False
            st.session_state.delete_server_msg = f"Error: {str(e)}"

# Simplified MCP server handling - validate on submit
def add_new_mcp_server_handle():
    """Simplified server addition - validate on submit with clear error messages"""
    status, msg = True, "The server has been added successfully!"
    
    try:
        # Get form values
        server_name = st.session_state.get('new_mcp_server_name', '').strip()
        server_id = st.session_state.get('new_mcp_server_id', '').strip()
        server_cmd = st.session_state.get('new_mcp_server_cmd', '')
        server_args = st.session_state.get('new_mcp_server_args', '')
        server_env = st.session_state.get('new_mcp_server_env', '')
        server_config_json = st.session_state.get('new_mcp_server_json_config', '').strip()
        
        # Simple validation with clear messages
        if not server_name:
            status, msg = False, "❌ **Server name is required**"
            return status, msg
        
        if len(server_name) < 3:
            status, msg = False, "❌ **Server name must be at least 3 characters long**"
            return status, msg
        
        if server_name in st.session_state.mcp_servers:
            status, msg = False, f"⚠️ **Server name '{server_name}' already exists!** Please choose a different name."
            return status, msg
        
        config_json = {}
        
        # Process JSON configuration if provided
        if server_config_json:
            try:
                config_json = json.loads(server_config_json)
                
                if "mcpServers" in config_json:
                    config_json = config_json["mcpServers"]
                    
                if not config_json:
                    status, msg = False, "❌ **JSON configuration is empty**"
                    return status, msg
                    
                server_id = list(config_json.keys())[0]
                server_conf = config_json[server_id]
                
                # Check if this is a remote server configuration
                if "server_url" in server_conf:
                    # This is a remote server configuration
                    if not server_conf["server_url"].startswith(("http://", "https://")):
                        status, msg = False, "❌ **Server URL must start with http:// or https://**"
                        return status, msg
                else:
                    # This is a local server configuration
                    if "command" not in server_conf:
                        status, msg = False, "❌ **JSON configuration missing 'command' field**"
                        return status, msg
                    server_cmd = server_conf["command"]
                    server_args = server_conf["args"]
                    server_env = server_conf.get('env', {})
                    
            except json.JSONDecodeError as e:
                status, msg = False, f"❌ **Invalid JSON format**: {str(e)}"
                return status, msg
        else:
            # Manual configuration validation
            if not server_id:
                status, msg = False, "❌ **Server ID is required when using manual configuration**"
                return status, msg
            
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', server_id):
                status, msg = False, "❌ **Server ID must start with a letter and contain only letters, numbers, underscores, and hyphens**"
                return status, msg
            
            if server_id in st.session_state.mcp_servers.values():
                status, msg = False, f"⚠️ **Server ID '{server_id}' already exists!** Please choose a different ID."
                return status, msg
            
            if not server_cmd or server_cmd not in mcp_command_list:
                status, msg = False, f"❌ **Invalid command!** Must be one of: {', '.join(mcp_command_list)}"
                return status, msg
        
        # Validate environment variables if provided
        if server_env and isinstance(server_env, str):
            try:
                server_env = json.loads(server_env)
                if not isinstance(server_env, dict):
                    status, msg = False, "❌ **Environment variables must be a JSON object**"
                    return status, msg
            except json.JSONDecodeError as e:
                status, msg = False, f"❌ **Invalid environment variables JSON**: {str(e)}"
                return status, msg
        
        # Process arguments
        if isinstance(server_args, str):
            server_args = [x.strip() for x in server_args.split(' ') if x.strip()]

        logging.info(f'Adding new MCP server: {server_id}:{server_name}')
        
        # Make API call
        with st.spinner('Adding the server...'):
            result = request_add_mcp_server(server_id, server_name, server_cmd, 
                                          args=server_args, env=server_env, config_json=config_json)
            if result:
                status, msg = result
                if status:
                    st.session_state.mcp_servers[server_name] = server_id
            else:
                status, msg = False, "❌ **Failed to add server due to connection error**"
        
    except Exception as e:
        status, msg = False, f"❌ **Unexpected error**: {str(e)}"
        logging.error(f"Error in add_new_mcp_server_handle: {e}")
    
    st.session_state.new_mcp_server_fd_status = status
    st.session_state.new_mcp_server_fd_msg = msg

@st.dialog('MCP Server Management')
def add_new_mcp_server():
    # Initialize session state variables
    if 'delete_server_status' not in st.session_state:
        st.session_state.delete_server_status = False
    if 'delete_server_msg' not in st.session_state:
        st.session_state.delete_server_msg = ""
    if 'show_delete_confirmation' not in st.session_state:
        st.session_state.show_delete_confirmation = False
    if 'selected_server_id' not in st.session_state:
        st.session_state.selected_server_id = ""
    
    # Create tabs
    explore_tab, add_tab, delete_tab = st.tabs(["🔍 Explore Servers", "➕ Add Server", "🗑️ Delete Server"])
    
    # Explore Tab
    with explore_tab:
        if st.session_state.mcp_servers:
            selected_server_name = st.selectbox(
                'Select MCP server to explore',
                list(st.session_state.mcp_servers.keys()),
                key="explore_server_selector"
            )
            
            if selected_server_name:
                server_id = st.session_state.mcp_servers[selected_server_name]
                
                try:
                    with st.spinner("Loading server information..."):
                        server_config = request_list_mcp_server_config(server_id)
                        server_tools = request_list_mcp_server_tools(server_id)
                    
                    # Display server information
                    st.markdown("### Server Information")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**Server Name:** {selected_server_name}")
                    with col2:
                        st.markdown(f"**Server ID:** {server_id}")
                    
                    # Display server configuration
                    st.markdown("### Server Configuration")
                    if server_config:
                        st.code(json.dumps(server_config, indent=2), language="json")
                    else:
                        st.info("No configuration available for this server")
                    
                    # Display available tools
                    st.markdown("### Available Tools")
                    if server_tools and server_tools.get('tools'):
                        st.code(json.dumps(server_tools, indent=2), language="json")
                        
                        # Show tool summary
                        tools_list = server_tools.get('tools', [])
                        if tools_list:
                            st.markdown("#### Tool Summary")
                            for i, tool in enumerate(tools_list, 1):
                                tool_spec = tool.get('toolSpec', {})
                                tool_name = tool_spec.get('name', 'Unknown')
                                tool_desc = tool_spec.get('description', 'No description available')
                                st.markdown(f"**{i}. {tool_name}:** {tool_desc}")
                    else:
                        st.info("No tools available for this server")
                        
                except Exception as e:
                    st.error(f"❌ **Error loading server information**: {str(e)}")
                    logging.error(f"Error in explore tab: {e}")
        else:
            st.info("No MCP servers available to explore. Add a server first!")
    
    # Add Tab - Simplified validation
    with add_tab:
        # Show error/success messages with auto-clear
        if 'new_mcp_server_fd_status' in st.session_state:
            if st.session_state.new_mcp_server_fd_status:
                success_container = st.success(st.session_state.new_mcp_server_fd_msg, icon="✅")
                refresh_container = st.success("Server added successfully! Please **refresh** to see it in the list.", icon="📒")
                time.sleep(3)
                success_container.empty()
                refresh_container.empty()
                # Clear form fields
                for key in ['new_mcp_server_fd_msg', 'new_mcp_server_id', 'new_mcp_server_name', 
                          'new_mcp_server_args', 'new_mcp_server_env', 'new_mcp_server_json_config']:
                    if key in st.session_state:
                        st.session_state[key] = ""
                st.session_state.should_rerun = True
            else:
                if st.session_state.get('new_mcp_server_fd_msg'):
                    st.error(st.session_state.new_mcp_server_fd_msg, icon="🚨")

        # Pre-filled examples
        st.markdown("### 📋 Quick Start Examples")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📁 Local Filesystem", use_container_width=True):
                st.session_state.new_mcp_server_json_config = """{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/directory"],
      "env": {"READ_ONLY": "true"}
    }
  }
}"""
        
        with col2:
            if st.button("🌐 Web Search (Exa)", use_container_width=True):
                st.session_state.new_mcp_server_json_config = """{
  "mcpServers": {
    "exa_search": {
      "command": "npx",
      "args": ["-y", "exa-mcp-server"],
      "env": {"EXA_API_KEY": "your_api_key_here"}
    }
  }
}"""

        # Simple form - always enabled submit button
        with st.form("add_mcp_server_form"):
            new_mcp_server_name = st.text_input("Server Name *", 
                                                value="", 
                                                placeholder="Enter a descriptive name for this server", 
                                                key="new_mcp_server_name",
                                                help="This name will appear in the server list for easy identification")
            
            new_mcp_server_config_json = st.text_area("JSON Configuration", 
                                        height=200,
                                        value="", key="new_mcp_server_json_config",
                                        placeholder='{"mcpServers": {"server_name": {"command": "npx", "args": ["-y", "package-name"]}}}',
                                        help="Provide complete MCP server configuration in JSON format. Use examples above or manual config below.")
            
            # Simple JSON preview
            if new_mcp_server_config_json:
                try:
                    parsed_json = json.loads(new_mcp_server_config_json)
                    st.markdown("#### ✅ JSON Preview")
                    st.code(json.dumps(parsed_json, indent=2), language="json")
                except json.JSONDecodeError as e:
                    st.markdown("#### ❌ JSON Error")
                    st.error(f"Invalid JSON: {str(e)}")
                    
            with st.expander(label='Manual Configuration (Alternative)', expanded=False):
                new_mcp_server_id = st.text_input("Server ID", 
                                                value="", 
                                                placeholder="unique_server_id", 
                                                key="new_mcp_server_id",
                                                help="Unique identifier for this server")

                new_mcp_server_cmd = st.selectbox("Run Command", 
                                                mcp_command_list, 
                                                key="new_mcp_server_cmd",
                                                help="Command used to execute the MCP server")
                                                
                new_mcp_server_args = st.text_area("Run Arguments", 
                                                value="", key="new_mcp_server_args",
                                                placeholder="-y @modelcontextprotocol/server-filesystem /path/to/directory",
                                                help="Command line arguments for the MCP server")
                                                
                new_mcp_server_env = st.text_area("Environment Variables", 
                                                value="", key="new_mcp_server_env",
                                                placeholder='{"API_KEY": "your_key_here", "PARAM": "value"}',
                                                help="Environment variables in JSON format")

            # Always enabled submit button - validate on submit
            submitted = st.form_submit_button("Add Server", 
                                              on_click=add_new_mcp_server_handle,
                                              use_container_width=True)
    
    # Delete Tab
    with delete_tab:
        # Display status messages
        if 'delete_server_status' in st.session_state:
            if st.session_state.delete_server_status:
                st.success(st.session_state.delete_server_msg, icon="✅")
                st.session_state.delete_server_status = False
                st.session_state.delete_server_msg = ""
            else:
                if 'delete_server_msg' in st.session_state and st.session_state.delete_server_msg:
                    st.error(st.session_state.delete_server_msg, icon="🚨")
        
        # Filter out built-in servers
        deletable_servers = [server for server in st.session_state.mcp_servers 
                           if "Built-in" not in server]
        
        if deletable_servers:
            with st.form("delete_form"):
                st.markdown("### ⚠️ Delete MCP Server")
                st.warning("This action cannot be undone. The server will be permanently removed from your session.")
                
                server_to_delete = st.selectbox(
                    'Select server to delete',
                    deletable_servers,
                    key="server_to_delete",
                    help="Choose the MCP server you want to remove"
                )
                
                if server_to_delete:
                    server_id = st.session_state.mcp_servers[server_to_delete]
                    st.info(f"**Server ID:** {server_id}")
                
                delete_button = st.form_submit_button(
                    "🗑️ Request Deletion", 
                    on_click=show_delete_confirmation,
                    use_container_width=True
                )
        else:
            st.info("No user-added MCP servers available to delete.")
            st.button("🗑️ Request Deletion", 
                     disabled=True,
                     use_container_width=True)
        
        # Confirmation dialog
        if st.session_state.get('show_delete_confirmation', False):
            st.markdown("---")
            st.error(f"⚠️ **Confirm Deletion**\n\nAre you sure you want to delete the server '{st.session_state.server_to_delete}'?\n\nThis action cannot be undone.")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Yes, Delete Server", 
                           key="confirm_delete", 
                           type="primary", 
                           use_container_width=True):
                    confirm_delete()
            with col2:
                if st.button("❌ Cancel", 
                           key="cancel_delete", 
                           use_container_width=True):
                    cancel_delete()

def on_system_prompt_change():
    if st.session_state.messages[0]["role"] == "system":
        st.session_state.messages[0]["content"] = st.session_state.system_prompt
        
# UI
with st.sidebar:
    # User info display in collapsible format
    with st.expander("👤 User Information", expanded=False):
        try:
            user_info = request_user_info()
            if user_info:
                if user_info.get('email'):
                    st.markdown(f"📧 **Email:** {user_info['email']}")
                if user_info.get('username'):
                    st.markdown(f"👤 **Username:** {user_info['username']}")
                if user_info.get('user_id'):
                    st.markdown(f"🆔 **User ID:** `{user_info['user_id'][:12]}...`")
                if user_info.get('session_id'):
                    st.markdown(f"🔗 **Session:** `{user_info['session_id'][:8]}...`")
                if user_info.get('groups'):
                    st.markdown(f"👥 **Groups:** {', '.join(user_info['groups'])}")
                
                if not any([user_info.get('email'), user_info.get('username'), user_info.get('groups')]):
                    st.info("Using fallback authentication")
            else:
                # Fallback to show basic info
                alb_info = get_alb_user_info()
                if alb_info:
                    st.markdown(f"🔐 **ALB User:** {alb_info['user_identity'][:20]}...")
                else:
                    st.markdown("🔧 **Mode:** Local Development")
        except Exception as e:
            st.error(f"Unable to load user info: {str(e)}")

    # Model Selection
    if st.session_state.model_names:
        llm_model_name = st.selectbox('Model',
                                      list(st.session_state.model_names.keys()),
                                      help="Select the language model to use for conversations")
    else:
        st.error("No models available. Please check your connection.")
        st.stop()
                                      
    # Collapsible Model Settings
    with st.expander("Model Settings", expanded=False):
        st.session_state.max_tokens = st.number_input('Max output tokens',
                                     min_value=1, max_value=64000, value=8000,
                                     help="Maximum number of tokens the model can generate")
        st.session_state.budget_tokens = st.number_input('Max thinking tokens',
                                     min_value=1024, max_value=128000, value=8192, step=1024,
                                     help="Maximum tokens for model reasoning (Claude models only)")
        st.session_state.temperature = st.number_input('Temperature',
                                     min_value=0.0, max_value=1.0, value=0.6, step=0.1,
                                     help="Controls randomness: 0.0 = deterministic, 1.0 = very random")
                                     
    # Collapsible Conversation Settings
    with st.expander("Conversation Settings", expanded=False):
        st.session_state.system_prompt = st.text_area('System Prompt',
                                    value=st.session_state.system_prompt,
                                    height=100,
                                    on_change=on_system_prompt_change,
                                    help="Instructions that guide the model's behavior throughout the conversation")
        st.session_state.only_n_most_recent_images = st.number_input('Recent images to keep',
                                     min_value=0, value=1,
                                     help="Number of most recent images to retain in conversation history")
        st.session_state.enable_thinking = st.toggle('Enable Thinking', 
                                                    value=False,
                                                    help="Show model's reasoning process (Claude models only)")
        st.session_state.enable_stream = st.toggle('Stream Response', 
                                                  value=True,
                                                  help="Display response as it's being generated")

    # MCP Servers Section
    st.markdown("### MCP Servers")
    
    # Show memory usage if significant
    if st.session_state.memory_tracker['total_size_mb'] > 10:
        st.caption(f"Memory usage: {st.session_state.memory_tracker['total_size_mb']:.1f}MB")
    
    st.markdown(f"**Active Servers:** {len(st.session_state.mcp_servers)}")
    
    with st.expander(label='Enable Servers for Chat', expanded=True):
        if st.session_state.mcp_servers:
            for i, server_name in enumerate(st.session_state.mcp_servers):
                st.checkbox(label=server_name, value=False, key=f'mcp_server_{server_name}')
        else:
            st.info("No MCP servers available. Add one below!")
    
    st.button("⚙️ Manage MCP Servers", 
              on_click=add_new_mcp_server,
              use_container_width=True,
              help="Add, explore, or delete MCP servers")
    
    # Clear conversation button
    st.button("🗑️ Clear Conversation", 
             on_click=clear_conversation, 
             key="clear_button",
             use_container_width=True,
             help="Clear conversation history and free memory")

st.title("💬 Bedrock Chatbot with MCP")

# Enhanced Quick Start section
st.info("""
💡 **Production-Ready Experience:** This chatbot features comprehensive error handling, performance monitoring, 
smart caching, memory management, and simplified validation. Use "Manage MCP Servers" to add powerful external capabilities.
""")

# Display version information
st.markdown(f"<div style='position: fixed; right: 10px; bottom: 10px; font-size: 12px; color: gray; background: rgba(255,255,255,0.8); padding: 2px 6px; border-radius: 3px;'>v{commit_id}</div>", unsafe_allow_html=True)

# Display chat messages
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

# Handle user input with enhanced error handling
if prompt := st.chat_input("Type your message here..."):
    try:
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
            
            try:
                response, msg_extras = request_chat(st.session_state.messages, model_id, 
                                mcp_server_ids, stream=st.session_state.enable_stream,
                                max_tokens=st.session_state.max_tokens,
                                temperature=st.session_state.temperature, extra_params={
                                    "only_n_most_recent_images": st.session_state.only_n_most_recent_images,
                                    "budget_tokens": st.session_state.budget_tokens,
                                    "enable_thinking": st.session_state.enable_thinking
                                }
                            )
                
                # Enhanced streaming response processing
                if st.session_state.enable_stream:
                    if isinstance(response, requests.Response):
                        # Initialize enhanced progress tracking
                        progress_tracker = StreamingProgress()
                        
                        # Create containers for real-time updates
                        stats_container = st.empty()
                        thinking_container = st.empty()
                        
                        tool_count = 1
                        thinking_content = ""
                        thinking_start_time = datetime.now().strftime("%H:%M:%S")
                        
                        try:
                            for content in process_stream_response(response, progress_tracker):
                                full_response += content
                                
                                # Process different content types
                                thk_msg, tool_msg = "", ""
                                thk_regex = r"<thinking>(.*?)</thinking>"
                                tooluse_regex = r"<tool_use>(.*?)</tool_use>"
                                
                                # Enhanced thinking processing
                                thk_m = re.search(thk_regex, full_response, re.DOTALL)
                                if thk_m:
                                    thk_msg = thk_m.group(1)
                                    full_response = re.sub(thk_regex, "", full_response, flags=re.DOTALL)
                                    if thk_msg != thinking_content:
                                        thinking_content = thk_msg
                                        progress_tracker.update_thinking(thk_msg)
                                        # Display enhanced thinking
                                        thinking_data = format_thinking_content(thinking_content, thinking_start_time)
                                        with thinking_container.container():
                                            display_enhanced_thinking(thinking_data)

                                # Enhanced tool processing
                                tool_m = re.search(tooluse_regex, full_response, re.DOTALL)
                                if tool_m:
                                    tool_msg = tool_m.group(1)
                                    full_response = re.sub(tooluse_regex, "", full_response)
                                    
                                if tool_msg:
                                    with st.container(border=True):
                                        try:
                                            tool_blocks = json.loads(tool_msg)
                                            display_enhanced_tool_results(tool_blocks, tool_count)
                                            tool_count += 1
                                        except json.JSONDecodeError as e:
                                            st.error(f"Error parsing tool results: {e}")

                                # Update real-time statistics
                                with stats_container.container():
                                    st.markdown("### 📊 Live Statistics")
                                    display_streaming_stats(progress_tracker)
                                
                                # Update response with cursor
                                response_placeholder.markdown(full_response + "▌")
                        
                        except Exception as e:
                            st.error(f"Error during streaming: {str(e)}")
                            logging.error(f"Streaming error: {e}")
                        
                        # Final response without cursor and clear stats
                        response_placeholder.markdown(full_response)
                        stats_container.empty()
                    else:
                        response_placeholder.markdown(response)
                        full_response = response
                else:
                    # Enhanced non-streaming response
                    if msg_extras.get('tool_use', []):
                        st.markdown("### 🔧 Tools Used")
                        with st.container(border=True):
                            for i, tool_info in enumerate(msg_extras.get('tool_use', []), 1):
                                with st.expander(f"Tool {i}: {tool_info.get('name', 'Unknown')}", expanded=False):
                                    st.code(json.dumps(tool_info, ensure_ascii=False, indent=2), language="json")
                    
                    # Enhanced thinking display for non-streaming
                    thk_regex = r"<thinking>(.*?)</thinking>"
                    thk_m = re.search(thk_regex, response, re.DOTALL)
                    if thk_m:
                        thk_msg = thk_m.group(1)
                        thinking_data = format_thinking_content(thk_msg)
                        display_enhanced_thinking(thinking_data)

                    # Clean response content
                    clean_response = re.sub(thk_regex, "", response)
                    st.write(clean_response)
                    full_response = response
            
            except Exception as e:
                st.error(f"❌ **Error generating response**: {str(e)}")
                logging.error(f"Chat error: {e}")
                full_response = f"Error: {str(e)}"
                response_placeholder.markdown(full_response)

        # Add assistant's response to chat history
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        
        # Cleanup after large responses
        cleanup_session_state()
        
    except Exception as e:
        st.error(f"❌ **Critical Error**: {str(e)}")
        logging.error(f"Critical chat error: {e}")

# Periodic cleanup (every 50 messages)
if len(st.session_state.messages) % 50 == 0:
    cleanup_session_state()