"""
FastAPI backend for Finsense web chatbot.
Provides REST API endpoints for conversation and research.
"""

import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Import Finsense components
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.agent import FinsenseCoordinator
from agent.conversational_agent import ConversationalAgent
from ui.chatbot import (
    INVESTMENT_GOALS, 
    AVAILABLE_SECTORS, 
    parse_initial_query,
    parse_sectors_with_llm,
    is_delegating_decision,
    suggest_sectors_from_goals,
    get_llm_client
)
from ui.summary_generator import (
    generate_sector_goal_summary,
    generate_risk_summary_with_citations,
    generate_stock_picks_summary
)
from backend.auth import get_current_user

load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Finsense API", version="1.0.0")

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session storage (in production, use Redis or database)
sessions: Dict[str, Dict[str, Any]] = {}
session_chat_agents: Dict[str, ConversationalAgent] = {}


# Request/Response Models
class ChatMessage(BaseModel):
    session_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    bot_message: str
    state: str
    data: Optional[Dict[str, Any]] = None
    needs_confirmation: bool = False
    options: Optional[List[str]] = None


class ResearchRequest(BaseModel):
    session_id: str


class ResearchResponse(BaseModel):
    session_id: str
    status: str
    progress: Optional[str] = None
    results: Optional[Dict[str, Any]] = None


# Helper Functions
def create_session() -> str:
    """Create a new session with initial state"""
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "state": "initial",
        "analysis_mode": "full_research",
        "preferences": {
            "goals": None,
            "sectors": None,
            "risk_tolerance": None
        },
        "conversation_history": [],
        "research_data": None,
        "created_at": datetime.now().isoformat()
    }
    return session_id


def get_or_create_conversational_agent(session_id: str) -> ConversationalAgent:
    """Get or create a session-scoped conversational agent."""
    agent = session_chat_agents.get(session_id)
    if agent is None:
        agent = ConversationalAgent()
        session_chat_agents[session_id] = agent
    return agent


def get_session(session_id: str) -> Dict[str, Any]:
    """Get session data or create new session"""
    if not session_id or session_id not in sessions:
        new_id = create_session()
        return sessions[new_id]
    return sessions[session_id]


def is_stock_focused_request(user_input: str) -> bool:
    """Heuristic to detect stock-picks-focused requests."""
    text = (user_input or "").strip().lower()
    if not text:
        return False

    stock_words = ["stock", "stocks", "share", "shares", "picks", "ideas"]
    report_words = ["report", "full research", "comprehensive", "deep dive", "analysis"]

    has_stock_word = any(word in text for word in stock_words)
    asks_for_report = any(word in text for word in report_words)
    return has_stock_word and not asks_for_report


