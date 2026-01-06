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
    Parse an initial open-ended query for goals, sectors, and risk tolerance.
    
    Returns dict with:
        - goals: List[str] or None
        - sectors: List[str] or None
        - risk_tolerance: str or None
    """
    llm_client = get_llm_client()
    
    if not llm_client:
        # Fallback: basic keyword matching without LLM
        result = {"goals": None, "sectors": None, "risk_tolerance": None}
        
        # Check for risk tolerance keywords
        user_lower = user_input.lower()
        if any(word in user_lower for word in ["low risk", "conservative", "safe", "stable"]):
            result["risk_tolerance"] = "low"
        elif any(word in user_lower for word in ["high risk", "aggressive", "growth"]):
            result["risk_tolerance"] = "high"
        elif any(word in user_lower for word in ["medium risk", "moderate", "balanced"]):
            result["risk_tolerance"] = "medium"
        
        return result
    
    # Use LLM for comprehensive parsing
    try:
        prompt = f"""Parse this investment query and extract investment goals, sectors, and risk tolerance.

AVAILABLE INVESTMENT GOALS: {', '.join(INVESTMENT_GOALS.keys())}
AVAILABLE SECTORS: {', '.join(AVAILABLE_SECTORS)}
RISK TOLERANCE LEVELS: low, medium, high

User query: "{user_input}"

Extract and return ONLY a JSON object with these fields (use null if not mentioned):
{{
  "goals": [list of goal keys that match the query, or null],
  "sectors": [list of sector names that match the query, or null],
  "risk_tolerance": "low" or "medium" or "high" or null
}}

Examples:
Query: "I want growth in tech and healthcare with low risk"
Result: {{"goals": ["growth"], "sectors": ["technology", "healthcare"], "risk_tolerance": "low"}}

Query: "ESG investing"
Result: {{"goals": ["esg"], "sectors": null, "risk_tolerance": null}}

Query: "Analyze everything"
Result: {{"goals": null, "sectors": null, "risk_tolerance": null}}

JSON object:"""

        response = llm_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=300
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
            "risk_tolerance": None
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
        return {"goals": None, "sectors": None, "risk_tolerance": None}


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
"tech and healthcare" → false
"1,2,3" → false
"all sectors" → false

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
    
    print("\nHow to select:")
    if llm_client:
        print("  ✓ Natural language - describe any way you want:")
        print("    'tech and pharma' / 'banks' / 'renewable energy and EVs'")
        print("    'defensive stocks' / 'growth sectors' / 'all but energy'")
        if suggested_sectors:
            print("  ✓ Build on suggestions: 'suggested plus energy and materials'")
    print("  ✓ Numbers: '1,2,5' or just '1'")
    print("  ✓ Type 'all' for all sectors")
    if suggested_sectors:
        print("  ✓ Press Enter to use suggested sectors")
    
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
        response = input("\nProceed with this analysis? (yes/no): ").strip().lower()
        if response in ["yes", "y"]:
            return True
        elif response in ["no", "n"]:
            return False
        else:
            print("  [!] Please enter 'yes' or 'no'")


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
    
    # Conversation loop (allow restart if user rejects confirmation)
    while True:
        # Start with open-ended question
        print("\n" + "="*80)
        print("TELL ME ABOUT YOUR INVESTMENT INTERESTS")
        print("="*80)
        print("\nYou can tell me everything at once, or we'll go step-by-step.")
        print("\nExamples:")
        print("  • 'I want growth in technology with medium risk'")
        print("  • 'ESG investing in healthcare and energy sectors'")
        print("  • 'Low risk defensive strategy'")
        print("  • Type 'ideas' or 'help' to see available goal options")
        print("  • Just press Enter to go through each question\n")
        
        initial_input = input("What are you looking for? ").strip()
        
        # Check if user is asking for ideas/suggestions about goals
        if initial_input:
            asking_for_help = any(keyword in initial_input.lower() for keyword in [
                "ideas", "suggestions", "help", "what goals", "what options", 
                "what can", "show me", "list goals", "available goals",
                "don't know", "not sure", "unsure"
            ])
            
            if asking_for_help:
                show_goal_suggestions()
                print("\nNow that you've seen the options, let's try again!")
                continue  # Restart the loop to ask the question again
        
        # Parse initial query
        if initial_input:
            print("\n  Analyzing your request...")
            parsed = parse_initial_query(initial_input)
            
            goals = parsed.get("goals")
            sectors = parsed.get("sectors")
            risk_tolerance = parsed.get("risk_tolerance")
            
            # Show what was understood
            understood = []
            if goals:
                goal_names = [INVESTMENT_GOALS[g]["name"] for g in goals]
                understood.append(f"Goals: {', '.join(goal_names)}")
            if sectors:
                understood.append(f"Sectors: {', '.join(sectors)}")
            if risk_tolerance:
                understood.append(f"Risk: {risk_tolerance.upper()}")
            
            if understood:
                print("\n  ✓ Understood:")
                for item in understood:
                    print(f"    • {item}")
        else:
            goals = None
            sectors = None
            risk_tolerance = None
        
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
            correct = input("  Is this correct? (yes/no): ").strip().lower()
            if correct in ["no", "n"]:
                goals = collect_investment_goals()
        
        # Step 2: Sector Selection (if not provided)
        if sectors is None:
            suggested_sectors = suggest_sectors_from_goals(goals)
            sectors = collect_sector_preferences(suggested_sectors)
        else:
            # Confirm parsed values
            print("\n[Sectors to Analyze]")
            print(f"  Understood: {', '.join(sectors)} ({len(sectors)} total)")
            correct = input("  Is this correct? (yes/no): ").strip().lower()
            if correct in ["no", "n"]:
                suggested_sectors = suggest_sectors_from_goals(goals)
                sectors = collect_sector_preferences(suggested_sectors)
        
        # Step 3: Risk Tolerance (mandatory, must be specified)
        if risk_tolerance is None:
            risk_tolerance = collect_risk_tolerance()
        else:
            # Confirm parsed value
            print("\n[Risk Tolerance]")
            print(f"  Understood: {risk_tolerance.upper()}")
            correct = input("  Is this correct? (yes/no): ").strip().lower()
            if correct in ["no", "n"]:
                risk_tolerance = collect_risk_tolerance()
        
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
