import fetch from 'node-fetch';

async function testWhoami() {
  const MCP_URL = process.env.MCP_URL || 'http://localhost:3000/mcp';
  
  console.log('Testing whoami tool without authentication...');
  
  // Test without authentication
  const unauthResponse = await fetch(MCP_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json, text/event-stream'
    },
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: 1,
      method: 'whoami'
    })
  });
  
  const unauthResult = await unauthResponse.json();
  console.log('Unauthenticated result:', JSON.stringify(unauthResult, null, 2));
  
  // Test with authentication if token is provided
  if (process.env.AUTH_TOKEN) {
    console.log('\nTesting whoami tool with authentication...');
    
    const authResponse = await fetch(MCP_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
        'Authorization': `Bearer ${process.env.AUTH_TOKEN}`
      },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 2,
        method: 'whoami'
      })
    });
    
    const authResult = await authResponse.json();
    console.log('Authenticated result:', JSON.stringify(authResult, null, 2));
  } else {
    console.log('\nSkipping authenticated test (no AUTH_TOKEN provided)');
  }
}

testWhoami().catch(console.error);
