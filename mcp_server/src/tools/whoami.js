import jwt from "jsonwebtoken";
import jwksClient from "jwks-rsa";
import log4js from "log4js";

const l = log4js.getLogger();

// Cache for JWKS client to avoid recreating it
let jwksClientInstance = null;

/**
 * Get JWKS client for Cognito JWT verification
 */
function getJwksClient() {
  if (!jwksClientInstance && process.env.COGNITO_USER_POOL_ID) {
    const userPoolId = process.env.COGNITO_USER_POOL_ID;
    const region = process.env.AWS_REGION || 'us-east-1';
    const jwksUri = `https://cognito-idp.${region}.amazonaws.com/${userPoolId}/.well-known/jwks.json`;
    
    l.debug(`Initializing JWKS client with URI: ${jwksUri}`);
    
    jwksClientInstance = jwksClient({
      jwksUri: jwksUri,
      requestHeaders: {},
      timeout: 30000,
      cache: true,
      cacheMaxEntries: 5,
      cacheMaxAge: 600000,
    });
  }
  
  return jwksClientInstance;
}

/**
 * Verify JWT token with Cognito
 */
async function verifyToken(token) {
  return new Promise((resolve, reject) => {
    try {
      // Check for empty or invalid token
      if (!token || token.trim() === "") {
        return resolve({
          verified: false, 
          payload: null,
          reason: "Empty token provided"
        });
      }
      
      // First decode the token without verification to get the header
      const decodedHeader = jwt.decode(token, { complete: true });
      
      if (!decodedHeader) {
        return resolve({
          verified: false, 
          payload: null,
          reason: "Invalid token format"
        });
      }
      
      const kid = decodedHeader.header.kid;
      const client = getJwksClient();
      
      if (!client) {
        // If no JWKS client (no Cognito config), just decode without verification
        const decoded = jwt.decode(token);
        return resolve({ 
          verified: false, 
          payload: decoded,
          reason: "COGNITO_USER_POOL_ID not configured"
        });
      }
      
      client.getSigningKey(kid, (err, key) => {
        if (err) {
          return resolve({ 
            verified: false, 
            payload: jwt.decode(token),
            reason: `Error getting signing key: ${err.message}`
          });
        }
        
        const signingKey = key.publicKey || key.rsaPublicKey;
        const clientId = process.env.COGNITO_CLIENT_ID;
        const userPoolId = process.env.COGNITO_USER_POOL_ID;
        const region = process.env.AWS_REGION || 'us-east-1';
        const issuer = `https://cognito-idp.${region}.amazonaws.com/${userPoolId}`;
        
        jwt.verify(token, signingKey, {
          audience: clientId,
          issuer: issuer,
          algorithms: ['RS256']
        }, (verifyErr, decoded) => {
          if (verifyErr) {
            return resolve({ 
              verified: false, 
              payload: jwt.decode(token),
              reason: verifyErr.message
            });
          }
          
          resolve({ 
            verified: true, 
            payload: decoded,
            reason: "Token signature verified"
          });
        });
      });
    } catch (error) {
      resolve({ 
        verified: false, 
        payload: null,
        reason: `Error processing token: ${error.message}`
      });
    }
  });
}

/**
 * Check if a token is using the 'none' algorithm or is otherwise unsigned
 */
function isUnsignedToken(token) {
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

/**
 * whoami tool implementation
 * Returns information about the current user based on their JWT token
 */
export default async function whoami(params, context) {
  try {
    // Log the context to help debug
    l.debug(`whoami tool called with params: ${JSON.stringify(params || {})}`);
    l.debug(`whoami tool context keys: ${context ? Object.keys(context).join(', ') : 'undefined'}`);
    
    // Try to get the token from various sources
    let token = null;
    
    // 1. Try to get it from the context.request.headers
    if (context && context.request && context.request.headers && context.request.headers.authorization) {
      token = extractToken(context.request.headers.authorization);
      if (token) {
        l.debug('Found token in context.request.headers.authorization');
      }
    }
    
    // 2. Try to get it from the context.authInfo
    if (!token && context && context.authInfo && context.authInfo.token) {
      token = context.authInfo.token;
      l.debug('Found token in context.authInfo.token');
    }
    
    // 3. Try to get it from the context.auth
    if (!token && context && context.auth && context.auth.token) {
      token = context.auth.token;
      l.debug('Found token in context.auth.token');
    }
    
    // 4. Try to get it from the params (in case it was passed as a parameter)
    if (!token && params && params.token) {
      token = params.token;
      l.debug('Found token in params.token');
    }
    
    // 5. Try to get it from the global variable (set in transport.js)
    if (!token && global.lastAuthHeader) {
      token = extractToken(global.lastAuthHeader);
      if (token) {
        l.debug('Found token in global.lastAuthHeader');
      }
    }
    
    // Log whether we found a token
    if (token) {
      l.debug(`Found token: ${token.substring(0, 20)}...`);
    } else {
      l.debug('No token found or token is empty');
    }
    
    // Default response for unauthenticated users
    let result = {
      authenticated: false,
      message: "No authentication token provided",
      userInfo: null,
      tokenInfo: null,
      environment: {
        cognitoConfigured: !!process.env.COGNITO_USER_POOL_ID,
        region: process.env.AWS_REGION || 'us-east-1'
      }
    };
    
    if (token) {
      // Check if the token is unsigned
      const tokenIsUnsigned = isUnsignedToken(token);
      
      // Attempt to verify and decode the token
      const tokenResult = await verifyToken(token);
      
      result = {
        authenticated: tokenResult.verified && !tokenIsUnsigned,
        message: tokenIsUnsigned ? "Token is unsigned" : tokenResult.reason,
        userInfo: tokenResult.payload ? {
          username: tokenResult.payload.username || tokenResult.payload["cognito:username"] || tokenResult.payload.sub,
          email: tokenResult.payload.email,
          tenantId: tokenResult.payload["custom:tenantId"] || tokenResult.payload.tenantId,
          tenantTier: tokenResult.payload["custom:tenantTier"] || tokenResult.payload.tenantTier
        } : null,
        tokenInfo: {
          issuer: tokenResult.payload?.iss,
          audience: tokenResult.payload?.aud,
          expiration: tokenResult.payload?.exp ? new Date(tokenResult.payload.exp * 1000).toISOString() : null,
          issuedAt: tokenResult.payload?.iat ? new Date(tokenResult.payload.iat * 1000).toISOString() : null,
          tokenUse: tokenResult.payload?.token_use,
          isUnsigned: tokenIsUnsigned
        },
        environment: {
          cognitoConfigured: !!process.env.COGNITO_USER_POOL_ID,
          region: process.env.AWS_REGION || 'us-east-1'
        }
      };
    }
    
    // Return in the format expected by the MCP SDK
    return {
      isError: false,
      content: [
        {
          type: "text",
          text: JSON.stringify(result)
        }
      ]
    };
  } catch (error) {
    l.error(`Error in whoami tool: ${error.message}`);
    return {
      isError: true,
      content: [
        {
          type: "text",
          text: `Error processing request: ${error.message}`
        }
      ]
    };
  }
}