async def get_llm_response(
    user_input: str,
    context: str,
    session: Dict[str, Any],
    session_id: str,
) -> Dict[str, Any]:
    """
    Process user input based on conversation state.
    Returns dict with: bot_message, new_state, data (parsed values)
    """
    state = session["state"]
    preferences = session["preferences"]
    llm_client = get_llm_client()

    # Conversational-first mode: users can ask direct questions naturally.
    # Switch to guided report mode only when explicitly requested.
    message_text = (user_input or "").strip()
    lowered = message_text.lower()
    
    # Only these explicit triggers enter guided mode
    guided_switches = {
        "/report",
        "/guided",
        "guided mode",
        "research mode",
        "full report",
        "run full analysis",
        "full analysis",
    }
    chat_switches = {"/chat", "chat mode", "conversational mode"}

    if lowered in chat_switches:
        session["state"] = "conversational"
        return {
            "bot_message": "Switched to conversational mode. Ask for stocks, headlines, market overview, sector risk, or full research anytime.",
            "state": "conversational",
            "data": {},
        }

    if lowered in guided_switches:
        session["state"] = "collecting_initial"
        session["analysis_mode"] = "full_research"
        preferences["goals"] = None
        preferences["sectors"] = None
        preferences["risk_tolerance"] = None
        return {
            "bot_message": "Switched to guided report mode.\n\n" + format_goals_question(),
            "state": "collecting_goals",
            "data": {},
        }

    # CONVERSATIONAL MODE: Route ALL messages through conversational agent
    # unless we're in the middle of the guided flow
    if state not in {"collecting_goals", "collecting_sectors", "collecting_risk", "confirming", "ready_to_research"}:
        if message_text:
            agent = get_or_create_conversational_agent(session_id)
            bot_message = await agent.process_message(message_text)
            return {
                "bot_message": bot_message,
                "state": "conversational",
                "data": {},
            }
        else:
            # Empty input - return welcome message
            return {
                "bot_message": get_welcome_message(),
                "state": "conversational",
                "data": {}
            }

    if is_stock_focused_request(user_input):
        session["analysis_mode"] = "stock_picks"
    
    # GUIDED MODE: Only reach here if in middle of guided flow
    # Initial state - welcome message (legacy fallback)
    if state == "initial":
        # Try to parse everything from initial input
        if user_input.strip():
            parsed = parse_initial_query(user_input)
            
            # Check if LLM needs clarification
            if parsed.get("needs_clarification"):
                # Stay in initial state and ask for clarification
                return {
                    "bot_message": parsed.get("clarification_message", "Could you provide more details?"),
                    "state": "collecting_initial",
                    "data": {"parsed": parsed}
                }
            
            # Update preferences with parsed values
            if parsed.get("goals"):
                preferences["goals"] = parsed["goals"]
            if parsed.get("sectors"):
                preferences["sectors"] = parsed["sectors"]
            if parsed.get("risk_tolerance"):
                preferences["risk_tolerance"] = parsed["risk_tolerance"]
            
            # Determine next state based on what was parsed
            if not preferences.get("goals"):
                # Need to collect goals
                return {
                    "bot_message": format_goals_question(parsed),
                    "state": "collecting_goals",
                    "data": {"parsed": parsed}
                }
            elif not preferences.get("sectors"):
                # Have goals, need sectors
                suggested = suggest_sectors_from_goals(preferences["goals"])
                return {
                    "bot_message": format_sectors_question(preferences["goals"], suggested),
                    "state": "collecting_sectors",
                    "data": {"suggested_sectors": suggested}
                }
            elif not preferences.get("risk_tolerance"):
                # Have goals and sectors, need risk
                return {
                    "bot_message": format_risk_question(),
                    "state": "collecting_risk",
                    "data": {}
                }
            else:
                # Have everything, go to confirmation
                return {
                    "bot_message": format_confirmation(
                        preferences, session.get("analysis_mode", "full_research")
                    ),
                    "state": "confirming",
                    "data": {}
                }
        else:
            # Empty input, start with welcome
            return {
                "bot_message": get_welcome_message(),
                "state": "conversational",
                "data": {}
            }
    
    # Collecting initial comprehensive input
    elif state == "collecting_initial":
        # Check if user is asking for examples
        user_lower = user_input.strip().lower()
        if any(keyword in user_lower for keyword in ["example", "examples", "sample", "demo"]):
            return {
                "bot_message": "Tell me what you want to explore, and I’ll guide you from there.",
                "state": "collecting_initial",
                "data": {}
            }
        
        parsed = parse_initial_query(user_input)
        
        # Check if clarification is needed
        if parsed.get("needs_clarification") and parsed.get("confidence") == "low":
            # Ask for clarification
            return {
                "bot_message": parsed.get("clarification_message", "Could you provide more details about your investment preferences?"),
                "state": "collecting_initial",
                "data": {}
            }
        
        # Update preferences (store what was parsed for debugging)
        if parsed.get("goals"):
            preferences["goals"] = parsed["goals"]
        if parsed.get("sectors"):
            preferences["sectors"] = parsed["sectors"]
        if parsed.get("risk_tolerance"):
            preferences["risk_tolerance"] = parsed["risk_tolerance"]
            print(f"[DEBUG] Set risk_tolerance to: {preferences['risk_tolerance']}")
        
        # DEBUG: Log current preferences state
        print(f"[DEBUG] After parsing - preferences: goals={preferences.get('goals')}, sectors={preferences.get('sectors')}, risk={preferences.get('risk_tolerance')}")
        
        # Build natural acknowledgment message
        understood_parts = []
        if preferences.get("goals"):
            goal_names = [INVESTMENT_GOALS[g]["name"] for g in preferences["goals"]]
            understood_parts.append(', '.join(goal_names))
        if preferences.get("sectors"):
            sector_text = ', '.join(preferences['sectors'])
            if understood_parts:
                understood_parts.append(f"in the {sector_text} {'sector' if len(preferences['sectors']) == 1 else 'sectors'}")
            else:
                understood_parts.append(f"the {sector_text} {'sector' if len(preferences['sectors']) == 1 else 'sectors'}")
        if preferences.get("risk_tolerance"):
            risk_text = f"with {preferences['risk_tolerance']} risk tolerance"
            understood_parts.append(risk_text)
        
        acknowledged = " ".join(understood_parts) if understood_parts else ""
        
        # If clarification needed AND nothing was understood, ask for clarification and stay in initial
        # If something was understood, proceed to ask for missing pieces
        if parsed.get("needs_clarification") and not acknowledged:
            return {
                "bot_message": parsed.get("clarification_message", "Could you provide more details about your investment preferences?"),
                "state": "collecting_initial",
                "data": {}
            }
        
        # Determine what to ask next
        if not preferences.get("goals"):
            goals_q = format_goals_question(parsed)
            message = f"Great! I can see you're interested in {acknowledged}.\n\n{goals_q}" if acknowledged else goals_q
            return {
                "bot_message": message,
                "state": "collecting_goals",
                "data": {}
            }
        elif not preferences.get("sectors"):
            suggested = suggest_sectors_from_goals(preferences["goals"])
            sectors_q = format_sectors_question(preferences["goals"], suggested)
            message = f"Great! I can see you're interested in {acknowledged}.\n\n{sectors_q}" if acknowledged else sectors_q
            print(f"[DEBUG] Returning sectors question. Message length: {len(message)}")
            print(f"[DEBUG] Message preview: {message[:200]}...")
            return {
                "bot_message": message,
                "state": "collecting_sectors",
                "data": {"suggested_sectors": suggested}
            }
        elif not preferences.get("risk_tolerance"):
            risk_q = format_risk_question()
            message = f"Great! I can see you're interested in {acknowledged}.\n\n{risk_q}" if acknowledged else risk_q
            return {
                "bot_message": message,
                "state": "collecting_risk",
                "data": {}
            }
        else:
            return {
                "bot_message": format_confirmation(
                    preferences, session.get("analysis_mode", "full_research")
                ),
                "state": "confirming",
                "data": {}
            }
    
    # Collecting goals
    elif state == "collecting_goals":
        # First, try to parse the full input to see if they provided other info too
        parsed = parse_initial_query(user_input)
        
        # Update any provided preferences
        if parsed.get("sectors") and not preferences.get("sectors"):
            preferences["sectors"] = parsed["sectors"]
        if parsed.get("risk_tolerance") and not preferences.get("risk_tolerance"):
            preferences["risk_tolerance"] = parsed["risk_tolerance"]
        
        # Handle goals parsing
        suggested_sectors = []
        if not user_input.strip():
            # No goals - exploratory mode
            preferences["goals"] = []
        elif parsed.get("goals"):
            # Goals already parsed from initial query
            preferences["goals"] = parsed["goals"]
            suggested_sectors = suggest_sectors_from_goals(parsed["goals"])
        elif llm_client and not user_input[0].isdigit():
            # Try to parse goals with LLM
            from ui.chatbot import parse_with_llm
            goal_keys = list(INVESTMENT_GOALS.keys())
            parsed_goals = parse_with_llm(
                llm_client,
                user_input,
                "Investment goals for financial research",
                goal_keys
            )
            if parsed_goals:
                preferences["goals"] = parsed_goals
                suggested_sectors = suggest_sectors_from_goals(parsed_goals)
            else:
                # Could not parse
                return {
                    "bot_message": "I couldn't understand those goals. Please try again or describe your investment objectives.",
                    "state": "collecting_goals",
                    "data": {}
                }
        else:
            # Try number parsing
            try:
                selected_indices = [int(x.strip()) for x in user_input.split(",")]
                goal_keys = list(INVESTMENT_GOALS.keys())
                selected_goals = []
                
                for idx in selected_indices:
                    if 1 <= idx <= len(INVESTMENT_GOALS):
                        selected_goals.append(goal_keys[idx - 1])
                    elif idx == len(INVESTMENT_GOALS) + 1:
                        # "Other" option - no goals
                        selected_goals = []
                        break
                
                preferences["goals"] = selected_goals
                suggested_sectors = suggest_sectors_from_goals(selected_goals)
            except (ValueError, IndexError):
                return {
                    "bot_message": "Invalid input. Please enter goal numbers (e.g., '1,3') or describe your goals.",
                    "state": "collecting_goals",
                    "data": {}
                }
        
        # Determine what to ask next based on what's still missing
        # Create acknowledgment for goals
        if preferences["goals"]:
            goal_names = [INVESTMENT_GOALS[g]["name"] for g in preferences["goals"]]
            acknowledgment = f"Great! You're interested in **{', '.join(goal_names)}**.\n\n"
        else:
            acknowledgment = "Great! Let's explore some investment opportunities.\n\n"
        
        if not preferences.get("sectors"):
            return {
                "bot_message": acknowledgment + format_sectors_question(preferences["goals"], suggested_sectors),
                "state": "collecting_sectors",
                "data": {"suggested_sectors": suggested_sectors}
            }
        elif not preferences.get("risk_tolerance"):
            return {
                "bot_message": acknowledgment + format_risk_question(),
                "state": "collecting_risk",
                "data": {}
            }
        else:
            return {
                "bot_message": format_confirmation(
                    preferences, session.get("analysis_mode", "full_research")
                ),
                "state": "confirming",
                "data": {}
            }
    
    # Collecting sectors
    elif state == "collecting_sectors":
        # DEBUG: Log what we're starting with
        print(f"[DEBUG] collecting_sectors - Starting preferences: goals={preferences.get('goals')}, sectors={preferences.get('sectors')}, risk={preferences.get('risk_tolerance')}")
        
        # First, try to parse the full input to see if they provided risk too
        parsed = parse_initial_query(user_input)
        if parsed.get("risk_tolerance") and not preferences.get("risk_tolerance"):
            preferences["risk_tolerance"] = parsed["risk_tolerance"]
            print(f"[DEBUG] Updated risk_tolerance from parsed: {preferences['risk_tolerance']}")
        
        suggested_sectors = session.get("data", {}).get("suggested_sectors", [])
        user_input_lower = user_input.strip().lower()
        
        # Check for "suggested + X" pattern
        wants_suggested_plus = any(keyword in user_input_lower for keyword in [
            "suggested", "suggest", "recommendation", "recommended"
        ])
        
        # Check if sectors were already parsed from full query
        if parsed.get("sectors") and not wants_suggested_plus:
            # Direct sector specification, use as-is
            preferences["sectors"] = parsed["sectors"]
        elif wants_suggested_plus:
            # User wants suggested sectors plus something else
            # Extract what to add beyond suggested
            additional_sectors = []
            
            if llm_client:
                # Remove suggestion-related keywords to extract the additional parts
                additional_text = user_input_lower
                for keyword in ["suggested", "suggestions", "recommended", "recommendations"]:
                    additional_text = additional_text.replace(keyword, "")
                for connector in ["plus", "and", "also", "with", "add", "include"]:
                    additional_text = additional_text.replace(connector, "")
                
                additional_text = additional_text.strip()
                
                if additional_text:
                    # Parse the additional sectors
                    additional_sectors = parse_sectors_with_llm(llm_client, additional_text)
                    if additional_sectors:
                        # Remove any that are already in suggested
                        additional_sectors = [s for s in additional_sectors if s not in suggested_sectors]
            
            # Combine suggested + additional
            if suggested_sectors:
                combined = suggested_sectors.copy()
                if additional_sectors:
                    combined.extend(additional_sectors)
                preferences["sectors"] = combined
                print(f"[DEBUG] Combined suggested ({suggested_sectors}) + additional ({additional_sectors}) = {combined}")
            elif additional_sectors:
                # No suggested sectors available, just use additional
                preferences["sectors"] = additional_sectors
            else:
                # Asked for suggested but no suggested available and nothing additional
                preferences["sectors"] = suggested_sectors if suggested_sectors else []
        # Empty input with suggestions - use suggested
        elif not user_input.strip() and suggested_sectors:
            preferences["sectors"] = suggested_sectors
        # Check for delegation ("you choose", "up to you", etc.)
        elif llm_client and is_delegating_decision(llm_client, user_input, "sector selection"):
            if suggested_sectors:
                preferences["sectors"] = suggested_sectors
            else:
                # Default diversified approach
                preferences["sectors"] = ["technology", "healthcare", "financial-services", "consumer", "industrials"]
        # Type 'all' for all sectors
        elif user_input.strip().lower() == "all":
            preferences["sectors"] = AVAILABLE_SECTORS.copy()
        # Try semantic parsing with LLM first for any text input
        elif llm_client and user_input.strip():
            # Check if it's pure numbers first
            if user_input.strip().replace(',', '').replace(' ', '').isdigit():
                # Parse numbers
                try:
                    selected_indices = [int(x.strip()) for x in user_input.split(",")]
                    selected_sectors = []
                    for idx in selected_indices:
                        if 1 <= idx <= len(AVAILABLE_SECTORS):
                            selected_sectors.append(AVAILABLE_SECTORS[idx - 1])
                    preferences["sectors"] = selected_sectors
                except (ValueError, IndexError):
                    return {
                        "bot_message": "Invalid input. Please enter sector numbers (e.g., '1,2,5') or describe the sectors.",
                        "state": "collecting_sectors",
                        "data": {"suggested_sectors": suggested_sectors}
                    }
            else:
                # Parse with LLM for natural language
                parsed_sectors = parse_sectors_with_llm(llm_client, user_input)
                if parsed_sectors:
                    preferences["sectors"] = parsed_sectors
                else:
                    return {
                        "bot_message": "I couldn't understand those sectors. Please try again or enter numbers (e.g., '1,2,5').",
                        "state": "collecting_sectors",
                        "data": {"suggested_sectors": suggested_sectors}
                    }
        
        # Determine what to ask next
        risk_value = preferences.get("risk_tolerance")
        print(f"[DEBUG] Before final check - risk_tolerance value: '{risk_value}', type: {type(risk_value)}, bool: {bool(risk_value)}")
        print(f"[DEBUG] Full preferences dict: {preferences}")
        
        # Create acknowledgment for sectors
        if preferences.get("sectors"):
            sector_list = ', '.join(preferences["sectors"])
            acknowledgment = f"Perfect! You're interested in **{sector_list}**.\n\n"
        else:
            acknowledgment = ""
        
        if not risk_value or risk_value not in ["low", "medium", "high"]:
            print("[DEBUG] Risk tolerance is missing or invalid, asking for it")
            return {
                "bot_message": acknowledgment + format_risk_question(),
                "state": "collecting_risk",
                "data": {}
            }
        else:
            print(f"[DEBUG] Risk tolerance exists: {risk_value}, going to confirmation")
            return {
                "bot_message": format_confirmation(
                    preferences, session.get("analysis_mode", "full_research")
                ),
                "state": "confirming",
                "data": {}
            }
    
    # Collecting risk tolerance
    elif state == "collecting_risk":
        # First, try to parse the full input in case they provided other info
        parsed = parse_initial_query(user_input)
        if parsed.get("goals") and not preferences.get("goals"):
            preferences["goals"] = parsed["goals"]
        if parsed.get("sectors") and not preferences.get("sectors"):
            preferences["sectors"] = parsed["sectors"]
        
        # Check if risk was already parsed
        if parsed.get("risk_tolerance"):
            preferences["risk_tolerance"] = parsed["risk_tolerance"]
        else:
            # Manual parsing
            risk_map = {"1": "low", "2": "medium", "3": "high"}
            
            if user_input.strip().lower() in ["low", "medium", "high"]:
                preferences["risk_tolerance"] = user_input.strip().lower()
            elif user_input.strip() in ["1", "2", "3"]:
                preferences["risk_tolerance"] = risk_map[user_input.strip()]
            elif llm_client:
                # Parse with LLM
                from ui.chatbot import parse_with_llm
                parsed_risk = parse_with_llm(
                    llm_client,
                    user_input,
                    "Risk tolerance level for investing",
                    ["low", "medium", "high"]
                )
                if parsed_risk and len(parsed_risk) == 1:
                    preferences["risk_tolerance"] = parsed_risk[0]
                else:
                    return {
                        "bot_message": "Please specify your risk tolerance: low, medium, or high (or enter 1-3).",
                        "state": "collecting_risk",
                        "data": {}
                    }
            else:
                return {
                    "bot_message": "Please specify your risk tolerance: low, medium, or high (or enter 1-3).",
                    "state": "collecting_risk",
                    "data": {}
                }
        
        # Create acknowledgment for risk tolerance
        risk_level = preferences.get("risk_tolerance", "medium")
        acknowledgment = f"Got it! You have a **{risk_level}** risk tolerance.\n\n"
        
        # Move to confirmation
        return {
            "bot_message": acknowledgment
            + format_confirmation(
                preferences, session.get("analysis_mode", "full_research")
            ),
            "state": "confirming",
            "data": {}
        }
    
    # Confirming preferences
    elif state == "confirming":
        response_lower = user_input.strip().lower()
        if response_lower in ["yes", "y"]:
            mode = session.get("analysis_mode", "full_research")
            start_message = (
                "Great! Starting stock-focused analysis..."
                if mode == "stock_picks"
                else "Great! Starting research analysis..."
            )
            return {
                "bot_message": start_message,
                "state": "ready_to_research",
                "data": {}
            }
        elif response_lower in ["no", "n"]:
            # Restart
            session["analysis_mode"] = "full_research"
            preferences["goals"] = None
            preferences["sectors"] = None
            preferences["risk_tolerance"] = None
            return {
                "bot_message": get_welcome_message(),
                "state": "collecting_initial",
                "data": {}
            }
        else:
            return {
                "bot_message": "Please answer 'yes' or 'no'.",
                "state": "confirming",
                "data": {}
            }
    
    # Default fallback
    return {
        "bot_message": "I didn't understand that. Let's start over.",
        "state": "collecting_initial",
        "data": {}
    }


