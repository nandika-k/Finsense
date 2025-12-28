import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio
import sys
import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List
import re
from urllib.parse import quote
from bs4 import BeautifulSoup

# Ensure stdout is unbuffered
sys.stdout.reconfigure(line_buffering=True)

# Only log to file if DEBUG environment variable is set
if os.getenv("MCP_DEBUG"):
    import logging
    from pathlib import Path
    LOG_FILE = Path(__file__).parent / "finsense_news.log"
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, mode='w')]
    )
    logger = logging.getLogger(__name__)
    
    def log(msg):
        logger.debug(msg)
else:
    def log(msg):
        pass

# --- MCP Server Initialization ---
app = Server("finsense-news")

# --- Sector Risk Knowledge Base ---
SECTOR_RISKS = {
    "technology": {
        "supply_chain": [
            "Semiconductor shortages and supply chain disruptions",
            "Dependence on foreign manufacturing (especially Asia)",
            "Component availability issues during geopolitical tensions"
        ],
        "regulatory": [
            "Antitrust regulations and data privacy laws",
            "AI governance and content moderation requirements",
            "International trade restrictions on technology exports"
        ],
        "economic": [
            "Reduced enterprise IT spending during economic downturns",
            "Currency fluctuations affecting international revenue",
            "Interest rate sensitivity for growth valuations"
        ],
        "geopolitical": [
            "US-China tech trade restrictions",
            "Data localization requirements in foreign markets",
            "Sanctions affecting technology exports"
        ],
        "technology": [
            "Rapid technological obsolescence",
            "Cybersecurity breaches and data theft",
            "Disruption from emerging technologies (AI, quantum computing)"
        ]
    },
    "healthcare": {
        "regulatory": [
            "FDA approval processes and drug pricing regulations",
            "Healthcare policy changes (Medicare, Medicaid)",
            "International regulatory compliance requirements"
        ],
        "supply_chain": [
            "Pharmaceutical ingredient supply disruptions",
            "Medical device manufacturing dependencies",
            "Cold chain logistics for biologics and vaccines"
        ],
        "economic": [
            "Healthcare spending cuts during economic downturns",
            "Insurance reimbursement rate changes",
            "Currency impacts on international operations"
        ],
        "geopolitical": [
            "Intellectual property protection in foreign markets",
            "Trade restrictions on medical equipment",
            "Pandemic response and vaccine distribution policies"
        ],
        "technology": [
            "Cybersecurity risks to patient data",
            "Disruption from telemedicine and digital health",
            "Regulatory changes for AI in medical devices"
        ]
    },
    "financial-services": {
        "regulatory": [
            "Banking regulations and capital requirements",
            "Interest rate policy changes by central banks",
            "Anti-money laundering (AML) compliance",
            "Consumer protection regulations"
        ],
        "economic": [
            "Credit defaults during economic recessions",
            "Interest rate sensitivity",
            "Market volatility affecting trading revenue",
            "Loan loss provisions during downturns"
        ],
        "geopolitical": [
            "Sanctions affecting international banking operations",
            "Currency devaluation in emerging markets",
            "Trade war impacts on global finance"
        ],
        "technology": [
            "Cybersecurity threats and data breaches",
            "Fintech disruption and digital banking competition",
            "Regulatory technology (RegTech) compliance costs"
        ],
        "systemic": [
            "Liquidity crises and bank runs",
            "Counterparty risk in derivatives markets",
            "Systemic risk from interconnected financial institutions"
        ]
    },
    "energy": {
        "geopolitical": [
            "Oil supply disruptions from geopolitical conflicts",
            "Sanctions on major oil-producing countries",
            "Pipeline and shipping route disruptions",
            "OPEC production decisions"
        ],
        "economic": [
            "Oil price volatility",
            "Demand destruction during economic recessions",
            "Currency impacts on commodity pricing"
        ],
        "regulatory": [
            "Environmental regulations and carbon pricing",
            "Renewable energy mandates",
            "Drilling and exploration restrictions",
            "Climate change policies"
        ],
        "environmental": [
            "Natural disasters affecting production facilities",
            "Climate change impacts on operations",
            "Environmental cleanup liabilities",
            "Transition risks to renewable energy"
        ],
        "supply_chain": [
            "Refinery capacity constraints",
            "Pipeline infrastructure limitations",
            "Storage capacity during supply gluts"
        ]
    },
    "consumer": {
        "supply_chain": [
            "Trade route disruptions affecting imports",
            "Manufacturing dependencies on low-cost regions",
            "Logistics and shipping delays",
            "Raw material price volatility"
        ],
        "economic": [
            "Consumer spending sensitivity to economic cycles",
            "Discretionary spending cuts during recessions",
            "Inflation impacts on purchasing power",
            "Unemployment affecting demand"
        ],
        "geopolitical": [
            "Trade war tariffs on consumer goods",
            "Currency devaluation in manufacturing countries",
            "Supply chain disruptions from geopolitical tensions"
        ],
        "regulatory": [
            "Product safety regulations",
            "Import tariffs and trade policies",
            "Environmental regulations on packaging"
        ],
        "competitive": [
            "E-commerce disruption of traditional retail",
            "Fast fashion and changing consumer preferences",
            "Brand reputation risks"
        ]
    },
    "consumer-discretionary": {
        "supply_chain": [
            "Trade route disruptions affecting global supply chains",
            "Manufacturing dependencies on Asia",
            "Shipping and logistics bottlenecks",
            "Component shortages"
        ],
        "economic": [
            "High sensitivity to economic downturns",
            "Discretionary spending cuts by consumers",
            "Interest rate sensitivity for big-ticket items",
            "Unemployment impacts on demand"
        ],
        "geopolitical": [
            "Trade war tariffs on consumer goods",
            "Currency fluctuations affecting costs",
            "Supply chain disruptions from geopolitical tensions"
        ],
        "competitive": [
            "E-commerce disruption",
            "Changing consumer preferences",
            "Brand reputation risks"
        ]
    },
    "industrials": {
        "economic": [
            "Cyclical demand tied to GDP growth",
            "Capital spending cuts during recessions",
            "Interest rate sensitivity for equipment financing"
        ],
        "supply_chain": [
            "Raw material price volatility (steel, aluminum, etc.)",
            "Component supply disruptions",
            "Logistics and transportation bottlenecks"
        ],
        "geopolitical": [
            "Trade war impacts on manufacturing",
            "Infrastructure project delays from political uncertainty",
            "Defense spending policy changes"
        ],
        "regulatory": [
            "Environmental regulations",
            "Safety and emissions standards",
            "Infrastructure spending policies"
        ]
    },
    "materials": {
        "economic": [
            "Commodity price volatility",
            "Demand tied to construction and manufacturing cycles",
            "Currency impacts on commodity pricing"
        ],
        "geopolitical": [
            "Trade restrictions on raw materials",
            "Mining rights and resource nationalism",
            "Sanctions affecting commodity exports"
        ],
        "environmental": [
            "Environmental regulations on mining",
            "Climate change impacts on operations",
            "Water usage restrictions"
        ],
        "supply_chain": [
            "Logistics disruptions for bulk commodities",
            "Infrastructure constraints",
            "Energy costs for processing"
        ]
    },
    "real-estate": {
        "economic": [
            "Interest rate sensitivity (mortgage rates)",
            "Economic recession reducing demand",
            "Unemployment affecting property values",
            "Inflation impacts on construction costs"
        ],
        "regulatory": [
            "Zoning and land use regulations",
            "Rent control policies",
            "Tax policy changes (property taxes, deductions)",
            "Environmental regulations"
        ],
        "geopolitical": [
            "Foreign investment restrictions",
            "Currency impacts on international buyers",
            "Trade war effects on commercial real estate"
        ],
        "systemic": [
            "Real estate bubble risks",
            "Commercial real estate oversupply",
            "Retail property disruption from e-commerce"
        ]
    },
    "utilities": {
        "regulatory": [
            "Rate-setting by public utility commissions",
            "Environmental regulations (emissions, renewables)",
            "Nuclear power regulations",
            "Grid modernization requirements"
        ],
        "economic": [
            "Interest rate sensitivity (capital-intensive)",
            "Economic downturn reducing demand",
            "Energy price volatility"
        ],
        "environmental": [
            "Climate change impacts (extreme weather)",
            "Natural disaster damage to infrastructure",
            "Transition to renewable energy",
            "Water scarcity for power generation"
        ],
        "technology": [
            "Grid cybersecurity threats",
            "Distributed energy resources disruption",
            "Smart grid technology adoption"
        ]
    },
    "communications": {
        "regulatory": [
            "Net neutrality regulations",
            "Spectrum allocation policies",
            "Content moderation requirements",
            "Data privacy regulations"
        ],
        "economic": [
            "Consumer spending on telecom services",
            "Enterprise spending on communications",
            "Currency impacts on international operations"
        ],
        "technology": [
            "5G infrastructure deployment costs",
            "Cybersecurity threats",
            "Disruption from new technologies",
            "Network capacity constraints"
        ],
        "competitive": [
            "Market saturation",
            "Price competition",
            "Over-the-top (OTT) service disruption"
        ]
    },
    "consumer-staples": {
        "supply_chain": [
            "Agricultural supply disruptions",
            "Food safety issues",
            "Packaging material shortages",
            "Logistics for perishable goods"
        ],
        "economic": [
            "Commodity price inflation",
            "Consumer spending shifts to private labels",
            "Currency impacts on international operations"
        ],
        "regulatory": [
            "Food safety regulations",
            "Labeling requirements",
            "Environmental regulations on packaging",
            "Trade policies on agricultural products"
        ],
        "competitive": [
            "Private label competition",
            "E-commerce disruption",
            "Changing consumer preferences (health, sustainability)"
        ]
    }
}

