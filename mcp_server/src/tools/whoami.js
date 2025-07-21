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
 * whoami tool implementation
 * Returns information about the current user based on their JWT token
 */
export default async function whoami(params, context) {
  try {
    const authHeader = context.request?.headers?.authorization;
    
    // Default response for unauthenticated users
    let result = {
      authenticated: false,
      message: "No authentication token provided",
      userInfo: null,
      tokenInfo: null
    };
    
    if (authHeader && authHeader.startsWith("Bearer ")) {
      const token = authHeader.split(" ")[1];
      
      // Attempt to verify and decode the token
      const tokenResult = await verifyToken(token);
      
      result = {
        authenticated: tokenResult.verified,
        message: tokenResult.reason,
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
          tokenUse: tokenResult.payload?.token_use
        }
      };
    }
    
    // Add server environment information
    result.environment = {
      cognitoConfigured: !!process.env.COGNITO_USER_POOL_ID,
      region: process.env.AWS_REGION || 'us-east-1'
    };
    
    return result;
  } catch (error) {
    l.error(`Error in whoami tool: ${error.message}`);
    return {
      authenticated: false,
      message: `Error processing request: ${error.message}`,
      userInfo: null,
      tokenInfo: null,
      error: true
    };
  }
}