def get_welcome_message() -> str:
    """Get initial welcome message"""
    return """Welcome! You can ask for stock ideas, market overview, sector risks, news headlines, or full research."""


def format_goals_question(parsed: Dict = None) -> str:
    """Format the goals collection question."""
    goals_list = "\n".join(
        [
            f"{idx}. **{info['name']}**: {info['description']}"
            for idx, (key, info) in enumerate(INVESTMENT_GOALS.items(), 1)
        ]
    )

    return f"""**What are your primary investment objectives?**

{goals_list}
{len(INVESTMENT_GOALS) + 1}. Other/Exploratory (no specific goal)

You can enter numbers (e.g., '1,3') or describe your goals naturally."""


def format_sectors_question(goals: List[str], suggested: List[str]) -> str:
    """Format the sectors collection question"""
    msg = "**Which sectors would you like to analyze?**\n\n"
    
    if suggested:
        msg += f"Based on your goals, I suggest: **{', '.join(suggested)}**\n\n"
    
    msg += "**Available sectors:**\n"
    for idx, sector in enumerate(AVAILABLE_SECTORS, 1):
        marker = " ✓ (suggested)" if sector in suggested else ""
        msg += f"{idx}. {sector}{marker}\n"
    
    msg += "\n**How to select:**\n"
    msg += "• Natural language: 'tech and pharma', 'renewable energy'\n"
    msg += "• Numbers: '1,2,5'\n"
    msg += "• Type 'all' for all sectors\n"
    
    return msg