# --- Helper Functions for News Fetching ---

def get_sector_keywords(sector: str) -> List[str]:
    """Get search keywords for a sector to query news"""
    sector_keywords_map = {
        "technology": ["technology", "tech", "software", "semiconductor", "AI", "cloud"],
        "healthcare": ["healthcare", "pharmaceutical", "biotech", "medical", "FDA", "drug"],
        "financial-services": ["banking", "finance", "financial", "bank", "credit", "lending"],
        "energy": ["energy", "oil", "crude", "petroleum", "natural gas", "renewable"],
        "consumer": ["retail", "consumer", "shopping", "e-commerce"],
        "consumer-discretionary": ["retail", "consumer discretionary", "luxury", "automotive"],
        "industrials": ["industrial", "manufacturing", "machinery", "aerospace", "defense"],
        "materials": ["materials", "mining", "steel", "chemicals", "commodities"],
        "real-estate": ["real estate", "property", "REIT", "housing", "commercial"],
        "utilities": ["utility", "electric", "power", "energy utility", "grid"],
        "communications": ["telecom", "communications", "5G", "wireless", "broadband"],
        "consumer-staples": ["consumer staples", "food", "beverage", "household products"]
    }
    return sector_keywords_map.get(sector.lower(), [sector])

def parse_timeframe_to_days(timeframe: str) -> int:
    """Parse timeframe string to number of days"""
    timeframe_lower = timeframe.lower()
    if "1d" in timeframe_lower or "1 day" in timeframe_lower:
        return 1
    elif "1w" in timeframe_lower or "1 week" in timeframe_lower or "week" in timeframe_lower:
        return 7
    elif "1m" in timeframe_lower or "1 month" in timeframe_lower or "month" in timeframe_lower:
        return 30
    elif "3m" in timeframe_lower or "3 month" in timeframe_lower:
        return 90
    elif "6m" in timeframe_lower or "6 month" in timeframe_lower:
        return 180
    elif "1y" in timeframe_lower or "1 year" in timeframe_lower or "year" in timeframe_lower:
        return 365
    else:
        return 7  # Default to 1 week

