"""
Interactive chatbot for collecting investor preferences and goals.

This module provides a conversational CLI interface to gather:
- Investment goals (growth, income, ESG, etc.)
- Sector/industry preferences
- Risk tolerance (mandatory)

Uses Groq LLM for semantic understanding of natural language inputs.
"""

import os
import json
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False
    Groq = None


# Available sectors in the Finsense system
AVAILABLE_SECTORS = [
    "technology",
    "healthcare",
    "financial-services",
    "energy",
    "consumer",
    "consumer-discretionary",
    "consumer-staples",
    "utilities",
    "real-estate",
    "industrials",
    "materials",
    "communication-services"
]

# Investment goal definitions
INVESTMENT_GOALS = {
    "growth": {
        "name": "Growth",
        "description": "Capital appreciation through high-growth sectors",
        "suggested_sectors": ["technology", "healthcare", "communication-services"]
    },
    "income": {
        "name": "Income/Dividends",
        "description": "Stable dividend income and cash flow",
        "suggested_sectors": ["utilities", "consumer-staples", "real-estate"]
    },
    "esg": {
        "name": "ESG/Environmental",
        "description": "Environmentally and socially responsible investing",
        "suggested_sectors": ["utilities", "healthcare", "technology"]
    },
    "value": {
        "name": "Value",
        "description": "Undervalued sectors with strong fundamentals",
        "suggested_sectors": ["financial-services", "energy", "industrials"]
    },
    "defensive": {
        "name": "Defensive/Stability",
        "description": "Low-volatility sectors for capital preservation",
        "suggested_sectors": ["consumer-staples", "utilities", "healthcare"]
    },
    "diversified": {
        "name": "Diversified Portfolio",
        "description": "Broad market exposure across multiple sectors",
        "suggested_sectors": ["technology", "healthcare", "financial-services", "consumer", "industrials"]
    }
}

RISK_TOLERANCE_LEVELS = ["low", "medium", "high"]


def parse_initial_query(user_input: str) -> Dict[str, Any]:
    """
    Parse an initial open-ended query for goals, sectors, and risk tolerance using LLM.
    
    Returns dict with:
        - goals: List[str] or None
        - sectors: List[str] or None  
        - risk_tolerance: str or None
        - needs_clarification: bool
        - clarification_message: str (if needs clarification)
        - confidence: str (high, medium, low)
    """
    llm_client = get_llm_client()
    
    if not llm_client:
        # Fallback: return needs clarification
        return {
            "goals": None, 
            "sectors": None, 
            "risk_tolerance": None,
            "needs_clarification": True,
            "clarification_message": "I'd be happy to help! Could you tell me about your investment goals, preferred sectors, or risk tolerance?",
            "confidence": "low"
        }
    
    # Use LLM for comprehensive parsing with confidence assessment
    try:
        prompt = f"""Parse this investment query and extract investment goals, sectors, and risk tolerance.
Assess your confidence in the interpretation and determine if clarification is needed.

AVAILABLE INVESTMENT GOALS: {', '.join(INVESTMENT_GOALS.keys())}
AVAILABLE SECTORS: {', '.join(AVAILABLE_SECTORS)}
RISK TOLERANCE LEVELS: low, medium, high

User query: "{user_input}"

Analyze the query and return ONLY a JSON object with these fields:
{{
  "goals": [list of goal keys that match, or null if unclear/not mentioned],
  "sectors": [list of sector names that match, or null if unclear/not mentioned],
  "risk_tolerance": "low" or "medium" or "high" or null if unclear/not mentioned,
  "confidence": "high" or "medium" or "low",
  "needs_clarification": true or false,
  "clarification_message": "what specifically needs clarification, if needs_clarification is true"
}}

Guidelines:
- Set confidence to "high" only if the user's intent is very clear
- Set confidence to "medium" if there's some ambiguity but you can make reasonable assumptions
- Set confidence to "low" if the query is vague or could mean multiple things
- Set needs_clarification to true if confidence is low OR if critical information is ambiguous
- Be generous in interpretation - if user says "tech stocks" assume sectors: ["technology"]
- If user says general things like "help me invest" or "what should I do", set needs_clarification to true

Examples:

Query: "I want growth in tech and healthcare with low risk"
Result: {{"goals": ["growth"], "sectors": ["technology", "healthcare"], "risk_tolerance": "low", "confidence": "high", "needs_clarification": false, "clarification_message": null}}

Query: "ESG investing in energy"  
Result: {{"goals": ["esg"], "sectors": ["energy"], "risk_tolerance": null, "confidence": "high", "needs_clarification": false, "clarification_message": null}}

Query: "I want safe investments"
Result: {{"goals": null, "sectors": null, "risk_tolerance": "low", "confidence": "medium", "needs_clarification": true, "clarification_message": "I understand you want safe investments. Which sectors interest you most? (technology, healthcare, finance, etc.)"}}

Query: "help me"
Result: {{"goals": null, "sectors": null, "risk_tolerance": null, "confidence": "low", "needs_clarification": true, "clarification_message": "I'd be happy to help! Are you looking for growth, income, ESG investing, or something else?"}}

Query: "ideas"
Result: {{"goals": null, "sectors": null, "risk_tolerance": null, "confidence": "high", "needs_clarification": false, "clarification_message": null}}

JSON object:"""

        response = llm_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=400
        )
        
        content = response.choices[0].message.content.strip()
        
        # Remove markdown code blocks
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]).strip()
        
        if content.startswith("json"):
            content = content[4:].strip()
        
        parsed = json.loads(content)
        
        # Validate and clean the parsed data
        result = {
            "goals": None,
            "sectors": None,
            "risk_tolerance": None,
            "needs_clarification": parsed.get("needs_clarification", False),
            "clarification_message": parsed.get("clarification_message"),
            "confidence": parsed.get("confidence", "medium")
        }
        
        # Validate goals
        if parsed.get("goals") and isinstance(parsed["goals"], list):
            valid_goals = [g for g in parsed["goals"] if g in INVESTMENT_GOALS]
            result["goals"] = valid_goals if valid_goals else None
        
        # Validate sectors
        if parsed.get("sectors") and isinstance(parsed["sectors"], list):
            valid_sectors = [s for s in parsed["sectors"] if s in AVAILABLE_SECTORS]
            result["sectors"] = valid_sectors if valid_sectors else None
        
        # Validate risk tolerance
        if parsed.get("risk_tolerance") in ["low", "medium", "high"]:
            result["risk_tolerance"] = parsed["risk_tolerance"]
        
        return result
        
    except Exception as e:
        if os.getenv("DEBUG_CHATBOT"):
            print(f"[DEBUG] LLM parsing error: {e}")
        return {
            "goals": None, 
            "sectors": None, 
            "risk_tolerance": None,
            "needs_clarification": True,
            "clarification_message": "I didn't quite catch that. Could you tell me more about what you're looking for?",
            "confidence": "low"
        }