def format_risk_question() -> str:
    """Format the risk tolerance question"""
    return """**What is your risk tolerance?** (Required)

1. **Low** - Prefer stable, low-volatility investments
2. **Medium** - Balanced risk/reward profile
3. **High** - Comfortable with volatility for higher potential returns

Enter 1-3 or describe your risk comfort level."""


def format_confirmation(preferences: Dict, analysis_mode: str = "full_research") -> str:
    """Format confirmation message"""
    goals = preferences.get("goals", [])
    sectors = preferences.get("sectors", [])
    risk = preferences.get("risk_tolerance", "medium")
    
    msg = "**PREFERENCES SUMMARY**\n\n"
    
    if goals:
        goal_names = [INVESTMENT_GOALS[g]["name"] for g in goals]
        msg += f"**Investment Goals:** {', '.join(goal_names)}\n"
    else:
        msg += "**Investment Goals:** Exploratory (no specific goals)\n"
    
    msg += f"**Sectors to Analyze:** {', '.join(sectors)} ({len(sectors)} total)\n"
    msg += f"**Risk Tolerance:** {risk.upper()}\n"
    mode_label = "Stock Picks" if analysis_mode == "stock_picks" else "Full Research Report"
    msg += f"**Analysis Mode:** {mode_label}\n\n"
    msg += "**Proceed with this analysis?** (yes/no)"
    
    return msg


