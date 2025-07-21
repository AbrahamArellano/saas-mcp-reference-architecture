#!/usr/bin/env python3
"""
Cognito Authentication Helper Script

This script handles AWS Cognito authentication, including SECRET_HASH calculation,
and saves the resulting tokens to a temporary file.

Usage:
    python cognito_auth.py --client-id CLIENT_ID --username USERNAME --password PASSWORD 
                          [--client-secret CLIENT_SECRET] [--region REGION] 
                          [--output-file OUTPUT_FILE]
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import tempfile
from typing import Dict, Optional

import boto3
from botocore.exceptions import ClientError


def calculate_secret_hash(username: str, client_id: str, client_secret: str) -> str:
    """
    Calculate the SECRET_HASH value required for Cognito authentication when a client secret is used.
    
    Args:
        username: The username for authentication
        client_id: The Cognito app client ID
        client_secret: The Cognito app client secret
        
    Returns:
        The calculated SECRET_HASH as a base64-encoded string
    """
    message = username + client_id
    dig = hmac.new(
        key=client_secret.encode('utf-8'),
        msg=message.encode('utf-8'),
        digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(dig).decode()


def authenticate_cognito(
    client_id: str,
    username: str,
    password: str,
    client_secret: Optional[str] = None,
    region: str = 'us-east-1'
) -> Dict:
    """
    Authenticate with AWS Cognito using USER_PASSWORD_AUTH flow.
    
    Args:
        client_id: The Cognito app client ID
        username: The username for authentication
        password: The password for authentication
        client_secret: The Cognito app client secret (optional)
        region: The AWS region where the Cognito user pool is located
        
    Returns:
        Dict containing authentication result with tokens
        
    Raises:
        Exception: If authentication fails
    """
    cognito_client = boto3.client('cognito-idp', region_name=region)
    
    auth_params = {
        'USERNAME': username,
        'PASSWORD': password
    }
    
    # Add SECRET_HASH if client_secret is provided
    if client_secret:
        auth_params['SECRET_HASH'] = calculate_secret_hash(username, client_id, client_secret)
    
    try:
        response = cognito_client.initiate_auth(
            ClientId=client_id,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters=auth_params
        )
        return response
    except ClientError as e:
        print(f"Authentication error: {e}", file=sys.stderr)
        if 'NotAuthorizedException' in str(e) and 'SECRET_HASH' in str(e) and not client_secret:
            print("\nERROR: This Cognito client requires a client secret.", file=sys.stderr)
            print("Please provide the --client-secret parameter and try again.", file=sys.stderr)
        raise


def save_tokens_to_file(auth_result: Dict, output_file: Optional[str] = None) -> str:
    """
    Save authentication tokens to a file.
    
    Args:
        auth_result: The authentication result containing tokens
        output_file: Path to the output file (optional)
        
    Returns:
        Path to the file where tokens were saved
    """
    if not output_file:
        # Create a temporary file if no output file is specified
        fd, output_file = tempfile.mkstemp(prefix='cognito_tokens_', suffix='.json')
        os.close(fd)
    
    # Extract relevant token information
    tokens = {
        'id_token': auth_result.get('AuthenticationResult', {}).get('IdToken'),
        'access_token': auth_result.get('AuthenticationResult', {}).get('AccessToken'),
        'refresh_token': auth_result.get('AuthenticationResult', {}).get('RefreshToken'),
        'token_type': auth_result.get('AuthenticationResult', {}).get('TokenType'),
        'expires_in': auth_result.get('AuthenticationResult', {}).get('ExpiresIn')
    }
    
    with open(output_file, 'w') as f:
        json.dump(tokens, f, indent=2)
    
    return output_file


def main():
    """Main function to parse arguments and run the authentication process."""
    parser = argparse.ArgumentParser(description='AWS Cognito Authentication Helper')
    parser.add_argument('--client-id', required=True, help='Cognito app client ID')
    parser.add_argument('--username', required=True, help='Username for authentication')
    parser.add_argument('--password', required=True, help='Password for authentication')
    parser.add_argument('--client-secret', help='Cognito app client secret (if required)')
    parser.add_argument('--region', default='us-east-1', help='AWS region (default: us-east-1)')
    parser.add_argument('--output-file', help='Path to save the tokens (default: temporary file)')
    
    args = parser.parse_args()
    
    try:
        # Authenticate with Cognito
        auth_result = authenticate_cognito(
            client_id=args.client_id,
            username=args.username,
            password=args.password,
            client_secret=args.client_secret,
            region=args.region
        )
        
        # Save tokens to file
        output_file = save_tokens_to_file(auth_result, args.output_file)
        
        print(f"Authentication successful!")
        print(f"Tokens saved to: {output_file}")
        
        # Print the ID token for immediate use
        id_token = auth_result.get('AuthenticationResult', {}).get('IdToken')
        if id_token:
            print("\nID Token (for authorization header):")
            print(f"Bearer {id_token}")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