def detect_user_intent(client: Any, user_input: str, context: str) -> str:
    """
    Lightweight LLM-based intent classification.
    
    Args:
        client: Groq client
        user_input: User's input text
        context: What they're responding to (goals, sectors, risk)
    
    Returns:
        One of: "delegate", "specify", "help", "unclear"
    """
    if not client:
        return "unclear"
    
    try:
        prompt = f"""Classify the user's intent in this conversation about {context}.

User input: "{user_input}"

Classify as ONE of these intents:
- "delegate": User wants you to decide/choose for them (e.g., "you pick", "whatever's best", "up to you", "you decide", "recommend something")
- "specify": User is specifying their own preferences (e.g., "tech and healthcare", "growth", "low risk")
- "help": User wants to see options/ideas (e.g., "what are my options", "show me", "help", "ideas")
- "unclear": Cannot determine intent

Return ONLY the intent word, nothing else."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10
        )
        
        intent = response.choices[0].message.content.strip().lower()
        
        # Validate response
        if intent in ["delegate", "specify", "help", "unclear"]:
            return intent
        
        return "unclear"
        
    except Exception as e:
        if os.getenv("DEBUG_CHATBOT"):
            print(f"[DEBUG] Intent detection error: {e}")
        return "unclear"


def get_llm_client() -> Optional[Any]:
    """Get Groq client if API key is available"""
    if not HAS_GROQ:
        return None
    
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    
    try:
        return Groq(api_key=api_key)
    except Exception:
        return None


def parse_sectors_with_llm(client: Any, user_input: str) -> Optional[List[str]]:
    """
    Use LLM to parse natural language sector selection with broad understanding.
    Handles synonyms, abbreviations, industry names, and various phrasings.
    
    Args:
        client: Groq client
        user_input: User's natural language input
    
    Returns:
        List of matched sector names, or None if parsing fails
    """
    if not client:
        return None
        
    try:
        prompt = f"""Parse the user's input to identify which financial market sectors they want to analyze.

VALID SECTORS (these are the ONLY allowed values):
- technology (also: tech, software, IT, computers, semiconductors, AI, cloud computing)
- healthcare (also: health, medical, pharma, pharmaceuticals, biotech, hospitals)
- financial-services (also: finance, banks, banking, fintech, insurance, financial)
- energy (also: oil, gas, petroleum, renewable energy, utilities energy, power)
- consumer (also: consumer goods, retail, e-commerce, shopping)
- consumer-discretionary (also: discretionary, luxury, entertainment, travel, automotive, cars)
- consumer-staples (also: staples, food, beverages, household goods, groceries)
- utilities (also: electric, water, power utilities, infrastructure utilities)
- real-estate (also: realestate, property, housing, REITs, commercial real estate)
- industrials (also: manufacturing, aerospace, defense, construction, machinery)
- materials (also: mining, chemicals, metals, commodities, raw materials)
- communication-services (also: communications, telecom, media, social media, streaming)