def fetch_headlines_from_rss(sector: str, days: int, max_results: int = 20) -> List[Dict]:
    """
    Fetch headlines from financial news RSS feeds.
    Uses free RSS feeds - no API key required.
    """
    headlines = []
    keywords = get_sector_keywords(sector)
    
    # Financial news RSS feeds (free, no API key)
    rss_feeds = [
        "https://feeds.finance.yahoo.com/rss/2.0/headline",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.reuters.com/reuters/businessNews",
    ]
    
    risk_keywords = ["risk", "disruption", "crisis", "threat", "concern", "warning", 
                     "volatility", "uncertainty", "challenge", "pressure", "decline", "drop"]
    
    try:
        for feed_url in rss_feeds:
            if len(headlines) >= max_results:
                break
                
            try:
                # Fetch RSS feed
                response = requests.get(feed_url, timeout=10)
                if response.status_code != 200:
                    continue
                
                # Parse RSS XML
                soup = BeautifulSoup(response.content, 'xml')
                items = soup.find_all('item')[:max_results]
                
                for item in items:
                    if len(headlines) >= max_results:
                        break
                    
                    title = item.find('title')
                    link = item.find('link')
                    pub_date = item.find('pubDate')
                    description = item.find('description')
                    
                    if not title:
                        continue
                    
                    title_text = title.get_text().strip()
                    link_text = link.get_text().strip() if link else ""
                    pub_date_text = pub_date.get_text().strip() if pub_date else ""
                    desc_text = description.get_text().strip() if description else ""
                    
                    # Check if headline is relevant to sector or contains risk keywords
                    title_lower = title_text.lower()
                    desc_lower = desc_text.lower()
                    combined_text = f"{title_lower} {desc_lower}"
                    
                    # Match against sector keywords or risk keywords
                    is_relevant = (
                        any(keyword.lower() in combined_text for keyword in keywords) or
                        any(risk_kw in combined_text for risk_kw in risk_keywords)
                    )
                    
                    if is_relevant:
                        headlines.append({
                            "title": title_text,
                            "url": link_text,
                            "date": pub_date_text,
                            "description": desc_text,
                            "source": feed_url.split('/')[2] if '/' in feed_url else "unknown"
                        })
                        
            except Exception as e:
                log(f"Error fetching from {feed_url}: {e}")
                continue
                
    except Exception as e:
        log(f"Error fetching headlines: {e}")
    
    # Remove duplicates based on title
    seen_titles = set()
    unique_headlines = []
    for headline in headlines:
        title_lower = headline["title"].lower()
        if title_lower not in seen_titles:
            seen_titles.add(title_lower)
            unique_headlines.append(headline)
    
    return unique_headlines[:max_results]

