// prompts.js
const promptTemplates = {
  flight_search: {
    name: "flight_search",
    description: "Guide for searching flights with preferences",
    arguments: [
      {
        name: "origin",
        description: "Departure city or airport code",
        required: true
      },
      {
        name: "destination", 
        description: "Arrival city or airport code",
        required: true
      },
      {
        name: "date",
        description: "Travel date (YYYY-MM-DD)",
        required: true
      },
      {
        name: "preferences",
        description: "Travel preferences (e.g., nonstop, morning)",
        required: false
      }
    ],
    template: `I'll help you search for flights from {{origin}} to {{destination}} on {{date}}.

Let me search for available options using the flight search tool.

<use_tool>
find_flights with origin: "{{origin}}", destination: "{{destination}}", departure: "{{date}}"
</use_tool>

Based on your preferences: {{preferences}}

I'll analyze the results and highlight:
1. Best value options
2. Most convenient times
3. Loyalty program benefits
4. Available seat classes

Would you like me to search for return flights as well?`
  },
  
  booking_flow: {
    name: "booking_flow",
    description: "Complete travel booking workflow with policy compliance",
    arguments: [],
    template: `I'll guide you through the complete travel booking process.

First, let's check your current bookings to avoid conflicts:
<use_tool>list_bookings</use_tool>

Next, I'll need to know:
1. Your travel dates and destination
2. Whether you need flights, hotels, or both
3. Your budget preferences
4. Any loyalty programs you want to use

I'll also check the company travel policy:
<use_resource>travelpolicy://company/policy</use_resource>

Once we have your preferences, I'll:
- Search for the best options
- Compare prices and benefits
- Check policy compliance
- Handle the booking

What type of trip are you planning?`
  },
  
  loyalty_overview: {
    name: "loyalty_overview",
    description: "Check all loyalty program statuses",
    arguments: [],
    template: `Let me check all your loyalty program statuses.

<use_tool>loyalty_info</use_tool>

I'll provide you with:
- Current points/miles balance for each program
- Your tier status and benefits
- Points needed for next tier
- Recommendations for maximizing rewards

This will help you choose the best airline or hotel for earning and redeeming points.`
  },
  
  policy_compliant_booking: {
    name: "policy_compliant_booking",
    description: "Book travel following company policy",
    arguments: [
      {
        name: "trip_type",
        description: "Type of trip: business or personal",
        required: true
      },
      {
        name: "budget",
        description: "Maximum budget for the trip",
        required: false
      }
    ],
    template: `I'll help you book {{trip_type}} travel while ensuring compliance with company policy.

First, let me check the travel policy for {{trip_type}} trips:
<use_resource>travelpolicy://tenant</use_resource>

Key policy points to consider:
- Approved vendors and booking classes
- Per diem limits and expense guidelines
- Advance booking requirements
- Required approvals

{{budget_text}}I'll ensure all bookings comply with these guidelines.

What are your travel dates and destination?`
  }
};

function processPromptTemplate(template, args = {}) {
  // Handle special cases
  const processedArgs = { ...args };
  
  // Add default for preferences
  if (template.name === 'flight_search' && !processedArgs.preferences) {
    processedArgs.preferences = 'any flight is fine';
  }
  
  // Add budget text for policy_compliant_booking
  if (template.name === 'policy_compliant_booking') {
    processedArgs.budget_text = processedArgs.budget 
      ? `Your specified budget is ${processedArgs.budget}. ` 
      : '';
  }
  
  // Replace template variables
  return template.template.replace(/\{\{(\w+)\}\}/g, (match, key) => {
    return processedArgs[key] || '';
  });
}

export function registerPromptHandlers(mcpServer) {
  // Check if the server has a prompt method
  if (typeof mcpServer.prompt === 'function') {
    // Register each prompt
    Object.values(promptTemplates).forEach(promptDef => {
      mcpServer.prompt(
        promptDef.name,
        promptDef.description,
        promptDef.arguments,
        async (args) => {
          const processedText = processPromptTemplate(promptDef, args);
          return {
            messages: [{
              role: "user",
              content: {
                type: "text",
                text: processedText
              }
            }]
          };
        }
      );
    });
  } else {
    console.error("MCP Server doesn't support prompt registration with .prompt() method");
    
    // Alternative: Try registering as a tool that returns prompt text
    mcpServer.tool(
      "get_prompt",
      "Get a prompt template for various workflows",
      {
        name: z.enum(['flight_search', 'booking_flow', 'loyalty_overview', 'policy_compliant_booking']),
        arguments: z.optional(z.record(z.string()))
      },
      async ({ name, arguments: args }) => {
        const promptDef = promptTemplates[name];
        if (!promptDef) {
          return { error: `Unknown prompt: ${name}` };
        }
        
        const processedText = processPromptTemplate(promptDef, args);
        return {
          content: [{
            type: "text",
            text: processedText
          }]
        };
      }
    );
    
    mcpServer.tool(
      "list_prompts",
      "List all available prompt templates",
      {},
      async () => {
        return {
          content: [{
            type: "text",
            text: JSON.stringify(
              Object.values(promptTemplates).map(p => ({
                name: p.name,
                description: p.description,
                arguments: p.arguments
              })),
              null,
              2
            )
          }]
        };
      }
    );
  }
}