User input: "{user_input}"

Instructions:
- Understand synonyms, abbreviations, and related industry terms
- If user says "all" or "everything", return ALL sectors
- If user mentions specific companies, map them to their sectors (e.g., Apple → technology)
- Be flexible with phrasing (e.g., "tech stocks" → technology)
- Handle multiple sectors (e.g., "tech and healthcare" → ["technology", "healthcare"])
- Only return sector names from the valid list above

Return ONLY a JSON array of sector names (use the exact names from the valid list).

Examples:
"tech and pharma" → ["technology", "healthcare"]
"banks and insurance" → ["financial-services"]
"renewable energy and EVs" → ["energy", "consumer-discretionary"]
"software companies" → ["technology"]
"retail and e-commerce" → ["consumer"]
"all sectors" → [all 12 sectors listed]
"defensive stocks" → ["utilities", "consumer-staples", "healthcare"]
"growth sectors" → ["technology", "healthcare", "communication-services"]

JSON array:"""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # Slightly higher for better synonym matching
            max_tokens=300
        )
        
        content = response.choices[0].message.content.strip()
        
        # Debug output
        if os.getenv("DEBUG_CHATBOT"):
            print(f"[DEBUG] LLM Response: {content}")
        
        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]).strip()
        
        if content.startswith("json"):
            content = content[4:].strip()
        
        parsed = json.loads(content)
        
        # Validate that all returned sectors are valid
        if isinstance(parsed, list):
            valid_parsed = [s for s in parsed if s in AVAILABLE_SECTORS]
            return valid_parsed if valid_parsed else None
        
        return None
    except json.JSONDecodeError as e:
        if os.getenv("DEBUG_CHATBOT"):
            print(f"[DEBUG] JSON parse error: {e}")
            print(f"[DEBUG] Content was: {content}")
        return None
    except Exception as e:
        if os.getenv("DEBUG_CHATBOT"):
            print(f"[DEBUG] LLM parsing error: {type(e).__name__}: {e}")
        return None


def parse_with_llm(client: Any, user_input: str, context: str, valid_options: List[str]) -> Optional[List[str]]:
    """
    Use LLM to parse natural language input into structured selections.
    
    Args:
        client: Groq client
        user_input: User's natural language input
        context: Context about what we're parsing (goals, sectors, etc.)
        valid_options: List of valid option keys/values
    
    Returns:
        List of matched options, or None if parsing fails
    """
    if not client:
        return None
        
    try:
        prompt = f"""Parse the user's input into a list of valid options.

Context: {context}

Valid options: {', '.join(valid_options)}

User input: "{user_input}"

Return ONLY a JSON array of matched options from the valid list. If the user wants all options, return all. If input is unclear or doesn't match any options, return an empty array.

Examples:
- "I want growth and ESG" -> ["growth", "esg"]
- "tech and healthcare" -> ["technology", "healthcare"]
- "low risk" -> ["low"]
- "all sectors" -> [all valid sector options]

