import jwt from "jsonwebtoken";
import fs from "fs";
import crypto from "crypto";
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

/**
 * Create a test JWT token that mimics Cognito's format
 * This is for testing purposes only - in production, tokens should come from Cognito
 * 
 * Usage:
 * node createCognitoToken.js [username]
 * 
 * If username is provided, the script will attempt to retrieve user info from Cognito
 * Otherwise, it will use default test values
 */

// Get username from command line arguments
const username = process.argv[2];

// Generate a test RSA key pair for signing (in production, Cognito manages this)
const { privateKey, publicKey } = crypto.generateKeyPairSync('rsa', {
  modulusLength: 2048,
  publicKeyEncoding: {
    type: 'spki',
    format: 'pem'
  },
  privateKeyEncoding: {
    type: 'pkcs8',
    format: 'pem'
  }
});

// Save the public key for verification (in production, this comes from Cognito's JWKS endpoint)
fs.writeFileSync('./test-public-key.pem', publicKey);
console.log('Test public key saved to test-public-key.pem');

const now = Math.floor(Date.now() / 1000);

// Function to get user info from Cognito
async function getUserInfoFromCognito(username) {
  try {
    const userPoolId = process.env.COGNITO_USER_POOL_ID;
    if (!userPoolId) {
      throw new Error("COGNITO_USER_POOL_ID environment variable is required");
    }

    console.log(`Retrieving user information for ${username} from Cognito User Pool ${userPoolId}...`);
    
    const { stdout } = await execAsync(`aws cognito-idp admin-get-user --user-pool-id ${userPoolId} --username ${username}`);
    const userInfo = JSON.parse(stdout);
    
    console.log(`Successfully retrieved user information for ${username}`);
    
    // Extract user attributes
    const attributes = {};
    userInfo.UserAttributes.forEach(attr => {
      attributes[attr.Name] = attr.Value;
    });
    
    return {
      sub: userInfo.Username,
      email: attributes.email || "no-email@example.com",
      email_verified: attributes.email_verified === "true",
      name: attributes.name || `${attributes.given_name || ""} ${attributes.family_name || ""}`.trim() || username,
      given_name: attributes.given_name || "",
      family_name: attributes.family_name || "",
      "custom:tenantId": attributes["custom:tenantId"] || "",
      "custom:tenantTier": attributes["custom:tenantTier"] || ""
    };
  } catch (error) {
    console.error(`Error retrieving user info from Cognito: ${error.message}`);
    console.error("Using default test values instead");
    return null;
  }
}

// Main function to create the token
async function createToken() {
  // Default payload
  let userInfo = {
    sub: "user1",
    email: "test@example.com",
    email_verified: true,
    name: "Test User1",
    given_name: "Test",
    family_name: "User1",
    "custom:tenantId": "ABC123",
    "custom:tenantTier": "premium"
  };
  
  // If username is provided, try to get user info from Cognito
  if (username) {
    const cognitoUserInfo = await getUserInfoFromCognito(username);
    if (cognitoUserInfo) {
      userInfo = cognitoUserInfo;
    }
  }
  
  // Create a token that matches Cognito's format
  const payload = {
    sub: userInfo.sub,
    aud: process.env.COGNITO_CLIENT_ID || "test-client-id",
    iss: process.env.COGNITO_USER_POOL_ID ? 
      `https://cognito-idp.${process.env.AWS_REGION || 'us-east-1'}.amazonaws.com/${process.env.COGNITO_USER_POOL_ID}` :
      "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TEST123456",
    iat: now,
    exp: now + 3600, // 1 hour
    auth_time: now,
    token_use: "access",
    scope: "aws.cognito.signin.user.admin",
    username: userInfo.sub,
    
    // Standard claims
    email: userInfo.email,
    email_verified: userInfo.email_verified,
    name: userInfo.name,
    given_name: userInfo.given_name,
    family_name: userInfo.family_name,
    
    // Custom attributes (Cognito prefixes with custom:)
    "custom:tenantId": userInfo["custom:tenantId"],
    "custom:tenantTier": userInfo["custom:tenantTier"],
    
    // Cognito groups (if any)
    "cognito:groups": ["users", "admin"]
  };

  const header = {
    kid: "test-key-id",
    alg: "RS256",
    typ: "JWT"
  };

  // Sign the token
  const token = jwt.sign(payload, privateKey, { 
    algorithm: 'RS256',
    header: header
  });

  console.log('\n========== COGNITO-COMPATIBLE TEST TOKEN ==========');
  console.log(token);
  console.log('\n========== TOKEN PAYLOAD ==========');
  console.log(JSON.stringify(payload, null, 2));
  console.log('\n========== USAGE ==========');
  console.log('Use this token in your Authorization header:');
  console.log(`Authorization: Bearer ${token}`);
  console.log('\n========== NOTES ==========');
  console.log('- This token is signed with a test RSA key');
  console.log('- In production, use actual Cognito-issued tokens');
  console.log('- The server will verify this token if COGNITO_USER_POOL_ID is not set');
  console.log('- For full Cognito verification, deploy the infrastructure first');

  // Also create a simple unsigned token for backward compatibility
  const unsignedPayload = {
    sub: userInfo.sub,
    name: userInfo.name,
    email: userInfo.email,
    roles: ["user", "admin"],
    permissions: ["read"],
    org: "tenant1",
    "custom:tenantId": userInfo["custom:tenantId"],
    iat: now,
    exp: now + 3600
  };

  const unsignedToken = jwt.sign(unsignedPayload, "", { algorithm: 'none' });

  console.log('\n========== UNSIGNED TOKEN (FALLBACK) ==========');
  console.log(unsignedToken);
  console.log('\nThis unsigned token can be used when COGNITO_USER_POOL_ID is not configured.');
}

// Run the main function
createToken().catch(error => {
  console.error(`Error creating token: ${error.message}`);
  process.exit(1);
});