def format_research_results(research_data: Dict, preferences: Dict) -> str:
    """Format research results as HTML for display"""
    html = "<div class='research-results'>"
    
    # Market Overview
    html += "<div class='result-section'><h3>📊 Market Overview</h3>"
    market_ctx = research_data.get("market_context", {})
    if "error" not in market_ctx:
        market_data = market_ctx.get("data", market_ctx)
        if market_data:
            html += "<div class='market-indices'>"
            for index_name, index_data in market_data.items():
                if isinstance(index_data, dict):
                    value = index_data.get('value', 'N/A')
                    change = index_data.get('change', 'N/A')
                    change_pct = index_data.get('change_percent', 'N/A')
                    change_class = 'positive' if str(change).startswith('+') or (isinstance(change, (int, float)) and change > 0) else 'negative'
                    html += f"""
                    <div class='index-card'>
                        <div class='index-name'>{index_name}</div>
                        <div class='index-value'>{value}</div>
                        <div class='index-change {change_class}'>{change} ({change_pct}%)</div>
                    </div>
                    """
            html += "</div>"
    else:
        html += f"<p class='error'>Error: {market_ctx.get('error')}</p>"
    html += "</div>"
    
    # Sector Analysis
    html += "<div class='result-section'><h3>🎯 Sector Analysis</h3>"
    sectors = research_data.get("sector_deep_dives", {})
    for sector_name, sector_data in sectors.items():
        html += f"<div class='sector-card'><h4>{sector_name.upper()}</h4>"
        
        # Performance
        perf = sector_data.get("market_performance", {})
        if "error" not in perf and perf:
            html += "<div class='sector-metric'><strong>Market Performance:</strong><ul>"
            html += f"<li>1-Month: {perf.get('performance_1m', 'N/A')}</li>"
            html += f"<li>3-Month: {perf.get('performance_3m', 'N/A')}</li>"
            html += f"<li>1-Year: {perf.get('performance_1y', 'N/A')}</li>"
            top = perf.get('top_performers', [])
            if top:
                html += f"<li>Top Performers: {', '.join([str(t) for t in top[:3]])}</li>"
            html += "</ul></div>"
        
        # Risk
        risk = sector_data.get("risk_profile", {})
        if "error" not in risk and risk:
            metrics = risk.get('metrics', risk)
            html += "<div class='sector-metric'><strong>Risk Profile:</strong><ul>"
            html += f"<li>Volatility: {metrics.get('annualized_volatility', 'N/A')}</li>"
            html += f"<li>Max Drawdown: {metrics.get('max_drawdown', 'N/A')}</li>"
            html += f"<li>Trend: {metrics.get('trend', 'N/A')}</li>"
            html += f"<li>Risk Level: {metrics.get('percentile', 'N/A')}</li>"
            html += "</ul></div>"
        
        # News
        news = sector_data.get("news_analysis", {})
        if "error" not in news and news:
            risks = news.get('identified_risks', [])
            html += f"<div class='sector-metric'><strong>Risk Themes ({len(risks)} identified):</strong><ul>"
            for risk_item in risks[:3]:
                risk_text = risk_item.get('risk', 'N/A')
                category = risk_item.get('category', 'N/A')
                html += f"<li><span class='risk-category'>[{category.upper()}]</span> {risk_text}</li>"
            html += "</ul></div>"
        
        html += "</div>"
    html += "</div>"
    
    # Portfolio Implications
    if len(sectors) > 1:
        html += "<div class='result-section'><h3>💼 Portfolio Implications</h3>"
        corr = research_data.get("portfolio_implications", {}).get("correlations", {})
        if "error" not in corr and corr:
            html += f"<p><strong>Diversification Score:</strong> {corr.get('diversification_score', 'N/A')}</p>"
            
            insights = corr.get('insights', {})
            if insights:
                html += "<div class='insights'><ul>"
                for key, value in insights.items():
                    if isinstance(value, list) and value:
                        html += f"<li><strong>{key.replace('_', ' ').title()}:</strong> {', '.join(value[:3])}</li>"
                html += "</ul></div>"
        html += "</div>"
    
    # Goal-Based Recommendations
    goal_recs = research_data.get("goal_based_recommendations", {})
    if goal_recs and goal_recs.get("ranked_sectors"):
        html += "<div class='result-section'><h3>⭐ Recommendations</h3>"
        html += f"<p>{goal_recs.get('summary', '')}</p>"
        
        top_picks = goal_recs.get("top_picks", [])
        if top_picks:
            html += "<div class='recommendations'>"
            for idx, pick in enumerate(top_picks, 1):
                html += f"""
                <div class='recommendation-card'>
                    <div class='rec-number'>{idx}</div>
                    <div class='rec-content'>
                        <h4>{pick['sector'].upper()} <span class='score'>Score: {pick['score']}</span></h4>
                        <p><strong>Volatility:</strong> {pick['volatility']} | <strong>1M Performance:</strong> {pick['performance_1m']}</p>
                        <p><strong>Risk Level:</strong> {pick['risk_level']}</p>
                        {f"<p><strong>Why:</strong> {', '.join(pick['reasons'][:2])}</p>" if pick.get('reasons') else ''}
                    </div>
                </div>
                """
            html += "</div>"
        html += "</div>"
    
    # Stock Recommendations
    stock_recs = research_data.get("stock_recommendations", {})
    if stock_recs and "error" not in stock_recs:
        html += "<div class='result-section'><h3>📈 Stock Recommendations</h3>"
        
        for goal, goal_data in stock_recs.items():
            if isinstance(goal_data, dict) and "stocks" in goal_data:
                stocks = goal_data.get("stocks", [])
                goal_display = goal.upper()
                html += f"<h4>{goal_display} Goal - {goal_data.get('summary', '')}</h4>"
                
                if stocks:
                    html += "<div class='stock-recommendations'>"
                    for idx, stock in enumerate(stocks, 1):
                        html += f"""
                        <div class='stock-card'>
                            <div class='stock-header'>
                                <span class='stock-ticker'>{stock['ticker']}</span>
                                <span class='stock-price'>${stock['price']}</span>
                            </div>
                            <h5>{stock['name']}</h5>
                            <div class='stock-metrics'>
                                <div class='metric'><strong>1M Performance:</strong> {stock['performance_1m']}</div>
                                <div class='metric'><strong>Volatility:</strong> {stock['volatility']}</div>
                                {f"<div class='metric'><strong>Dividend Yield:</strong> {stock['dividend_yield']}</div>" if stock.get('dividend_yield') != 'N/A' else ''}
                                {f"<div class='metric'><strong>ESG Score:</strong> {stock['esg_score']}</div>" if stock.get('esg_score') != 'N/A' else ''}
                            </div>
                            <div class='stock-score'>Score: {stock['score']}</div>
                            {f"<p class='stock-reasons'><strong>Why:</strong> {', '.join(stock['reasons'][:2])}</p>" if stock.get('reasons') else ''}
                        </div>
                        """
                    html += "</div>"
        html += "</div>"
    
    # AI Summaries
    html += "<div class='result-section'><h3>🤖 AI-Generated Insights</h3>"
    
    sector_summary = generate_sector_goal_summary(research_data, preferences)
    html += f"<div class='ai-summary'><h4>Sector-Goal Alignment</h4><p>{sector_summary}</p></div>"
    
    risk_summary = generate_risk_summary_with_citations(research_data)
    html += f"<div class='ai-summary'><h4>Key Risks & News Citations</h4><p>{risk_summary}</p></div>"
    
    # Add stock picks summary if available
    stock_summary = generate_stock_picks_summary(research_data)
    if stock_summary:
        html += f"<div class='ai-summary'><h4>Stock Recommendations Explained</h4><p>{stock_summary}</p></div>"
    
    html += "</div>"
    
    html += "</div>"
    return html