JSON array:"""
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=200
        )
        
        content = response.choices[0].message.content.strip()
        
        # Debug output
        if os.getenv("DEBUG_CHATBOT"):
            print(f"[DEBUG] LLM Response: {content}")
        
        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first line (```json or ```) and last line (```)
            content = "\n".join(lines[1:-1]).strip()
        
        # Remove "json" prefix if present
        if content.startswith("json"):
            content = content[4:].strip()
        
        parsed = json.loads(content)
        
        # Validate all options are valid
        if isinstance(parsed, list):
            valid_parsed = [opt for opt in parsed if opt in valid_options]
            return valid_parsed if valid_parsed else None
        
        return None
    except json.JSONDecodeError as e:
        if os.getenv("DEBUG_CHATBOT"):
            print(f"[DEBUG] JSON parse error: {e}")
            print(f"[DEBUG] Content was: {content}")
        return None
    except Exception as e:
        if os.getenv("DEBUG_CHATBOT"):
            print(f"[DEBUG] LLM parsing error: {type(e).__name__}: {e}")
        return None


def display_welcome():
    """Display welcome message and introduction"""
    print("\n" + "="*80)
    print("FINSENSE INVESTMENT RESEARCH ASSISTANT")
    print("="*80)
    print("\nWelcome! I'll help you identify sectors and stocks worth researching")
    print("based on your investment goals and risk tolerance.")
    print("\nLet's start by understanding your investment preferences...")
    print("-"*80)


def collect_investment_goals() -> List[str]:
    """Collect investment goals from user"""
    llm_client = get_llm_client()
    
    print("\n[STEP 1: Investment Goals]")
    print("\nWhat are your primary investment objectives?")
    print("\nAvailable goals:")
    
    for idx, (key, info) in enumerate(INVESTMENT_GOALS.items(), 1):
        print(f"  {idx}. {info['name']}: {info['description']}")
    
    print(f"\n  {len(INVESTMENT_GOALS) + 1}. Other/Exploratory (no specific goal)")
    
    if llm_client:
        print("\n[Natural Language Mode: Describe your goals or enter numbers]")
    else:
        print("\n[Tip: Set GROQ_API_KEY for natural language input]")
    
    while True:
        response = input("\nYour goals: ").strip()
        
        if not response:
            print("  -> No specific goals selected (exploratory mode)")
            return []
        
        # Try LLM parsing first if available
        if llm_client and not response[0].isdigit():
            goal_keys = list(INVESTMENT_GOALS.keys())
            parsed_goals = parse_with_llm(
                llm_client,
                response,
                "Investment goals for financial research",
                goal_keys
            )
            
            if parsed_goals:
                goal_names = [INVESTMENT_GOALS[g]["name"] for g in parsed_goals]
                print(f"  -> Understood: {', '.join(goal_names)}")
                confirm = input("  Is this correct? (yes/no): ").strip().lower()
                if confirm in ["yes", "y", ""]:
                    return parsed_goals
                else:
                    print("  Let's try again...")
                    continue
        
        # Fallback to number parsing
        try:
            selected_indices = [int(x.strip()) for x in response.split(",")]
            goal_keys = list(INVESTMENT_GOALS.keys())
            
            selected_goals = []
            for idx in selected_indices:
                if 1 <= idx <= len(INVESTMENT_GOALS):
                    selected_goals.append(goal_keys[idx - 1])
                elif idx == len(INVESTMENT_GOALS) + 1:
                    return []
                else:
                    raise ValueError(f"Invalid goal number: {idx}")
            
            goal_names = [INVESTMENT_GOALS[g]["name"] for g in selected_goals]
            print(f"  -> Selected: {', '.join(goal_names)}")
            return selected_goals
            
        except (ValueError, IndexError) as e:
            print(f"  [!] Could not parse input. Try numbers (e.g., '1,3') or describe your goals.")


def suggest_sectors_from_goals(goals: List[str]) -> List[str]:
    """Suggest sectors based on selected investment goals"""
    if not goals:
        return []
    
    # Collect all suggested sectors from goals
    suggested = set()
    for goal in goals:
        suggested.update(INVESTMENT_GOALS[goal]["suggested_sectors"])
    
    return sorted(list(suggested))


def is_delegating_decision(client: Any, user_input: str, context: str) -> bool:
    """
    Use LLM to detect if user is delegating the decision to the system.
    
    Args:
        client: Groq client
        user_input: User's response
        context: What decision is being delegated (e.g., "sector selection")
    
    Returns:
        True if user is delegating, False otherwise
    """
    if not client:
        return False
    
    try:
        prompt = f"""Is the user delegating this decision to you or asking you to decide for them?

Context: {context}
User said: "{user_input}"

Answer with ONLY "true" or "false".

Examples:
"whatever you think is best" → true
"you decide" → true
"up to you" → true
"I trust your judgment" → true
"you pick" → true
"surprise me" → true
"whatever you think" → true
"your call" → true
"you choose" → true
"tech and healthcare" → false
"1,2,3" → false
"all sectors" → false
"technology" → false