def extract_risk_themes_from_headlines(headlines: List, sector: str = None) -> Dict:
    """
    RAG-like extraction: Identifies specific risks and references the articles that discuss them.
    Groups risks by type and provides citations to source articles.
    """
    if not headlines:
        return {
            "identified_risks": [],
            "risk_categories": {},
            "summary": "No headlines provided"
        }
    
    # Normalize headlines to objects with metadata
    normalized_headlines = []
    for headline in headlines:
        if isinstance(headline, str):
            # Convert string to object format
            normalized_headlines.append({
                "title": headline,
                "url": "",
                "date": "",
                "source": "",
                "description": ""
            })
        elif isinstance(headline, dict):
            # Already in object format, ensure required fields
            normalized_headlines.append({
                "title": headline.get("title", ""),
                "url": headline.get("url", ""),
                "date": headline.get("date", ""),
                "source": headline.get("source", ""),
                "description": headline.get("description", "")
            })
    
    # Get sector risk knowledge base if sector provided
    sector_risks = {}
    if sector:
        sector_lower = sector.lower()
        sector_map = {
            "consumer": "consumer-discretionary",
            "consumer discretionary": "consumer-discretionary",
            "financial": "financial-services",
            "financial services": "financial-services"
        }
        normalized_sector = sector_map.get(sector_lower, sector_lower)
        sector_risks = SECTOR_RISKS.get(normalized_sector, {})
    
    # Risk category keywords mapping for general risk detection
    risk_category_keywords = {
        "supply_chain": ["supply chain", "logistics", "shipping", "trade route", "import", "export", 
                        "manufacturing", "component", "shortage", "disruption", "bottleneck"],
        "regulatory": ["regulation", "regulatory", "FDA", "compliance", "policy", "law", 
                      "antitrust", "sanction", "ban", "restriction", "approval"],
        "economic": ["recession", "inflation", "interest rate", "GDP", "unemployment", 
                     "spending", "demand", "economic", "currency", "dollar"],
        "geopolitical": ["trade war", "sanction", "geopolitical", "conflict", "tension", 
                        "China", "Russia", "tariff", "embargo", "diplomatic"],
        "technology": ["cybersecurity", "hack", "breach", "data", "AI", "disruption", 
                      "innovation", "obsolescence", "digital"],
        "environmental": ["climate", "weather", "disaster", "environmental", "emission", 
                          "carbon", "sustainability", "green"],
        "competitive": ["competition", "market share", "rival", "competitor", "pricing", 
                      "disruption", "innovation"],
        "systemic": ["crisis", "liquidity", "default", "contagion", "systemic", "bank run"]
    }
    
    # Dictionary to store risks with their source articles (RAG-style)
    # Structure: {risk_description: [article1, article2, ...]}
    identified_risks = {}
    risk_category_counts = {cat: 0 for cat in risk_category_keywords.keys()}
    
    # Analyze each headline/article
    for article in normalized_headlines:
        title = article.get("title", "")
        description = article.get("description", "")
        combined_text = f"{title} {description}".lower()
        
        # Match against structural risks from knowledge base (primary matching)
        if sector_risks:
            for category, risk_list in sector_risks.items():
                for structural_risk in risk_list:
                    # Extract meaningful keywords from structural risk (words > 3 chars)
                    risk_keywords = [kw for kw in re.findall(r'\b\w+\b', structural_risk.lower()) 
                                   if len(kw) > 3]
                    
                    # Count keyword matches
                    matches = sum(1 for kw in risk_keywords if kw in combined_text)
                    match_ratio = matches / len(risk_keywords) if risk_keywords else 0
                    
                    # Strong match: at least 30% of keywords or 2+ keywords match
                    if match_ratio >= 0.3 or matches >= 2:
                        # Add article reference to this risk
                        if structural_risk not in identified_risks:
                            identified_risks[structural_risk] = {
                                "risk_description": structural_risk,
                                "risk_category": category.replace("_", " ").title(),
                                "articles": [],
                                "article_count": 0
                            }
                        
                        # Add article citation
                        article_ref = {
                            "title": title,
                            "url": article.get("url", ""),
                            "date": article.get("date", ""),
                            "source": article.get("source", ""),
                            "relevance": "high" if match_ratio >= 0.5 or matches >= 3 else "medium"
                        }
                        identified_risks[structural_risk]["articles"].append(article_ref)
                        identified_risks[structural_risk]["article_count"] += 1
                        risk_category_counts[category] = risk_category_counts.get(category, 0) + 1
        
        # Also detect general risk categories (secondary matching for uncategorized risks)
        for category, keywords in risk_category_keywords.items():
            if any(keyword in combined_text for keyword in keywords):
                # Create a general risk description if not already matched to structural risk
                general_risk = f"{category.replace('_', ' ').title()} concerns"
                if general_risk not in identified_risks and category not in [r.get("risk_category", "").lower().replace(" ", "_") 
                                                                           for r in identified_risks.values()]:
                    # Only add if we have sector risks but this wasn't matched
                    if not sector_risks or category not in sector_risks:
                        if general_risk not in identified_risks:
                            identified_risks[general_risk] = {
                                "risk_description": general_risk,
                                "risk_category": category.replace("_", " ").title(),
                                "articles": [],
                                "article_count": 0
                            }
                        identified_risks[general_risk]["articles"].append({
                            "title": title,
                            "url": article.get("url", ""),
                            "date": article.get("date", ""),
                            "source": article.get("source", ""),
                            "relevance": "medium"
                        })
                        identified_risks[general_risk]["article_count"] += 1
    
    # Convert to list format and sort by article count (most discussed risks first)
    risks_list = []
    for risk_desc, risk_data in identified_risks.items():
        risks_list.append({
            "risk": risk_data["risk_description"],
            "category": risk_data["risk_category"],
            "article_count": risk_data["article_count"],
            "articles": risk_data["articles"][:5]  # Top 5 articles per risk
        })
    
    # Sort by article count (descending)
    risks_list.sort(key=lambda x: x["article_count"], reverse=True)
    
    # Summarize by category
    category_summary = {}
    for risk_item in risks_list:
        category = risk_item["category"]
        if category not in category_summary:
            category_summary[category] = {
                "risk_count": 0,
                "article_count": 0
            }
        category_summary[category]["risk_count"] += 1
        category_summary[category]["article_count"] += risk_item["article_count"]
    
    return {
        "identified_risks": risks_list,
        "risk_categories": category_summary,
        "total_risks_identified": len(risks_list),
        "total_articles_analyzed": len(normalized_headlines),
        "summary": f"Identified {len(risks_list)} specific risks across {len(category_summary)} categories, referenced in {sum(r['article_count'] for r in risks_list)} article mentions"
    }