def format_stock_focused_results(research_data: Dict, preferences: Dict) -> str:
    """Format a stock-picks-first result view."""
    html = "<div class='research-results'>"
    html += "<div class='result-section'><h3>📈 Stock Picks</h3>"

    stock_recs = research_data.get("stock_recommendations", {})
    if stock_recs and "error" not in stock_recs:
        for goal, goal_data in stock_recs.items():
            if isinstance(goal_data, dict) and "stocks" in goal_data:
                stocks = goal_data.get("stocks", [])
                goal_display = goal.upper()
                html += f"<h4>{goal_display} Goal - {goal_data.get('summary', '')}</h4>"

                if stocks:
                    html += "<div class='stock-recommendations'>"
                    for stock in stocks:
                        html += f"""
                        <div class='stock-card'>
                            <div class='stock-header'>
                                <span class='stock-ticker'>{stock['ticker']}</span>
                                <span class='stock-price'>${stock['price']}</span>
                            </div>
                            <h5>{stock['name']}</h5>
                            <div class='stock-metrics'>
                                <div class='metric'><strong>1M Performance:</strong> {stock['performance_1m']}</div>
                                <div class='metric'><strong>Volatility:</strong> {stock['volatility']}</div>
                                {f"<div class='metric'><strong>Dividend Yield:</strong> {stock['dividend_yield']}</div>" if stock.get('dividend_yield') != 'N/A' else ''}
                                {f"<div class='metric'><strong>ESG Score:</strong> {stock['esg_score']}</div>" if stock.get('esg_score') != 'N/A' else ''}
                            </div>
                            <div class='stock-score'>Score: {stock['score']}</div>
                            {f"<p class='stock-reasons'><strong>Why:</strong> {', '.join(stock['reasons'][:2])}</p>" if stock.get('reasons') else ''}
                        </div>
                        """
                    html += "</div>"
    else:
        html += "<p>No stock recommendations available for the selected preferences yet.</p>"

    html += "</div>"

    stock_summary = generate_stock_picks_summary(research_data)
    if stock_summary:
        html += f"<div class='result-section'><h3>🤖 Stock Picks Explained</h3><p>{stock_summary}</p></div>"

    html += "</div>"
    return html


