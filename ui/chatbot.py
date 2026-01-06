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
    
    print("\nOptions:")
    if llm_client:
        print("  - Describe sectors (e.g., 'tech and healthcare')")
    print("  - Enter sector numbers (comma-separated, e.g., '1,2,5')")
    print("  - Type 'all' to analyze all sectors")
    if suggested_sectors:
        print("  - Press Enter to use suggested sectors")
    
    while True:
        response = input("\nYour choice: ").strip().lower()
        
        # Use suggested sectors if available and user presses Enter
        if not response and suggested_sectors:
            print(f"  -> Using suggested sectors: {', '.join(suggested_sectors)}")
            return suggested_sectors
        
        # Analyze all sectors
        if response == "all":
            print(f"  -> Analyzing all {len(AVAILABLE_SECTORS)} sectors")
            return AVAILABLE_SECTORS.copy()
        
        # Try LLM parsing for natural language
        if llm_client and not response[0].isdigit():
            parsed_sectors = parse_with_llm(
                llm_client,
                response,
                "Sector/industry selection for financial analysis",
                AVAILABLE_SECTORS
            )
            
            if parsed_sectors:
                print(f"  -> Understood: {', '.join(parsed_sectors)} ({len(parsed_sectors)} sectors)")
                confirm = input("  Is this correct? (yes/no): ").strip().lower()
                if confirm in ["yes", "y", ""]:
                    return parsed_sectors
                else:
                    print("  Let's try again...")
                    continue
        
        # Parse sector numbers
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
            
            print(f"  -> Selected {len(selected_sectors)} sectors: {', '.join(selected_sectors)}")
            return selected_sectors
            
        except (ValueError, IndexError) as e:
            print(f"  [!] Could not parse input. Try numbers, sector names, or 'all'.")


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


def run_chatbot() -> Optional[Dict]:
    """
    Run the complete chatbot conversation flow.
    
    Returns:
        Dict with keys: 'goals', 'sectors', 'risk_tolerance'
        None if user cancels
    """
    display_welcome()
    
    # Conversation loop (allow restart if user rejects confirmation)
    while True:
        # Step 1: Collect goals
        goals = collect_investment_goals()
        
        # Step 2: Suggest and collect sectors
        suggested_sectors = suggest_sectors_from_goals(goals)
        sectors = collect_sector_preferences(suggested_sectors)
        
        # Step 3: Collect risk tolerance (mandatory)
        risk_tolerance = collect_risk_tolerance()
        
        # Confirmation
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
