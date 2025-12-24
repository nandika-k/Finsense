# Finsense
A personalized financial research assistant.

Finsense helps users make sense of market uncertainty by combining live market data, news events, and risk analysis. Instead of giving investment advice, it highlights what areas of the market are worth researching based on current conditions and a user’s preferences.

The system is built around AI agents that reason about information, supported by modular MCP servers that provide reliable data and analytics.

## AI Agents
### Coordinator Agent
The main, user-facing agent. It interprets the user’s goals, risk tolerance, and ethical boundaries, decides what type of analysis is needed, and combines insights from specialized agents into a clear, human-readable summary.

### Macro & Events Agent
Focuses on understanding what is happening in the world. It analyzes news headlines to identify macroeconomic and geopolitical risks and explains how these events may affect different market sectors.

### Market & Risk Agent
Focuses on quantitative market behavior. It evaluates sector and stock performance, correlations, and volatility to identify patterns that may indicate elevated risk or emerging trends.

## MCP Servers
### mcp_market
Processes market data to understand sector and stock performance. It provides historical returns, price summaries, and basic trend information that ground the system’s insights in real market behavior.

### mcp_news
Retrieves relevant news headlines and extracts risk-related themes from unstructured text. It maps these themes to affected sectors, helping translate real-world events into market context.

### mcp_risk
Analyzes inter-sector relationships, correlations, and volatility. It helps identify how risk can spread across the market and highlights areas that may be more sensitive during periods of stress.