# API Endpoints
@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "healthy", "service": "Finsense API"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatMessage, user: Dict[str, Any] = Depends(get_current_user)):
    """
    Handle chat messages and guide conversation.
    """
    # Get or create session
    session_id = request.session_id
    if not session_id or session_id not in sessions:
        session_id = create_session()
    session = sessions[session_id]
    
    # Add user message to history
    session["conversation_history"].append({
        "role": "user",
        "message": request.message,
        "timestamp": datetime.now().isoformat()
    })
    
    # Process message based on state
    response_data = await get_llm_response(request.message, "", session, session_id)
    
    # DEBUG: Log the response before returning
    print(f"[DEBUG ENDPOINT] Response data: state={response_data.get('state')}, bot_message length={len(response_data.get('bot_message', ''))}")
    print(f"[DEBUG ENDPOINT] bot_message preview: {response_data.get('bot_message', '')[:200]}")
    
    # Update session state
    session["state"] = response_data["state"]
    if "data" in response_data and response_data["data"]:
        session["data"] = response_data["data"]
    
    # Add bot message to history
    session["conversation_history"].append({
        "role": "bot",
        "message": response_data["bot_message"],
        "timestamp": datetime.now().isoformat()
    })
    
    return ChatResponse(
        session_id=session_id,
        bot_message=response_data["bot_message"],
        state=response_data["state"],
        data=response_data.get("data"),
        needs_confirmation=response_data["state"] == "confirming"
    )