def identify_stock_risks(ticker: str) -> Dict:
    """Identify risks for a specific stock based on its sector"""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Try to get sector from stock info
        sector = info.get('sector', '').lower() if info else ''
        industry = info.get('industry', '').lower() if info else ''
        
        # Map common industry keywords to sectors
        if not sector:
            if any(kw in industry for kw in ['tech', 'software', 'semiconductor']):
                sector = 'technology'
            elif any(kw in industry for kw in ['health', 'pharma', 'biotech']):
                sector = 'healthcare'
            elif any(kw in industry for kw in ['bank', 'finance', 'financial']):
                sector = 'financial-services'
            elif any(kw in industry for kw in ['oil', 'energy', 'petroleum']):
                sector = 'energy'
            elif any(kw in industry for kw in ['retail', 'consumer']):
                sector = 'consumer'
            else:
                sector = 'technology'  # Default
        
        result = identify_sector_risks(sector)
        result["ticker"] = ticker
        result["identified_sector"] = sector
        return result
    except Exception as e:
        log(f"Error identifying stock risks: {e}")
        return {
            "error": f"Could not identify risks for {ticker}: {str(e)}",
            "ticker": ticker
        }

def identify_sector_risks(sector: str) -> Dict:
    """
    Identify structural/inherent risks for a sector based on knowledge base.
    
    This tool provides baseline risk profiles based on sector characteristics.
    For current/recent risk events from news, use fetch_headlines + extract_risk_themes tools.
    """
    sector_lower = sector.lower()
    
    # Normalize sector name
    sector_map = {
        "consumer": "consumer-discretionary",
        "consumer discretionary": "consumer-discretionary",
        "financial": "financial-services",
        "financial services": "financial-services"
    }
    
    normalized_sector = sector_map.get(sector_lower, sector_lower)
    
    # Get risks from knowledge base
    risks = SECTOR_RISKS.get(normalized_sector, {})
    
    if not risks:
        # Try to find partial match
        for key in SECTOR_RISKS.keys():
            if sector_lower in key or key in sector_lower:
                risks = SECTOR_RISKS[key]
                normalized_sector = key
                break
    
    if not risks:
        return {
            "sector": sector,
            "error": f"Unknown sector: {sector}. Available sectors: {', '.join(SECTOR_RISKS.keys())}",
            "available_sectors": list(SECTOR_RISKS.keys())
        }
    
    # Structure the response
    risk_categories = []
    for category, risk_list in risks.items():
        risk_categories.append({
            "category": category.replace("_", " ").title(),
            "risks": risk_list,
            "count": len(risk_list)
        })
    
    result = {
        "sector": normalized_sector,
        "risk_type": "structural_inherent",
        "description": "These are structural/inherent risks based on sector characteristics. For current risk events, use fetch_headlines + extract_risk_themes tools.",
        "risk_categories": risk_categories,
        "total_risk_count": sum(len(r) for r in risks.values()),
        "summary": f"Identified {len(risk_categories)} major risk categories with {sum(len(r) for r in risks.values())} specific structural risks"
    }
    
    return result

