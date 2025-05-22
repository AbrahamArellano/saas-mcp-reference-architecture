import "./logging.js";
import log4js from "log4js";
import express from "express";
import metadata from "./metadata.js";
import transport from "./transport.js";
import cors from "cors";
import jwt from "jsonwebtoken";
import httpContext, {
  middleware as httpContextMiddleware,
} from "express-http-context";

await metadata.init();

const l = log4js.getLogger();
const PORT = 3000;

const app = express();
app.use(express.json());
app.use(
  cors({
    origin: "*",
    methods: ["GET", "POST", "DELETE", "UPDATE", "PUT", "PATCH"],
    allowedHeaders: ["Content-Type", "Authorization"],
  })
);
app.use(httpContextMiddleware);

app.use(async (req, res, next) => {
  try {
    l.debug("JWT middleware executing");
    // Get user from data on request
    const bearer = req.get("Authorization");
    l.debug("Authorization header: " + bearer);

    // Extract JWT token from Authorization header
    if (bearer && bearer.startsWith("Bearer ")) {
      const token = bearer.split(" ")[1];
      l.debug("Token extracted: " + token.substring(0, 20) + "...");

      // Decode JWT token (without verification)
      try {
        // Using the jwt library to decode the token
        const userData = jwt.decode(token);

        if (userData) {
          // Add decoded user data to the request-scoped context
          httpContext.set("user", userData);
          httpContext.set("token", token);

          httpContext.set("userId", userData.sub);
          httpContext.set("tenantId", userData["custom:tenantId"] || "");
          httpContext.set("tenantTier", userData["custom:tenantTier"] || "basic");

          // Print detailed JWT payload information to terminal
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
              userData.roles ||
              userData["cognito:groups"] ||
              userData.groups ||
              [];
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

          // Also log to the application logger
          l.info("JWT token decoded successfully with the following claims:");
        } else {
          l.warn("Invalid JWT token format");
          httpContext.set("user", bearer);
        }
      } catch (tokenErr) {
        l.error("Failed to decode JWT token", tokenErr);
        l.error(tokenErr);
        httpContext.set("user", bearer);
      }
    } else {
      l.debug("No Bearer token found");
      httpContext.set("user", bearer);
    }

    return next();
  } catch (err) {
    l.error("Error in JWT middleware:");
    l.error(err);
    return next(err);
  }
});

app.get("/health", (req, res) => {
  res.json(metadata.all);
});

app.use(async (req, res, next) => {
  l.debug(`> ${req.method} ${req.originalUrl}`);
  l.debug(req.body);
  // l.debug(req.headers);
  return next();
});

await transport.bootstrap(app);

await app.listen(PORT, () => {
  l.debug(metadata.all);
  l.debug(`listening on http://localhost:${PORT}`);
});
