// generate-token.js
import jwt from "jsonwebtoken";

// Create payload with relevant user information
const payload = {
  sub: "user1",
  name: "Test User1",
  email: "test@example.com",
  roles: ["user", "admin"],
  permissions: ["read"],
  org: "tenant1",
  "custom:tenantId": "ABC123",
  iat: Math.floor(Date.now() / 1000),
  exp: Math.floor(Date.now() / 1000) + 60 * 60, // Token expires in 1 hour
};

// Generate a token - for testing purposes only
// In a real application, you would sign this with a secret
// But since our middleware only uses jwt.decode(), we can create a token with any algorithm
const header = {
  alg: "none",
  typ: "JWT",
};

// Create token parts
const encodedHeader = Buffer.from(JSON.stringify(header))
  .toString("base64")
  .replace(/=/g, "")
  .replace(/\+/g, "-")
  .replace(/\//g, "_");
const encodedPayload = Buffer.from(JSON.stringify(payload))
  .toString("base64")
  .replace(/=/g, "")
  .replace(/\+/g, "-")
  .replace(/\//g, "_");

// Create token without signature
const token = `${encodedHeader}.${encodedPayload}.`;

console.log("JWT Token (unsigned):");
console.log(token);
console.log("\nFor testing with curl:");
console.log(
  `curl -X GET http://localhost:3000/health -H "Authorization: Bearer ${token}"`
);

// Decode the token to verify contents
const decoded = jwt.decode(token);
console.log("\nDecoded Token:");
console.log(JSON.stringify(decoded, null, 2));
