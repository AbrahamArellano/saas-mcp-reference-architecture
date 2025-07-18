import log4js from "log4js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import mcpServer from "./mcp-server.js";
import mcpErrors from "./mcp-errors.js";
import jwt from "jsonwebtoken";

const MCP_PATH = "/mcp";

const l = log4js.getLogger();

const bootstrap = async (app) => {
  app.post(MCP_PATH, postRequestHandler);
  app.get(MCP_PATH, sessionRequestHandler);
  app.delete(MCP_PATH, sessionRequestHandler);
};

const decodeJwt = (bearer) => {
  l.debug("Authorization header: " + bearer);

  // Extract JWT token from Authorization header
  if (!(bearer && bearer.startsWith("Bearer "))) {
    throw Error("Unauthorized!");
  }

  const token = bearer.split(" ")[1];
  l.debug("Token extracted: " + token.substring(0, 20) + "...");

  const userData = jwt.decode(token);

  if (userData) {
    console.log("\n========== JWT TOKEN PAYLOAD ==========");
    console.log(`Subject (sub): ${userData.sub || "Not provided"}`);
    console.log(
      `User Name: ${
        userData.name ||
        userData.preferred_username ||
        userData["cognito:username"] ||
        "Not provided"
      }`
    );
    console.log(`Email: ${userData.email || "Not provided"}`);

    // Handle roles/groups which could be in different formats
    if (userData.roles || userData["cognito:groups"] || userData.groups) {
      const roles =
        userData.roles || userData["cognito:groups"] || userData.groups || [];
      console.log("Roles/Groups:");
      if (Array.isArray(roles)) {
        roles.forEach((role) => console.log(`  - ${role}`));
      } else {
        console.log(`  - ${roles}`);
      }
    }

    // Handle custom claims
    console.log("\nAll Claims:");
    Object.keys(userData).forEach((key) => {
      const value = userData[key];
      if (typeof value === "object" && value !== null) {
        console.log(`${key}: ${JSON.stringify(value)}`);
      } else {
        console.log(`${key}: ${value}`);
      }
    });
    console.log("=======================================\n");

    return {
      user: userData,
      token: token,
      userId: userData.sub,
      tenantId: userData["custom:tenantId"] || "",
      tenantTier: userData["custom:tenantTier"] || "basic",
    };
  }
};

const postRequestHandler = async (req, res) => {
  try {
    req.auth = decodeJwt(req.get("Authorization"));

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
    l.error(`Error handling MCP request ${err}`);
    if (!res.headersSent) {
      res.status(500).json(mcpErrors.internalServerError);
    }
  }
};

const sessionRequestHandler = async (req, res) => {
  res.status(405).set("Allow", "POST").json(mcpErrors.methodNotAllowed);
};

export default {
  bootstrap,
};