@app.post("/api/research", response_model=ResearchResponse)
async def research(request: ResearchRequest, user: Dict[str, Any] = Depends(get_current_user)):
    """
    Trigger research analysis for a session.
    """
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[request.session_id]
    preferences = session["preferences"]
    analysis_mode = session.get("analysis_mode", "full_research")
    
    # Validate preferences
    if not preferences.get("sectors") or not preferences.get("risk_tolerance"):
        raise HTTPException(status_code=400, detail="Incomplete preferences")
    
    # Update state
    session["state"] = "researching"
    
    try:
        # Initialize coordinator
        coordinator = FinsenseCoordinator()
        await coordinator.initialize()
        
        # Run research
        research_data = await coordinator.conduct_research(
            sectors=preferences["sectors"],
            risk_tolerance=preferences["risk_tolerance"],
            investment_goals=preferences.get("goals", [])
        )
        
        # Store results
        session["research_data"] = research_data
        session["state"] = "complete"
        
        # Cleanup
        await coordinator.cleanup()
        
        # Format results as HTML
        if analysis_mode == "stock_picks":
            results_html = format_stock_focused_results(research_data, preferences)
        else:
            results_html = format_research_results(research_data, preferences)
        
        return ResearchResponse(
            session_id=request.session_id,
            status="complete",
            results={
                "html": results_html,
                "raw": research_data
            }
        )
        
    except Exception as e:
        session["state"] = "error"
        raise HTTPException(status_code=500, detail=f"Research failed: {str(e)}")


@app.get("/api/status/{session_id}")
async def get_status(session_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Get session status"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    return {
        "session_id": session_id,
        "state": session["state"],
        "preferences": session["preferences"]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
