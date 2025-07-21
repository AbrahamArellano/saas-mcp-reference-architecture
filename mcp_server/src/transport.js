import log4js from "log4js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import mcpServer from "./mcp-server.js";
import mcpErrors from "./mcp-errors.js";
import { processJwt } from "./jwt-verifier.js";

const MCP_PATH = "/mcp";

const l = log4js.getLogger();

const bootstrap = async (app) => {
  app.post(MCP_PATH, postRequestHandler);
  app.get(MCP_PATH, sessionRequestHandler);
  app.delete(MCP_PATH, sessionRequestHandler);
};

const postRequestHandler = async (req, res) => {
  try {
    // Check if this is a request to the whoami tool
    const isWhoamiRequest = req.body && 
                           req.body.method === "whoami" && 
                           req.body.jsonrpc === "2.0";
    
    // Only process JWT for non-whoami requests or if Authorization header is present
    if (!isWhoamiRequest || req.get("Authorization")) {
      try {
        // Use the JWT processing function
        req.auth = await processJwt(req.get("Authorization"));
      } catch (authError) {
        // For whoami requests, continue even if authentication fails
        if (!isWhoamiRequest) {
          throw authError; // Re-throw for non-whoami requests
        }
        // For whoami, we'll let the tool handle the auth error
        l.debug(`Authentication error in whoami request: ${authError.message}`);
      }
    }

    // Create new instances of MCP Server and Transport for each incoming request
    const newMcpServer = mcpServer.create();
    const transport = new StreamableHTTPServerTransport({
      // This is a stateless MCP server, so we don't need to keep track of sessions
      sessionIdGenerator: undefined,

      // Uncomment if you want to disable SSE in responses
      // enableJsonResponse: true,
    });

    res.on("close", () => {
      l.debug(`request processing complete`);
      transport.close();
      newMcpServer.close();
    });
    await newMcpServer.connect(transport);
    await transport.handleRequest(req, res, req.body);
  } catch (err) {
    l.error(`Error handling MCP request: ${err.message}`);
    
    if (!res.headersSent) {
      // Return specific error responses based on the error message
      if (err.message.includes('No authorization token provided')) {
        res.status(401).json(mcpErrors.missingToken);
      } else if (err.message.includes('Invalid authorization format')) {
        res.status(401).json(mcpErrors.invalidAuthFormat);
      } else if (err.message.includes('Empty token provided')) {
        res.status(401).json(mcpErrors.emptyToken);
      } else if (err.message.includes('Authentication failed: Your token has expired')) {
        res.status(401).json(mcpErrors.invalidToken);
      } else if (err.message.includes('Authentication failed')) {
        res.status(401).json(mcpErrors.tokenVerificationFailed);
      } else {
        res.status(500).json(mcpErrors.internalServerError);
      }
    }
  }
};

const sessionRequestHandler = async (req, res) => {
  res.status(405).set("Allow", "POST").json(mcpErrors.methodNotAllowed);
};

export default {
  bootstrap,
};
