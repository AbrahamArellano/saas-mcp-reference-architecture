import log4js from "log4js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import mcpServer from "./mcp-server.js";
import mcpErrors from "./mcp-errors.js";
import { processJwt } from "./jwt-verifier.js";

const MCP_PATH = "/mcp";

const l = log4js.getLogger();

// List of methods that can be accessed without authentication
const PUBLIC_METHODS = [
  "initialize",
  "notifications/initialized",
  "tools/list",
  "whoami"
];

const bootstrap = async (app) => {
  app.post(MCP_PATH, postRequestHandler);
  app.get(MCP_PATH, sessionRequestHandler);
  app.delete(MCP_PATH, sessionRequestHandler);
};

/**
 * Extract token from authorization header
 */
function extractToken(authHeader) {
  if (!authHeader) {
    return null;
  }
  
  if (!authHeader.startsWith("Bearer ")) {
    return null;
  }
  
  const token = authHeader.substring(7).trim();
  if (token === "") {
    return null;
  }
  
  return token;
}

const postRequestHandler = async (req, res) => {
  try {
    // Store the original authorization header
    const originalAuthHeader = req.get("Authorization");
    
    // Store it in a global variable that the whoami tool can access
    global.lastAuthHeader = originalAuthHeader;
    
    // Extract the token from the Authorization header
    const token = extractToken(originalAuthHeader);
    
    // If this is a tools/call for whoami, add the token to the arguments
    if (req.body && 
        req.body.jsonrpc === "2.0" && 
        req.body.method === "tools/call" && 
        req.body.params && 
        req.body.params.name === "whoami") {
      
      if (!req.body.params.arguments) {
        req.body.params.arguments = {};
      }
      
      if (token) {
        req.body.params.arguments.token = token;
        l.debug("Added token to whoami tool arguments");
      } else {
        l.debug("No valid token found to add to whoami tool arguments");
      }
    }
    
    // Check if this is a public endpoint request
    let isPublicEndpoint = req.body && 
                          req.body.jsonrpc === "2.0" && 
                          PUBLIC_METHODS.includes(req.body.method);
    
    // Special case for tools/call with whoami tool
    if (req.body && 
        req.body.jsonrpc === "2.0" && 
        req.body.method === "tools/call" && 
        req.body.params && 
        req.body.params.name === "whoami") {
      isPublicEndpoint = true;
      l.debug("Special case: tools/call with whoami tool is a public endpoint");
    }
    
    l.debug(`Request method: ${req.body?.method}, isPublicEndpoint: ${isPublicEndpoint}`);
    
    let isAuthenticated = false;
    let isUnsignedToken = false;
    
    if (isPublicEndpoint) {
      // For public endpoints, allow anonymous access
      try {
        req.auth = await processJwt(originalAuthHeader, true); // true = allow anonymous
        
        // Check if we have a valid authenticated user with a properly signed token
        if (req.auth && req.auth.userId !== "anonymous") {
          // Check if the token is unsigned
          if (token) {
            try {
              // Decode the token header
              const parts = token.split('.');
              if (parts.length >= 2) {
                const headerStr = Buffer.from(parts[0], 'base64').toString();
                const header = JSON.parse(headerStr);
                
                // Check if algorithm is 'none' or missing
                if (header.alg === 'none' || !header.alg || !header.kid) {
                  isUnsignedToken = true;
                  l.debug("Token is unsigned, limiting available tools");
                }
              }
            } catch (error) {
              l.error(`Error checking token signature: ${error.message}`);
              isUnsignedToken = true;
            }
          } else {
            isUnsignedToken = true;
            l.debug("No valid token found, limiting available tools");
          }
          
          isAuthenticated = !isUnsignedToken;
          l.debug(`User authentication status: ${isAuthenticated ? "authenticated" : "unauthenticated"}`);
        } else {
          l.debug("Anonymous access for public endpoint");
        }
      } catch (error) {
        l.error(`Error processing JWT for public endpoint: ${error.message}`);
        // For public endpoints, we'll continue even if there's an error
        req.auth = {
          user: {},
          token: "",
          userId: "anonymous",
          tenantId: "",
          tenantTier: "basic",
        };
        isAuthenticated = false;
      }
    } else {
      // For all other requests, require full authentication
      req.auth = await processJwt(originalAuthHeader, false); // false = require authentication
      isAuthenticated = true;
    }

    // Create new instances of MCP Server and Transport for each incoming request
    const newMcpServer = mcpServer.create(isAuthenticated);
    
    // Create a custom context object that includes the authorization header
    const customContext = {
      authInfo: {
        token: token
      },
      auth: req.auth
    };
    
    const transport = new StreamableHTTPServerTransport({
      // This is a stateless MCP server, so we don't need to keep track of sessions
      sessionIdGenerator: undefined,
      // Pass the custom context to the transport
      extraContext: customContext
    });

    // Store the original authorization header in the request object
    req.originalAuthHeader = originalAuthHeader;

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