Answer (true or false):"""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10
        )
        
        answer = response.choices[0].message.content.strip().lower()
        return answer == "true"
        
    except Exception:
        return False


def collect_sector_preferences(suggested_sectors: List[str]) -> List[str]:
    """Collect sector/industry preferences from user"""
    llm_client = get_llm_client()
    
    print("\n[STEP 2: Sector Preferences]")
    
    if suggested_sectors:
        print(f"\nBased on your goals, I suggest analyzing these sectors:")
        print(f"  {', '.join(suggested_sectors)}")
        print("\nYou can use these suggestions or choose your own sectors.")
    
    print("\nAvailable sectors:")
    for idx, sector in enumerate(AVAILABLE_SECTORS, 1):
        marker = " (suggested)" if sector in suggested_sectors else ""
        print(f"  {idx:2d}. {sector}{marker}")
    
    if llm_client:
        print("  ✓ Natural language - describe any way you want:")
        print("    'tech and pharma' / 'banks' / 'renewable energy and EVs'")
        print("    'defensive stocks' / 'growth sectors' / 'all but energy'")
        if suggested_sectors:
            print("  ✓ Build on suggestions: 'suggested plus energy and materials'")
    
    while True:
        response = input("\nYour choice: ").strip()
        
        # Use suggested sectors if available and user presses Enter
        if not response and suggested_sectors:
            print(f"  -> Using suggested sectors: {', '.join(suggested_sectors)}")
            return suggested_sectors
        
        response_lower = response.lower()
        
        # Check if user is delegating the decision (using LLM)
        if llm_client and is_delegating_decision(llm_client, response, "sector selection"):
            if suggested_sectors:
                print(f"  -> Great! I'll use the suggested sectors based on your goals:")
                print(f"     {', '.join(suggested_sectors)}")
                return suggested_sectors
            else:
                # No suggestions available, use diversified approach
                default_sectors = ["technology", "healthcare", "financial-services", "consumer", "industrials"]
                print(f"  -> I'll select a diversified mix of sectors:")
                print(f"     {', '.join(default_sectors)}")
                return default_sectors
        
        # Analyze all sectors
        if response_lower == "all":
            print(f"  -> Analyzing all {len(AVAILABLE_SECTORS)} sectors")
            return AVAILABLE_SECTORS.copy()
        
        # Check for "suggested + X" pattern
        if suggested_sectors and any(keyword in response_lower for keyword in ["suggested", "suggest", "recommendation"]):
            # Parse what to add to suggested sectors
            additional_sectors = []
            
            if llm_client:
                # Extract what to add beyond suggested sectors
                additional_text = response_lower
                for keyword in ["suggested", "suggestions", "recommended", "recommendations"]:
                    additional_text = additional_text.replace(keyword, "")
                for connector in ["plus", "and", "also", "with", "add", "include"]:
                    additional_text = additional_text.replace(connector, "")
                
                additional_text = additional_text.strip()
                
                if additional_text:
                    # Parse the additional sectors
                    additional_sectors = parse_sectors_with_llm(llm_client, additional_text)
                    
                    if additional_sectors:
                        # Remove sectors already in suggested
                        additional_sectors = [s for s in additional_sectors if s not in suggested_sectors]
            
            # Combine suggested + additional
            combined_sectors = suggested_sectors.copy()
            if additional_sectors:
                combined_sectors.extend(additional_sectors)
                print(f"\n  ✓ Parsed your request:")
                print(f"    • Suggested sectors: {', '.join(suggested_sectors)}")
                print(f"    • Plus additional: {', '.join(additional_sectors)}")
                print(f"    • Total: {len(combined_sectors)} sectors")
                
                confirm = input("\n  Is this correct? (yes/no): ").strip().lower()
                if confirm in ["yes", "y", ""]:
                    return combined_sectors
                else:
                    print("  Let's try again...")
                    continue
            else:
                # No additional sectors found, just use suggested
                print(f"  -> Using suggested sectors: {', '.join(suggested_sectors)}")
                return suggested_sectors
        
        # Try LLM parsing for natural language (now with broader understanding)
        if llm_client and not response[0].isdigit():
            parsed_sectors = parse_sectors_with_llm(llm_client, response)
            
            if parsed_sectors:
                print(f"\n  ✓ Understood your request:")
                print(f"    • Sectors: {', '.join(parsed_sectors)}")
                print(f"    • Total: {len(parsed_sectors)} sectors")
                
                confirm = input("\n  Is this correct? (yes/no): ").strip().lower()
                if confirm in ["yes", "y", ""]:
                    return parsed_sectors
                else:
                    print("\n  Let's try again. You can:")
                    print("    - Rephrase your request")
                    print("    - Use sector numbers instead (e.g., '1,2,5')")
                    print("    - Type specific sector names")
                    continue
        
        # Parse sector numbers
        if response[0].isdigit() or ',' in response:
            try:
                selected_indices = [int(x.strip()) for x in response.split(",")]
                selected_sectors = []
                
                for idx in selected_indices:
                    if 1 <= idx <= len(AVAILABLE_SECTORS):
                        selected_sectors.append(AVAILABLE_SECTORS[idx - 1])
                    else:
                        raise ValueError(f"Invalid sector number: {idx}")
                
                if not selected_sectors:
                    print("  [!] Please select at least one sector")
                    continue
                
                print(f"\n  ✓ Selected {len(selected_sectors)} sectors:")
                print(f"    • {', '.join(selected_sectors)}")
                
                confirm = input("\n  Proceed with these? (yes/no): ").strip().lower()
                if confirm in ["yes", "y", ""]:
                    return selected_sectors
                else:
                    print("  Let's try again...")
                    continue
                
            except (ValueError, IndexError) as e:
                print(f"  [!] Could not parse numbers. Valid range: 1-{len(AVAILABLE_SECTORS)}")
                continue
        
        # If nothing worked
        print("  [!] Couldn't understand that input. Try:")
        print("      - Natural language: 'tech and healthcare'")
        print("      - Numbers: '1,2,5'")
        print("      - 'all' for all sectors")


def collect_risk_tolerance() -> str:
    """Collect risk tolerance (mandatory)"""
    llm_client = get_llm_client()
    
    print("\n[STEP 3: Risk Tolerance]")
    print("\nWhat is your risk tolerance? (Required)")
    print("  1. Low    - Prefer stable, low-volatility investments")
    print("  2. Medium - Balanced risk/reward profile")
    print("  3. High   - Comfortable with volatility for higher potential returns")
    
    while True:
        response = input("\nYour risk tolerance: ").strip().lower()
        
        # Try direct match first
        if response in ["low", "medium", "high"]:
            print(f"  -> Risk tolerance: {response.upper()}")
            return response
        
        # Try number mapping
        if response in ["1", "2", "3"]:
            risk_map = {"1": "low", "2": "medium", "3": "high"}
            risk = risk_map[response]
            print(f"  -> Risk tolerance: {risk.upper()}")
            return risk
        
        # Try LLM parsing
        if llm_client:
            parsed_risk = parse_with_llm(
                llm_client,
                response,
                "Risk tolerance level for investing",
                RISK_TOLERANCE_LEVELS
            )
            
            if parsed_risk and len(parsed_risk) == 1:
                risk = parsed_risk[0]
                print(f"  -> Understood: {risk.upper()} risk tolerance")
                confirm = input("  Is this correct? (yes/no): ").strip().lower()
                if confirm in ["yes", "y", ""]:
                    return risk
                else:
                    print("  Let's try again...")
                    continue
        
        print("  [!] Please specify low, medium, or high (or enter 1-3)")


def parse_yes_no(response: str) -> Optional[bool]:
    """Semantically parse yes/no responses using LLM.
    
    Returns:
        True for yes/affirmative
        False for no/negative
        None if uncertain/unclear
    """
    response = response.strip().lower()
    
    # First check exact matches for speed
    if response in ["yes", "y", "yep", "yeah", "yea", "sure", "ok", "okay", "correct", "right", "affirmative", "proceed", "confirm"]:
        return True
    if response in ["no", "n", "nope", "nah", "negative", "incorrect", "wrong", "cancel"]:
        return False
    
    # Use LLM for semantic understanding of ambiguous responses
    llm_client = get_llm_client()
    if not llm_client:
        return None  # Uncertain without LLM
    
    try:
        prompt = f"""Classify this response as yes, no, or unclear.

