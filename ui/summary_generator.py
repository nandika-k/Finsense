"""
LLM-based summary generator for research findings.

Uses Groq LLM with low temperature to generate summaries based strictly on 
MCP server outputs without hallucination.
"""

import os
import json
from typing import Dict, List, Any
from dotenv import load_dotenv

load_dotenv()

try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False
    Groq = None


def get_groq_client():
    """Get Groq client if API key is available"""
    if not HAS_GROQ:
        return None
    
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    
    return Groq(api_key=api_key)


def generate_sector_goal_summary(research_data: Dict[str, Any], preferences: Dict[str, Any]) -> str:
    """
    Generate a brief summary about sectors and their correlation to investment goals.
    Uses actual research data - no hallucination.
    """
    client = get_groq_client()
    if not client:
        return "[LLM summary unavailable - set GROQ_API_KEY to enable]"
    
    # Extract relevant data from research
    sectors = list(research_data.get("sector_deep_dives", {}).keys())
    goals = preferences.get("goals", [])
    goal_recs = research_data.get("goal_based_recommendations", {})
    
    # Build data context for LLM
    sector_data_summary = {}
    for sector, data in research_data.get("sector_deep_dives", {}).items():
        perf = data.get("market_performance", {})
        risk = data.get("risk_profile", {})
        
        sector_data_summary[sector] = {
            "performance_1m": perf.get("performance_1m", "N/A"),
            "performance_3m": perf.get("performance_3m", "N/A"),
            "volatility": risk.get("annualized_volatility", "N/A"),
            "risk_level": risk.get("percentile", "N/A")
        }
    
    # Goal names mapping
    goal_names_map = {
        "growth": "Growth (capital appreciation)",
        "income": "Income (stable returns)",
        "esg": "ESG (environmental/social responsibility)",
        "value": "Value (undervalued opportunities)",
        "defensive": "Defensive (downside protection)",
        "diversified": "Diversified (risk spreading)"
    }
    
    goal_names = [goal_names_map.get(g, g) for g in goals]
    
    prompt = f"""Based ONLY on the following factual data from market research, write a brief 2-3 sentence summary about how the analyzed sectors align with the investor's goals.

INVESTOR GOALS: {', '.join(goal_names) if goal_names else 'Exploratory (no specific goals)'}

SECTORS ANALYZED: {', '.join(sectors)}

SECTOR PERFORMANCE DATA:
{json.dumps(sector_data_summary, indent=2)}

TOP RECOMMENDATIONS (if available):
{json.dumps(goal_recs.get('top_picks', [])[:3], indent=2)}

Instructions:
- Reference ONLY the specific data provided above
- Mention which sectors best match the stated goals based on the performance and risk metrics
- Keep it brief (2-3 sentences maximum)
- Do NOT make up or infer information not present in the data
- If no goals specified, state that analysis was exploratory across all sectors"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # Very low temperature to minimize hallucination
            max_tokens=200
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        return f"[Error generating summary: {e}]"


def generate_risk_summary_with_citations(research_data: Dict[str, Any]) -> str:
    """
    Generate a summary of key risks with citations to actual news articles.
    Only references risks that were actually identified in the data.
    """
    client = get_groq_client()
    if not client:
        return "[LLM risk summary unavailable - set GROQ_API_KEY to enable]"
    
    # Extract risk themes from all sectors
    risk_themes = {}
    article_citations = {}
    
    for sector, data in research_data.get("sector_deep_dives", {}).items():
        news = data.get("news_analysis", {})
        if "error" not in news and news:
            risks = news.get("identified_risks", [])
            if risks:
                risk_themes[sector] = []
                for risk_item in risks[:3]:  # Top 3 risks per sector
                    risk_text = risk_item.get("risk", "N/A")
                    category = risk_item.get("category", "N/A")
                    severity = risk_item.get("severity", "N/A")
                    sources = risk_item.get("sources", [])
                    
                    risk_themes[sector].append({
                        "risk": risk_text,
                        "category": category,
                        "severity": severity,
                        "article_count": len(sources)
                    })
                    
                    # Collect article citations
                    for article in sources[:2]:  # Max 2 articles per risk
                        title = article.get("title", "")
                        url = article.get("url", "")
                        if title and url:
                            if sector not in article_citations:
                                article_citations[sector] = []
                            article_citations[sector].append({
                                "title": title[:100],  # Truncate long titles
                                "url": url,
                                "related_risk": category
                            })
    
    if not risk_themes:
        return "No significant risks identified in recent news analysis."
    
    prompt = f"""Based ONLY on the following risk data extracted from real news articles, write a brief summary (3-4 sentences) highlighting the most significant risks across sectors.

IDENTIFIED RISKS BY SECTOR:
{json.dumps(risk_themes, indent=2)}

ARTICLE CITATIONS AVAILABLE:
{json.dumps(article_citations, indent=2)}

Instructions:
- Summarize the TOP 2-3 most significant risks based on severity and frequency
- Reference ONLY risks that appear in the data above
- Mention which sectors are affected
- Keep it factual and concise (3-4 sentences)
- Do NOT invent or infer risks not present in the data"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=250
        )
        
        summary = response.choices[0].message.content.strip()
        
        # Add article citations at the end
        if article_citations:
            summary += "\n\n📰 Related Articles:"
            for sector, articles in list(article_citations.items())[:3]:  # Max 3 sectors
                for article in articles[:2]:  # Max 2 articles per sector
                    summary += f"\n  • [{sector.upper()}] {article['title']}"
                    if article['url']:
                        summary += f"\n    {article['url']}"
        
        return summary
    
    except Exception as e:
        return f"[Error generating risk summary: {e}]"
