#!/bin/bash
export $(grep -v '^#' .env | xargs)
export PYTHONPATH=./src:$PYTHONPATH
source .venv/bin/activate

# Create necessary directories
mkdir -p ./tmp 
mkdir -p ${LOG_DIR}

# Set environment variables
export MCP_BASE_URL=http://${MCP_SERVICE_HOST}:${MCP_SERVICE_PORT}
echo "MCP_BASE_URL: ${MCP_BASE_URL}"

# Start MCP service
echo "Starting MCP service..."
nohup python src/main.py --mcp-conf conf/config.json --user-conf conf/user_mcp_config.json \
    --host ${MCP_SERVICE_HOST} --port ${MCP_SERVICE_PORT} > ${LOG_DIR}/start_mcp.log 2>&1 &

# Wait for MCP service to be fully ready
echo "Waiting for MCP service to be ready..."
sleep 15

# Test MCP is responding before starting Streamlit
echo "Testing MCP service health..."
RETRY_COUNT=0
MAX_RETRIES=12  # 60 seconds total (5 seconds * 12 retries)

until curl -f http://127.0.0.1:${MCP_SERVICE_PORT}/v1/list/models \
    -H "Authorization: Bearer ${API_KEY}" \
    -H "X-User-ID: startup-test" > /dev/null 2>&1; do
    
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "ERROR: MCP service failed to start after ${MAX_RETRIES} retries"
        echo "Check MCP logs: ${LOG_DIR}/start_mcp.log"
        exit 1
    fi
    
    echo "Waiting for MCP service... (attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 5
done

echo "MCP service is ready! Starting Chatbot service..."

# Now start Streamlit - MCP is confirmed working
nohup streamlit run chatbot.py \
    --server.port ${CHATBOT_SERVICE_PORT} > ${LOG_DIR}/start_chatbot.log 2>&1 &

echo "Services started successfully. Check logs in ${LOG_DIR}"
echo "MCP API: http://127.0.0.1:${MCP_SERVICE_PORT}"
echo "Streamlit UI: http://127.0.0.1:${CHATBOT_SERVICE_PORT}"