User response: "{response}"

Classify as:
- "yes" if the user is affirming, agreeing, or saying positive (examples: yeah, yea, sure, ok, correct, right, affirmative, yup, uh-huh, definitely, absolutely)
- "no" if the user is declining, disagreeing, or saying negative (examples: nah, nope, negative, wrong, incorrect, nay, nuh-uh)
- "unclear" if you cannot confidently determine yes or no, or if the response is ambiguous

Return ONLY one word: yes, no, or unclear"""

        llm_response = llm_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10
        )
        
        classification = llm_response.choices[0].message.content.strip().lower()
        
        if classification == "yes":
            return True
        elif classification == "no":
            return False
        else:
            return None  # Unclear
            
    except Exception as e:
        if os.getenv("DEBUG_CHATBOT"):
            print(f"[DEBUG] Yes/No parsing error: {e}")
        return None  # Uncertain on error


def confirm_preferences(goals: List[str], sectors: List[str], risk_tolerance: str) -> bool:
    """Display summary and ask for confirmation"""
    print("\n" + "="*80)
    print("PREFERENCES SUMMARY")
    print("="*80)
    
    if goals:
        goal_names = [INVESTMENT_GOALS[g]["name"] for g in goals]
        print(f"\nInvestment Goals: {', '.join(goal_names)}")
    else:
        print("\nInvestment Goals: Exploratory (no specific goals)")
    
    print(f"Sectors to Analyze: {', '.join(sectors)} ({len(sectors)} total)")
    print(f"Risk Tolerance: {risk_tolerance.upper()}")
    
    print("\n" + "-"*80)
    
    while True:
        response = input("\nProceed with this analysis? (yes/no): ").strip()
        
        result = parse_yes_no(response)
        
        if result is True:
            return True
        elif result is False:
            return False
        else:
            print("  [!] I'm not sure what you mean. Please answer 'yes' or 'no'.")


def show_goal_suggestions():
    """Display all available investment goals as suggestions"""
    print("\n" + "="*80)
    print("AVAILABLE INVESTMENT GOALS")
    print("="*80)
    print("\nHere are the investment goals you can choose from:\n")
    
    for idx, (key, info) in enumerate(INVESTMENT_GOALS.items(), 1):
        print(f"{idx}. {info['name']}")
        print(f"   {info['description']}")
        print(f"   Suggested sectors: {', '.join(info['suggested_sectors'])}")
        print()
    
    print("You can also choose 'Exploratory' mode with no specific goals.")
    print("="*80)


def run_chatbot() -> Optional[Dict]:
    """
    Run the complete chatbot conversation flow.
    
    Returns:
        Dict with keys: 'goals', 'sectors', 'risk_tolerance'
        None if user cancels
    """
    display_welcome()
    
    llm_client = get_llm_client()
    
    # Initialize state variables OUTSIDE loop to persist across iterations
    goals = None
    sectors = None
    risk_tolerance = None
    shown_understood = False  # Track if we've shown what we understood
    
    # Conversation loop (allow restart if user rejects confirmation)
    while True:
        # Start with open-ended question
        initial_input = input("What are you looking for? ").strip()
        
        # Check if user is asking for ideas/suggestions using LLM for semantic understanding
        if initial_input:
            initial_lower = initial_input.lower()
            
            # Check if asking for examples
            if any(keyword in initial_lower for keyword in ["example", "sample", "show me example", "demo"]):
                print("\n" + "="*80)
                print("EXAMPLE INPUTS")
                print("="*80)
                print("\nHere are some example inputs you can try:\n")
                print("  • 'I want growth in technology with medium risk'")
                print("  • 'ESG investing in healthcare and energy sectors'")
                print("  • 'Low risk defensive strategy'")
                print("  • 'Income focused on utilities and consumer staples, low risk'")
                print("  • 'Technology and financial services with high risk tolerance'")
                print("\nYou can also ask for:")
                print("  • 'ideas' or 'help' - see available goal options")
                print("  • 'what sectors' - see all available sectors")
                print("="*80)
                continue  # Restart the loop to ask the question again
            
            # Basic keyword check for goals (fast path)
            asking_for_goal_help = any(keyword in initial_lower for keyword in [
                "ideas", "suggestions", "help", "what goals", "what options", 
                "what can", "show me", "list goals", "available goals",
                "don't know", "not sure", "unsure"
            ])
            
            # Use LLM to semantically detect if asking for sector information
            asking_for_sector_help = False
            asking_what_needed = False
            if llm_client:
                try:
                    prompt = f"""Is the user asking to see available sectors or sector options?