# --- list_tools Handler ---
@app.list_tools()
async def list_tools() -> list[Tool]:
    log("list_tools called")
    return [
        Tool(
            name="fetch_headlines",
            description="Fetch news headlines",
            inputSchema={
                "type": "object",
                "properties": {
                    "sector": {"type": "string"},
                    "timeframe": {"type": "string"}
                },
                "required": ["sector", "timeframe"]
            }
        ),
        Tool(
            name="extract_risk_themes",
            description="RAG system: Fetches real news articles for a sector, extracts specific risk themes from those articles, and provides citations to the source articles. Identifies which structural risks are being discussed in current news and references the articles that mention them.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sector": {
                        "type": "string",
                        "description": "Sector name (e.g., 'technology', 'healthcare', 'consumer-discretionary')"
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "Timeframe for news articles (e.g., '1w', '1m', '1y')"
                    }
                },
                "required": ["sector", "timeframe"]
            }
        ),
        Tool(
            name="identify_sector_risks",
            description="Identify structural/inherent risks that a sector or stock can face based on sector characteristics. Provides baseline risk profiles including supply chain disruptions, regulatory changes, economic factors, and geopolitical issues. For current/recent risk events from news, use fetch_headlines + extract_risk_themes tools.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sector_or_ticker": {
                        "type": "string",
                        "description": "Sector name (e.g., 'technology', 'healthcare') or stock ticker symbol (e.g., 'AAPL', 'MSFT')"
                    }
                },
                "required": ["sector_or_ticker"]
            }
        )
    ]

