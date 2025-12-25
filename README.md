# Finsense
A personalized financial research assistant.

Finsense helps users make sense of market uncertainty by combining live market data, news events, and risk analysis. Instead of giving investment advice, it highlights what areas of the market are worth researching based on current conditions and a user’s preferences.

The system is built around an AI agent that reasons about information, supported by modular MCP servers that provide reliable data and analytics.

## MCP Servers
### mcp_market
Processes market data to understand sector and stock performance. It provides historical returns, price summaries, and basic trend information that ground the system’s insights in real market behavior.

### mcp_news
Retrieves relevant news headlines and extracts risk-related themes from unstructured text. It maps these themes to affected sectors, helping translate real-world events into market context.

### mcp_risk
Analyzes inter-sector relationships, correlations, and volatility. It helps identify how risk can spread across the market and highlights areas that may be more sensitive during periods of stress.