User input: "{initial_input}"

Answer with ONLY "true" or "false".

Examples:
"what sectors are available" → true
"show me sectors" → true
"which sectors can I choose" → true
"list all sectors" → true
"what are my sector options" → true
"sector ideas" → true
"suggested sectors" → true
"what sectors do you suggest" → true
"I want tech stocks" → false
"growth investing" → false
"help" → false

Answer (true or false):"""

                    response = llm_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0,
                        max_tokens=10
                    )
                    
                    answer = response.choices[0].message.content.strip().lower()
                    asking_for_sector_help = (answer == "true")
                    
                    # Also check if asking what information is needed
                    if not asking_for_sector_help:
                        prompt2 = f"""Is the user asking what information you need or what else is required?

User input: "{initial_input}"

Answer with ONLY "true" or "false".

Examples:
"what else do you need" → true
"what else do you need to know" → true
"what information do you need" → true
"what's missing" → true
"what do you need from me" → true
"anything else" → true
"esg low risk" → false
"technology" → false

Answer (true or false):"""
                        resp2 = llm_client.chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=[{"role": "user", "content": prompt2}],
                            temperature=0,
                            max_tokens=10
                        )
                        asking_what_needed = (resp2.choices[0].message.content.strip().lower() == "true")
                except Exception:
                    # Fallback to keyword matching if LLM fails
                    asking_for_sector_help = any(keyword in initial_lower for keyword in [
                        "what sectors", "show sectors", "list sectors", "available sectors",
                        "which sectors", "sector options"
                    ])
                    asking_what_needed = any(keyword in initial_lower for keyword in [
                        "what else", "what do you need", "what information", "what's missing"
                    ])
            else:
                # No LLM available, use keyword matching
                asking_for_sector_help = any(keyword in initial_lower for keyword in [
                    "what sectors", "show sectors", "list sectors", "available sectors",
                    "which sectors", "sector options"
                ])
            
            if asking_for_goal_help and not asking_for_sector_help:
                show_goal_suggestions()
                print("\nNow that you've seen the options, let's discuss your goals!")
                continue  # Restart the loop to ask the question again
            
            if asking_what_needed:
                # User is asking what info is needed - tell them specifically
                missing = []
                if sectors is None:
                    missing.append("which sectors to analyze")
                if risk_tolerance is None:
                    missing.append("your risk tolerance (low/medium/high)")
                
                if missing:
                    print(f"\n  → I still need to know: {' and '.join(missing)}")
                else:
                    print("\n  → I have all the information I need! Let me confirm...")
                continue
            
            if asking_for_sector_help:
                print("\n" + "="*80)
                print("AVAILABLE SECTORS")
                print("="*80)
                print("\nAll available sectors for analysis:\n")
                for idx, sector in enumerate(AVAILABLE_SECTORS, 1):
                    print(f"  {idx:2d}. {sector}")
                
                # Show suggested sectors if goals are known
                if goals:
                    suggested = suggest_sectors_from_goals(goals)
                    if suggested:
                        print(f"\n  💡 Based on your goals, I suggest: {', '.join(suggested)}")
                
                print("\n" + "="*80)
                print("\nNow tell me which sectors you'd like to analyze!")
                continue  # Restart the loop to ask the question again
        
        # Parse initial query
        if initial_input:
            print("\n  Analyzing your request...")
            parsed = parse_initial_query(initial_input)
            
            # Incrementally update state (don't replace, merge)
            if parsed.get("goals"):
                goals = parsed.get("goals")
            if parsed.get("sectors"):
                sectors = parsed.get("sectors")
            if parsed.get("risk_tolerance"):
                risk_tolerance = parsed.get("risk_tolerance")
            
            # Show what was understood from THIS input
            understood = []
            
            if parsed.get("goals"):
                goal_names = [INVESTMENT_GOALS[g]["name"] for g in parsed.get("goals")]
                understood.append(f"Goals: {', '.join(goal_names)}")
            
            if parsed.get("sectors"):
                understood.append(f"Sectors: {', '.join(parsed.get('sectors'))}")
            
            if parsed.get("risk_tolerance"):
                understood.append(f"Risk: {parsed.get('risk_tolerance').upper()}")
            
            if understood:
                print("\n  ✓ Understood:")
                for item in understood:
                    print(f"    • {item}")
                shown_understood = True  # Mark that we've shown info
                
                # If incomplete, prompt for what's missing instead of looping
                all_complete = (sectors is not None and risk_tolerance is not None)
                if not all_complete:
                    missing = []
                    if sectors is None:
                        missing.append("sectors")
                    if risk_tolerance is None:
                        missing.append("risk tolerance")
                    
                    if missing:
                        print(f"\n  → What about {' and '.join(missing)}?")
                    continue  # Ask again for remaining info
            else:
                # Nothing understood from this input - check if it's an affirmative
                if shown_understood and initial_lower in ["yes", "y", "yep", "yeah", "yea", "ok", "okay", "correct", "right"]:
                    # User is confirming what we showed before - check if we have everything
                    if sectors is not None and risk_tolerance is not None:
                        break  # We have everything, proceed to confirmation
                    else:
                        # Still missing something
                        missing = []
                        if sectors is None:
                            missing.append("sectors")
                        if risk_tolerance is None:
                            missing.append("risk tolerance")
                        print(f"\n  → I still need to know your {' and '.join(missing)}.")
                        continue
                # Otherwise, couldn't parse - will loop back to ask again
        
        # If we have everything from parsing, proceed to final confirmation
        if sectors is not None and risk_tolerance is not None:
            break  # Exit the initial question loop, skip step-by-step
        
        # Ask follow-up questions for missing information
        print("\n" + "-"*80)
        
        # Step 1: Investment Goals (if not provided)
        if goals is None:
            goals = collect_investment_goals()
        else:
            # Confirm parsed values
            print("\n[Investment Goals]")
            goal_names = [INVESTMENT_GOALS[g]["name"] for g in goals]
            print(f"  Understood: {', '.join(goal_names)}")
            
            while True:
                response = input("  Is this correct? (yes/no): ").strip()
                result = parse_yes_no(response)
                
                if result is True:
                    break  # Confirmed, move on
                elif result is False:
                    goals = collect_investment_goals()
                    break
                else:
                    print("  [!] I'm not sure what you mean. Please answer 'yes' or 'no'.")
        
        # Step 2: Sector Selection (if not provided)
        if sectors is None:
            suggested_sectors = suggest_sectors_from_goals(goals)
            sectors = collect_sector_preferences(suggested_sectors)
        else:
            # Confirm parsed values
            print("\n[Sectors to Analyze]")
            print(f"  Understood: {', '.join(sectors)} ({len(sectors)} total)")
            
            while True:
                response = input("  Is this correct? (yes/no): ").strip()
                result = parse_yes_no(response)
                
                if result is True:
                    break  # Confirmed, move on
                elif result is False:
                    suggested_sectors = suggest_sectors_from_goals(goals)
                    sectors = collect_sector_preferences(suggested_sectors)
                    break
                else:
                    print("  [!] I'm not sure what you mean. Please answer 'yes' or 'no'.")
        
        # Step 3: Risk Tolerance (mandatory, must be specified)
        if risk_tolerance is None:
            risk_tolerance = collect_risk_tolerance()
        else:
            # Confirm parsed value
            print("\n[Risk Tolerance]")
            print(f"  Understood: {risk_tolerance.upper()}")
            
            while True:
                response = input("  Is this correct? (yes/no): ").strip()
                result = parse_yes_no(response)
                
                if result is True:
                    break  # Confirmed, move on
                elif result is False:
                    risk_tolerance = collect_risk_tolerance()
                    break
                else:
                    print("  [!] I'm not sure what you mean. Please answer 'yes' or 'no'.")
        
        # Final Confirmation
        if confirm_preferences(goals, sectors, risk_tolerance):
            print("\n" + "="*80)
            print("Starting research analysis...")
            print("="*80 + "\n")
            
            return {
                "goals": goals,
                "sectors": sectors,
                "risk_tolerance": risk_tolerance
            }
        else:
            print("\nLet's start over...")
            print("-"*80)


if __name__ == "__main__":
    # Test the chatbot
    result = run_chatbot()
    if result:
        print("\n[Chatbot Output]")
        print(f"Goals: {result['goals']}")
        print(f"Sectors: {result['sectors']}")
        print(f"Risk Tolerance: {result['risk_tolerance']}")
    else:
        print("\nChatbot cancelled")