# --- call_tool Handler ---
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    log(f"call_tool: {name}")
    if name == "fetch_headlines":
        sector = arguments.get("sector", "")
        timeframe = arguments.get("timeframe", "")
        
        try:
            # Parse timeframe to determine how many days of news to fetch
            days = parse_timeframe_to_days(timeframe)
            
            # Fetch headlines from RSS feeds
            headlines = fetch_headlines_from_rss(sector, days, max_results=20)
            
            if not headlines:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "sector": sector,
                        "timeframe": timeframe,
                        "headlines": [],
                        "message": "No relevant headlines found for this sector and timeframe"
                    })
                )]
            
            # Return structured headlines
            result = {
                "sector": sector,
                "timeframe": timeframe,
                "days_covered": days,
                "headline_count": len(headlines),
                "headlines": headlines
            }
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except Exception as e:
            log(f"Error fetching headlines: {e}")
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Failed to fetch headlines: {str(e)}",
                    "sector": sector,
                    "timeframe": timeframe
                })
            )]
    
    elif name == "extract_risk_themes":
        sector = arguments.get("sector", "")
        timeframe = arguments.get("timeframe", "")
        
        try:
            # Step 1: Fetch real articles from RSS feeds
            days = parse_timeframe_to_days(timeframe)
            log(f"Fetching articles for {sector} over {timeframe} ({days} days)")
            
            articles = fetch_headlines_from_rss(sector, days, max_results=30)
            
            if not articles:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "sector": sector,
                        "timeframe": timeframe,
                        "identified_risks": [],
                        "articles_fetched": 0,
                        "message": "No relevant articles found for this sector and timeframe. Unable to extract risk themes."
                    })
                )]
            
            log(f"Fetched {len(articles)} articles, extracting risk themes...")
            
            # Step 2: Extract risk themes from real articles (RAG-style)
            result = extract_risk_themes_from_headlines(articles, sector)
            
            # Step 3: Add metadata about the fetch operation
            result["sector"] = sector
            result["timeframe"] = timeframe
            result["articles_fetched"] = len(articles)
            result["fetch_date"] = datetime.now().isoformat()
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except Exception as e:
            log(f"Error extracting risk themes: {e}")
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Failed to extract risk themes: {str(e)}",
                    "sector": sector,
                    "timeframe": timeframe
                })
            )]
    elif name == "identify_sector_risks":
        sector_or_ticker = arguments.get("sector_or_ticker", "")
        
        try:
            # Check if it's a ticker (typically 1-5 uppercase letters) or sector name
            is_ticker = len(sector_or_ticker) <= 5 and sector_or_ticker.isupper() and sector_or_ticker.isalpha()
            
            if is_ticker:
                result = identify_stock_risks(sector_or_ticker)
            else:
                result = identify_sector_risks(sector_or_ticker)
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except Exception as e:
            log(f"Error identifying sector risks: {e}")
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Failed to identify risks: {str(e)}",
                    "sector_or_ticker": sector_or_ticker
                })
            )]
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

# --- Main Entrypoint ---
async def main():
    log("Server starting")
    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            log("stdio_server initialized, starting message loop")
            init_options = app.create_initialization_options()
            await app.run(
                read_stream, 
                write_stream, 
                init_options
            )
            log("Server run completed normally")
    except Exception as e:
        log(f"Server error: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception:
        sys.exit(1)