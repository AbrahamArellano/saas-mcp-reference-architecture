import jwt from "jsonwebtoken";
import jwksClient from "jwks-rsa";
import log4js from "log4js";

const l = log4js.getLogger();

// Cache for JWKS client to avoid recreating it
let jwksClientInstance = null;

/**
 * Initialize JWKS client for Cognito JWT verification
 */
function getJwksClient() {
  if (!jwksClientInstance) {
    const userPoolId = process.env.COGNITO_USER_POOL_ID;
    const region = process.env.AWS_REGION || 'us-east-1';
    
    if (!userPoolId) {
      throw new Error('COGNITO_USER_POOL_ID environment variable is required');
    }

    const jwksUri = `https://cognito-idp.${region}.amazonaws.com/${userPoolId}/.well-known/jwks.json`;
    
    l.debug(`Initializing JWKS client with URI: ${jwksUri}`);
    
    jwksClientInstance = jwksClient({
      jwksUri: jwksUri,
      requestHeaders: {}, // Optional
      timeout: 30000, // Defaults to 30s
      cache: true,
      cacheMaxEntries: 5, // Default value
      cacheMaxAge: 600000, // Default value (10 minutes)
    });
  }
  
  return jwksClientInstance;
}

/**
 * Get signing key for JWT verification
 */
function getKey(header, callback) {
  const client = getJwksClient();
  
  client.getSigningKey(header.kid, (err, key) => {
    if (err) {
      l.error('Error getting signing key:', err);
      callback(err);
      return;
    }
    
    const signingKey = key.publicKey || key.rsaPublicKey;
    callback(null, signingKey);
  });
}

/**
 * Verify JWT token with Cognito
 */
export function verifyToken(token) {
  return new Promise((resolve, reject) => {
    const clientId = process.env.COGNITO_CLIENT_ID;
    const userPoolId = process.env.COGNITO_USER_POOL_ID;
    const region = process.env.AWS_REGION || 'us-east-1';
    
    if (!clientId || !userPoolId) {
      reject(new Error('COGNITO_CLIENT_ID and COGNITO_USER_POOL_ID environment variables are required'));
      return;
    }

    const issuer = `https://cognito-idp.${region}.amazonaws.com/${userPoolId}`;
    
    jwt.verify(token, getKey, {
      audience: clientId,
      issuer: issuer,
      algorithms: ['RS256']
    }, (err, decoded) => {
      if (err) {
        l.error('JWT verification failed:', err.message);
        reject(err);
      } else {
        l.debug('JWT verification successful');
        resolve(decoded);
      }
    });
  });
}

/**
 * Decode JWT without verification (for development/testing and public endpoints)
 */
export function decodeTokenUnsafe(token) {
  l.debug('Using JWT decode without verification');
  return jwt.decode(token);
}

/**
 * Create a default auth object for anonymous users
 */
export function createAnonymousAuth() {
  return {
    user: {},
    token: "",
    userId: "anonymous",
    tenantId: "",
    tenantTier: "basic",
  };
}

/**
 * Extract token from authorization header
 */
export function extractToken(authHeader) {
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

/**
 * Check if a token is using the 'none' algorithm or is otherwise unsigned
 */
export function isUnsignedToken(token) {
  try {
    // Check for empty or invalid token
    if (!token || token.trim() === "") {
      return true;
    }
    
    // Decode the token header
    const parts = token.split('.');
    if (parts.length < 2) return true; // Malformed token
    
    const headerStr = Buffer.from(parts[0], 'base64').toString();
    const header = JSON.parse(headerStr);
    
    // Check if algorithm is 'none' or missing
    return header.alg === 'none' || !header.alg || !header.kid;
  } catch (error) {
    l.error(`Error checking token signature: ${error.message}`);
    return true; // Assume unsigned if we can't parse it
  }
}

/**
 * Main function to handle JWT processing
 * Will use verification if Cognito is configured, otherwise falls back to unsafe decode
 */
export async function processJwt(bearer, allowAnonymous = false) {
  l.debug("Processing Authorization header: " + (bearer ? bearer.substring(0, 20) + "..." : "undefined"));

  // Extract token from authorization header
  const token = extractToken(bearer);
  
  // Check if token is missing or empty
  if (!token) {
    if (allowAnonymous) {
      l.debug("No valid token found, but anonymous access is allowed");
      return createAnonymousAuth();
    }
    l.error("No valid token found");
    throw new Error("Authentication failed: No authorization token provided. Please include a valid Bearer token in the Authorization header.");
  }
  
  l.debug("Token extracted: " + token.substring(0, 20) + "...");

  // Check if the token is unsigned or uses the 'none' algorithm
  const tokenIsUnsigned = isUnsignedToken(token);
  if (tokenIsUnsigned) {
    l.debug("Token is unsigned or uses 'none' algorithm");
    
    if (!allowAnonymous) {
      l.error("Unsigned tokens are not allowed for protected endpoints");
      throw new Error("Authentication failed: Unsigned tokens are not accepted for this endpoint.");
    }
    
    // For public endpoints, we'll accept unsigned tokens but decode them without verification
    const decodedData = decodeTokenUnsafe(token);
    if (!decodedData) {
      l.debug("Failed to decode unsigned token, returning anonymous auth");
      return createAnonymousAuth();
    }
    
    l.debug("Successfully decoded unsigned token");
    return {
      user: decodedData,
      token: token,
      userId: decodedData.sub || "anonymous",
      tenantId: decodedData["custom:tenantId"] || decodedData.tenantId || "",
      tenantTier: decodedData["custom:tenantTier"] || decodedData.tenantTier || "basic",
    };
  }

  let userData;
  
  // Try to verify with Cognito if configured
  if (process.env.COGNITO_USER_POOL_ID) {
    try {
      userData = await verifyToken(token);
      l.info('JWT verified successfully with Cognito');
    } catch (error) {
      l.error(`Cognito JWT verification failed: ${error.message}`);
      
      if (allowAnonymous) {
        l.debug("Token verification failed, but anonymous access is allowed. Trying to decode token without verification.");
        userData = decodeTokenUnsafe(token);
        
        if (!userData) {
          l.debug("Token decode failed, returning anonymous auth");
          return createAnonymousAuth();
        }
      } else {
        // Create more user-friendly error messages based on the error type
        if (error.name === 'TokenExpiredError') {
          throw new Error('Authentication failed: Your token has expired. Please log in again.');
        } else if (error.name === 'JsonWebTokenError') {
          throw new Error('Authentication failed: Invalid token format or signature.');
        } else if (error.name === 'NotBeforeError') {
          throw new Error('Authentication failed: Token not yet valid.');
        } else if (error.message.includes('signing key')) {
          throw new Error('Authentication failed: Token was not issued by the expected authority.');
        } else {
          throw new Error('Authentication failed: Token verification error.');
        }
      }
    }
  } else {
    // Fallback to unsafe decode for development
    l.warn('COGNITO_USER_POOL_ID not set - using unsafe JWT decode');
    userData = decodeTokenUnsafe(token);
    
    if (!userData && !allowAnonymous) {
      throw new Error('Authentication failed: Invalid token format.');
    } else if (!userData) {
      return createAnonymousAuth();
    }
  }

  // Log user information
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
    userId: userData.sub || "anonymous",
    tenantId: userData["custom:tenantId"] || userData.tenantId || "",
    tenantTier: userData["custom:tenantTier"] || userData.tenantTier || "basic",
  };
}
