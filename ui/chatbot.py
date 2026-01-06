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
        if suggested_sectors:
            print("  - Add to suggestions (e.g., 'suggested plus energy')")
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
        
        # Check for "suggested + X" pattern
        if suggested_sectors and any(keyword in response for keyword in ["suggested", "suggest", "recommendation"]):
            # Parse what to add to suggested sectors
            additional_sectors = []
            
            if llm_client:
                # Use LLM to extract additional sectors from phrases like:
                # "suggested plus energy"
                # "suggested but also add tech and healthcare"
                # "recommendations and also financial-services"
                prompt = f"""The user wants the suggested sectors PLUS some additional sectors.

Suggested sectors: {', '.join(suggested_sectors)}
Available additional sectors: {', '.join([s for s in AVAILABLE_SECTORS if s not in suggested_sectors])}

User said: "{response}"

Extract ONLY the additional sectors the user wants to add (not the suggested ones they already have).
Return a JSON array of sector names to ADD to the suggestions.

Examples:
"suggested plus energy" -> ["energy"]
"suggested but also tech and healthcare" -> ["technology", "healthcare"]
"recommendations and materials" -> ["materials"]

JSON array:"""
                
                try:
                    llm_response = llm_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0,
                        max_tokens=150
                    )
                    
                    content = llm_response.choices[0].message.content.strip()
                    
                    # Clean markdown
                    if content.startswith("```"):
                        lines = content.split("\n")
                        content = "\n".join(lines[1:-1]).strip()
                    if content.startswith("json"):
                        content = content[4:].strip()
                    
                    additional_parsed = json.loads(content)
                    if isinstance(additional_parsed, list):
                        additional_sectors = [s for s in additional_parsed if s in AVAILABLE_SECTORS and s not in suggested_sectors]
                
                except Exception as e:
                    if os.getenv("DEBUG_CHATBOT"):
                        print(f"[DEBUG] Error parsing additional sectors: {e}")
            
            # Combine suggested + additional
            combined_sectors = suggested_sectors.copy()
            if additional_sectors:
                combined_sectors.extend(additional_sectors)
                print(f"  -> Suggested sectors: {', '.join(suggested_sectors)}")
                print(f"  -> Plus additional: {', '.join(additional_sectors)}")
                print(f"  -> Total: {len(combined_sectors)} sectors")
                
                confirm = input("  Is this correct? (yes/no): ").strip().lower()
                if confirm in ["yes", "y", ""]:
                    return combined_sectors
                else:
                    print("  Let's try again...")
                    continue
            else:
                # No additional sectors found, just use suggested
                print(f"  -> Using suggested sectors: {', '.join(suggested_sectors)}")
                return suggested_sectors
        
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
            # Confirm and allow modification
            print("\n[Investment Goals]")
            goal_names = [INVESTMENT_GOALS[g]["name"] for g in goals]
            print(f"  Current: {', '.join(goal_names)}")
            modify = input("  Change these? (yes/no): ").strip().lower()
            if modify in ["yes", "y"]:
                goals = collect_investment_goals()
        
        # Step 2: Sector Selection (if not provided)
        if sectors is None:
            suggested_sectors = suggest_sectors_from_goals(goals)
            sectors = collect_sector_preferences(suggested_sectors)
        else:
            # Confirm and allow modification
            print("\n[Sectors to Analyze]")
            print(f"  Current: {', '.join(sectors)} ({len(sectors)} total)")
            modify = input("  Change these? (yes/no): ").strip().lower()
            if modify in ["yes", "y"]:
                suggested_sectors = suggest_sectors_from_goals(goals)
                sectors = collect_sector_preferences(suggested_sectors)
        
        # Step 3: Risk Tolerance (mandatory, must be specified)
        if risk_tolerance is None:
            risk_tolerance = collect_risk_tolerance()
        else:
            # Confirm and allow modification
            print("\n[Risk Tolerance]")
            print(f"  Current: {risk_tolerance.upper()}")
            modify = input("  Change this? (yes/no): ").strip().lower()
            if modify in ["yes", "y"]:
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
