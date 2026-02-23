# Finsense
A personalized financial research assistant.

Finsense helps users make sense of market uncertainty by combining live market data, news events, and risk analysis. Instead of giving investment advice, it highlights what areas of the market are worth researching based on current conditions and a user’s preferences.

The system is built around an AI agent that reasons about information, supported by modular MCP servers that provide reliable data and analytics.

Check it out: https://finsense-web.vercel.app/

## MCP Servers
### mcp_market
Processes market data to understand sector and stock performance. It provides historical returns, price summaries, and basic trend information that ground the system’s insights in real market behavior.

### mcp_news
Retrieves relevant news headlines and extracts risk-related themes from unstructured text. It maps these themes to affected sectors, helping translate real-world events into market context.

### mcp_risk

Analyzes inter-sector relationships, correlations, and volatility. It helps identify how risk can spread across the market and highlights areas that may be more sensitive during periods of stress.

## Auth0 Login & API Authentication

Finsense now supports Auth0-based authentication for protected API routes:

- `POST /api/chat`
- `POST /api/research`
- `GET /api/status/{session_id}`

### Backend env vars

Set these environment variables to enable token verification:

- `AUTH0_DOMAIN` (example: `your-tenant.us.auth0.com`)
- `AUTH0_AUDIENCE` (the API identifier configured in Auth0)

If these are not set, backend auth is disabled for local development.

### Frontend config

In [ui/index.html](ui/index.html), set `window.FINSENSE_AUTH0`:

- `domain`
- `clientId`
- `audience`

When set, the UI uses Auth0 Universal Login and sends `Authorization: Bearer <token>` on API calls.

### Tests

Run auth-focused tests:

- `C:/Users/nkarn/Code/Finsense/venv/Scripts/python.exe -m unittest tests/test_auth_api.py tests/test_auth_module.py`
