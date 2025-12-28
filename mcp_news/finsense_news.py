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
from bs4 import XMLParsedAsHTMLWarning
import warnings

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# Ensure stdout is unbuffered
sys.stdout.reconfigure(line_buffering=True)

# Enhanced logging - always log to stderr for debugging
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

def log(msg):
    logger.info(msg)

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

def get_sector_keywords(sector: str) -> Dict[str, List[str]]:
    """Get highly specific search keywords for each sector"""
    sector_keywords_map = {
        "technology": {
            "required": ["technology", "tech", "semiconductor", "chip", "AI", "software", "cloud", "data center"],
            "companies": ["Apple", "Microsoft", "Google", "Alphabet", "NVIDIA", "Meta", "Amazon AWS", "Intel", "AMD", "TSMC", "Samsung", "Qualcomm", "Oracle", "Salesforce", "Adobe", "Tesla"],
            "terms": ["GPU", "CPU", "artificial intelligence", "machine learning", "chip shortage", "fab", "foundry", "silicon", "processor", "cloud computing", "SaaS", "enterprise software", "cybersecurity", "5G", "quantum computing", "robotics"]
        },
        "healthcare": {
            "required": ["healthcare", "pharmaceutical", "biotech", "drug", "FDA", "clinical"],
            "companies": ["Pfizer", "Moderna", "Johnson & Johnson", "Eli Lilly", "Merck", "AbbVie", "Bristol Myers", "Amgen", "Gilead", "Regeneron"],
            "terms": ["vaccine", "clinical trial", "drug approval", "biosimilar", "gene therapy", "CAR-T", "obesity drug", "GLP-1", "oncology", "rare disease", "medical device"]
        },
        "financial-services": {
            "required": ["bank", "banking", "financial", "finance", "Fed", "interest rate"],
            "companies": ["JPMorgan", "Bank of America", "Wells Fargo", "Citigroup", "Goldman Sachs", "Morgan Stanley", "BlackRock", "Visa", "Mastercard"],
            "terms": ["Federal Reserve", "loan", "credit", "mortgage", "trading", "investment banking", "wealth management", "fintech", "payment", "capital markets", "deposit"]
        },
        "energy": {
            "required": ["oil", "energy", "crude", "natural gas", "petroleum", "renewable"],
            "companies": ["ExxonMobil", "Chevron", "ConocoPhillips", "Shell", "BP", "TotalEnergies", "NextEra Energy", "Occidental"],
            "terms": ["barrel", "WTI", "Brent", "OPEC", "refinery", "pipeline", "LNG", "wind", "solar", "EV", "electric vehicle", "battery"]
        },
        "consumer": {
            "required": ["retail", "consumer", "sales", "shopping"],
            "companies": ["Amazon", "Walmart", "Target", "Costco", "Home Depot", "Lowe's", "Nike", "Starbucks", "McDonald's"],
            "terms": ["e-commerce", "same-store sales", "Black Friday", "holiday shopping", "inventory", "margin", "foot traffic", "omnichannel"]
        },
        "consumer-discretionary": {
            "required": ["retail", "consumer discretionary", "automotive", "luxury"],
            "companies": ["Tesla", "Ford", "GM", "Nike", "Lululemon", "LVMH", "Disney", "Netflix", "Booking"],
            "terms": ["electric vehicle", "EV sales", "SUV", "pickup truck", "streaming", "theme park", "hotel", "travel", "restaurant"]
        },
        "industrials": {
            "required": ["industrial", "manufacturing", "aerospace", "defense"],
            "companies": ["Boeing", "Lockheed Martin", "Raytheon", "General Electric", "Caterpillar", "Deere", "3M", "Honeywell"],
            "terms": ["aircraft", "defense contract", "construction equipment", "factory", "automation", "supply chain", "logistics", "freight"]
        },
        "materials": {
            "required": ["materials", "mining", "metals", "chemicals"],
            "companies": ["Freeport-McMoRan", "Newmont", "Dow", "DuPont", "Nucor", "Steel Dynamics"],
            "terms": ["copper", "gold", "steel", "aluminum", "lithium", "commodity", "ore", "industrial metals", "rare earth"]
        },
        "real-estate": {
            "required": ["real estate", "property", "REIT", "housing", "mortgage"],
            "companies": ["Prologis", "American Tower", "Crown Castle", "Simon Property", "Realty Income"],
            "terms": ["commercial real estate", "office", "warehouse", "apartment", "multifamily", "rent", "occupancy", "cap rate"]
        },
        "utilities": {
            "required": ["utility", "electric", "power", "grid", "energy utility"],
            "companies": ["NextEra Energy", "Duke Energy", "Southern Company", "Dominion Energy", "American Electric Power"],
            "terms": ["electricity", "natural gas utility", "transmission", "distribution", "renewable energy", "nuclear", "power plant"]
        },
        "communications": {
            "required": ["telecom", "wireless", "broadband", "5G", "communications"],
            "companies": ["Verizon", "AT&T", "T-Mobile", "Comcast", "Charter Communications"],
            "terms": ["spectrum", "fiber", "cable", "satellite", "network", "subscriber", "ARPU", "tower"]
        },
        "consumer-staples": {
            "required": ["consumer staples", "food", "beverage", "packaged goods"],
            "companies": ["Procter & Gamble", "Coca-Cola", "PepsiCo", "Walmart", "Costco", "Mondelez", "Kraft Heinz"],
            "terms": ["CPG", "grocery", "private label", "pricing power", "volume", "brand", "distribution"]
        }
    }
    return sector_keywords_map.get(sector.lower(), {
        "required": [sector],
        "companies": [],
        "terms": []
    })

def get_sector_rss_feeds(sector: str) -> List[str]:
    """Get sector-specific RSS feeds"""
    base_feeds = [
        "https://feeds.finance.yahoo.com/rss/2.0/headline",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.reuters.com/reuters/businessNews",
    ]
    
    sector_feeds = {
        "technology": [
            "https://www.cnbc.com/id/19854910/device/rss/rss.html",  # CNBC Tech
            "https://feeds.reuters.com/reuters/technologyNews",
        ],
        "healthcare": [
            "https://feeds.reuters.com/reuters/healthNews",
        ],
        "financial-services": [
            "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        ],
        "energy": [
            "https://feeds.reuters.com/reuters/energy",
        ]
    }
    
    return base_feeds + sector_feeds.get(sector.lower(), [])

def analyze_sentiment(title: str, description: str, sector: str) -> Dict[str, any]:
    """Analyze sentiment of headline for the sector (positive/negative/mixed/neutral)"""
    text = f"{title} {description}".lower()
    
    # Positive indicators
    positive_words = [
        "surge", "jump", "rally", "gain", "rise", "climb", "soar", "boom", "growth",
        "profit", "beat", "exceed", "outperform", "record", "high", "breakthrough",
        "strong", "robust", "recovery", "innovation", "launch", "success", "win",
        "approval", "deal", "acquisition", "expansion", "upgrade", "bullish",
        "optimistic", "confident", "positive", "momentum", "accelerate"
    ]
    
    # Negative indicators
    negative_words = [
        "plunge", "drop", "fall", "decline", "tumble", "crash", "loss", "miss",
        "underperform", "weak", "concern", "worry", "fear", "risk", "threat",
        "crisis", "shortage", "disruption", "delay", "cut", "layoff", "downturn",
        "recession", "investigation", "lawsuit", "fine", "penalty", "bearish",
        "warning", "downgrade", "slump", "pressure", "struggle", "headwind",
        "volatility", "uncertainty", "challenge", "difficult"
    ]
    
    pos_count = sum(1 for word in positive_words if word in text)
    neg_count = sum(1 for word in negative_words if word in text)
    
    # Determine sentiment category
    if pos_count >= 2 and neg_count >= 2:
        sentiment = "mixed"
        confidence = "medium"
    elif pos_count > neg_count and pos_count >= 2:
        sentiment = "positive"
        confidence = "high" if pos_count >= 3 else "medium"
    elif pos_count > neg_count and pos_count == 1:
        sentiment = "positive"
        confidence = "low"
    elif neg_count > pos_count and neg_count >= 2:
        sentiment = "negative"
        confidence = "high" if neg_count >= 3 else "medium"
    elif neg_count > pos_count and neg_count == 1:
        sentiment = "negative"
        confidence = "low"
    elif pos_count == neg_count and pos_count >= 1:
        sentiment = "mixed"
        confidence = "medium"
    else:
        sentiment = "neutral"
        confidence = "high"
    
    return {
        "sentiment": sentiment,
        "confidence": confidence,
        "positive_signals": pos_count,
        "negative_signals": neg_count
    }

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

def is_relevant_to_sector(title: str, description: str, keywords: Dict[str, List[str]]) -> tuple[bool, int]:
    """Check if headline is relevant to sector with scoring"""
    text = f"{title} {description}".lower()
    score = 0
    
    # Required keywords (must have at least one)
    required_match = any(kw.lower() in text for kw in keywords.get("required", []))
    if not required_match:
        return False, 0
    score += 10
    
    # Company mentions (high value)
    company_matches = sum(1 for company in keywords.get("companies", []) if company.lower() in text)
    score += company_matches * 5
    
    # Technical terms (medium value)
    term_matches = sum(1 for term in keywords.get("terms", []) if term.lower() in text)
    score += term_matches * 2
    
    return score >= 10, score

def fetch_headlines_from_rss(sector: str, days: int, max_results: int = 20) -> List[Dict]:
    """
    Fetch sector-specific headlines from RSS feeds with sentiment analysis.
    """
    headlines = []
    keywords = get_sector_keywords(sector)
    
    log(f"Fetching headlines for sector: {sector}")
    log(f"Required keywords: {keywords.get('required', [])[:5]}")
    log(f"Companies: {keywords.get('companies', [])[:5]}")
    
    rss_feeds = get_sector_rss_feeds(sector)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    for feed_url in rss_feeds:
        if len(headlines) >= max_results:
            break
        
        try:
            log(f"Fetching from: {feed_url}")
            response = requests.get(feed_url, timeout=15, headers=headers)
            
            if response.status_code != 200:
                log(f"Failed to fetch {feed_url}: HTTP {response.status_code}")
                continue
            
            try:
                soup = BeautifulSoup(response.content, 'xml')
            except:
                soup = BeautifulSoup(response.content, 'html.parser')
            
            items = soup.find_all('item')
            
            log(f"Found {len(items)} items in feed")
            
            for item in items[:max_results * 3]:
                if len(headlines) >= max_results:
                    break
                
                title = item.find('title')
                link = item.find('link')
                pub_date = item.find('pubdate') or item.find('pubDate')
                description = item.find('description')
                
                if not title:
                    continue
                
                title_text = title.get_text().strip()
                link_text = link.get_text().strip() if link else ""
                pub_date_text = pub_date.get_text().strip() if pub_date else ""
                desc_text = description.get_text().strip() if description else ""
                
                # Clean HTML tags from description
                desc_text = re.sub(r'<[^>]+>', '', desc_text)
                
                # Check relevance with scoring
                is_relevant, relevance_score = is_relevant_to_sector(title_text, desc_text, keywords)
                
                if is_relevant and relevance_score >= 10:
                    # Analyze sentiment with detailed breakdown
                    sentiment_analysis = analyze_sentiment(title_text, desc_text, sector)
                    
                    source = link_text if link_text else (feed_url.split('/')[2] if '/' in feed_url else "unknown")
                    headlines.append({
                        "title": title_text,
                        "url": link_text,
                        "date": pub_date_text,
                        "description": desc_text[:200],
                        "source": source,
                        "relevance_score": relevance_score,
                        "sentiment": sentiment_analysis["sentiment"],
                        "sentiment_confidence": sentiment_analysis["confidence"],
                        "sentiment_details": {
                            "positive_signals": sentiment_analysis["positive_signals"],
                            "negative_signals": sentiment_analysis["negative_signals"]
                        }
                    })
                    log(f"Added ({sentiment_analysis['sentiment']}/{sentiment_analysis['confidence']}): {title_text[:60]}... (score: {relevance_score})")
                    
        except Exception as e:
            log(f"Error parsing {feed_url}: {e}")
            continue
    
    log(f"Total headlines collected: {len(headlines)}")
    
    # Remove duplicates and sort by relevance
    seen_titles = set()
    unique_headlines = []
    for headline in sorted(headlines, key=lambda x: x["relevance_score"], reverse=True):
        title_lower = headline["title"].lower()
        if title_lower not in seen_titles:
            seen_titles.add(title_lower)
            unique_headlines.append(headline)
    
    log(f"Unique headlines after deduplication: {len(unique_headlines)}")
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
    
    log(f"Extracting risk themes from {len(headlines)} headlines...")
    
    # Normalize headlines to objects with metadata
    normalized_headlines = []
    for headline in headlines:
        if isinstance(headline, str):
            # For string headlines, analyze sentiment
            sentiment_analysis = analyze_sentiment(headline, "", sector or "")
            normalized_headlines.append({
                "title": headline,
                "url": "",
                "date": "",
                "source": "",
                "description": "",
                "sentiment": sentiment_analysis["sentiment"],
                "sentiment_confidence": sentiment_analysis["confidence"]
            })
        elif isinstance(headline, dict):
            normalized_headlines.append({
                "title": headline.get("title", ""),
                "url": headline.get("url", ""),
                "date": headline.get("date", ""),
                "source": headline.get("source", ""),
                "description": headline.get("description", ""),
                "sentiment": headline.get("sentiment", "neutral"),
                "sentiment_confidence": headline.get("sentiment_confidence", "unknown")
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
        log(f"Using sector knowledge base: {normalized_sector}, categories: {list(sector_risks.keys())}")
    
    # Enhanced risk category keywords with more variations
    risk_category_keywords = {
        "supply_chain": ["supply", "chain", "logistics", "shipping", "trade", "import", "export", 
                        "manufacturing", "component", "shortage", "disruption", "bottleneck", "semiconductor"],
        "regulatory": ["regulation", "regulatory", "FDA", "compliance", "policy", "law", 
                      "antitrust", "sanction", "ban", "restriction", "approval", "government"],
        "economic": ["recession", "inflation", "interest", "rate", "GDP", "unemployment", 
                     "spending", "demand", "economic", "currency", "dollar", "earnings", "revenue",
                     "profit", "loss", "growth", "downturn", "slowdown"],
        "geopolitical": ["trade war", "sanction", "geopolitical", "conflict", "tension", 
                        "China", "Russia", "tariff", "embargo", "diplomatic", "war"],
        "technology": ["cybersecurity", "hack", "breach", "data", "AI", "artificial intelligence",
                      "innovation", "obsolescence", "digital", "cloud", "software"],
        "environmental": ["climate", "weather", "disaster", "environmental", "emission", 
                          "carbon", "sustainability", "green", "renewable"],
        "competitive": ["competition", "market share", "rival", "competitor", "pricing", 
                      "disruption", "innovation", "startup"],
        "systemic": ["crisis", "liquidity", "default", "contagion", "systemic", "bank run", "crash"]
    }
    
    identified_risks = {}
    risk_category_counts = {cat: 0 for cat in risk_category_keywords.keys()}
    
    # Analyze each headline/article
    for idx, article in enumerate(normalized_headlines):
        title = article.get("title", "")
        description = article.get("description", "")
        sentiment = article.get("sentiment", "neutral")
        sentiment_confidence = article.get("sentiment_confidence", "unknown")
        combined_text = f"{title} {description}".lower()
        
        log(f"Analyzing article {idx+1}: {title[:60]}...")
        article_matched = False
        
        # First pass: Match against general risk categories
        for category, keywords in risk_category_keywords.items():
            matched_keywords = [kw for kw in keywords if kw in combined_text]
            
            if matched_keywords:
                log(f"  - Found {category} keywords: {matched_keywords[:3]}")
                article_matched = True
                
                general_risk = f"{category.replace('_', ' ').title()} concerns"
                
                if general_risk not in identified_risks:
                    identified_risks[general_risk] = {
                        "risk_description": general_risk,
                        "risk_category": category.replace("_", " ").title(),
                        "articles": [],
                        "article_count": 0,
                        "sentiment_breakdown": {"positive": 0, "negative": 0, "mixed": 0, "neutral": 0}
                    }
                
                article_ref = {
                    "title": title,
                    "url": article.get("url", ""),
                    "date": article.get("date", ""),
                    "source": article.get("source", ""),
                    "sentiment": sentiment,
                    "sentiment_confidence": sentiment_confidence,
                    "relevance": "high" if len(matched_keywords) >= 3 else "medium",
                    "matched_keywords": matched_keywords[:5]
                }
                
                identified_risks[general_risk]["articles"].append(article_ref)
                identified_risks[general_risk]["article_count"] += 1
                identified_risks[general_risk]["sentiment_breakdown"][sentiment] += 1
                risk_category_counts[category] += 1
        
        # Second pass: Match specific structural risks
        if sector_risks:
            for category, risk_list in sector_risks.items():
                for structural_risk in risk_list:
                    skip_words = {'and', 'or', 'the', 'for', 'from', 'with', 'during', 'in', 'on', 'at', 'to', 'of'}
                    risk_keywords = [
                        kw for kw in re.findall(r'\b\w+\b', structural_risk.lower()) 
                        if len(kw) > 3 and kw not in skip_words
                    ]
                    
                    matches = sum(1 for kw in risk_keywords if kw in combined_text)
                    match_ratio = matches / len(risk_keywords) if risk_keywords else 0
                    
                    if matches >= 1 and (match_ratio >= 0.15 or matches >= 2):
                        log(f"  - Matched structural risk: {structural_risk[:50]}... ({matches}/{len(risk_keywords)} keywords)")
                        article_matched = True
                        
                        if structural_risk not in identified_risks:
                            identified_risks[structural_risk] = {
                                "risk_description": structural_risk,
                                "risk_category": category.replace("_", " ").title(),
                                "articles": [],
                                "article_count": 0,
                                "sentiment_breakdown": {"positive": 0, "negative": 0, "mixed": 0, "neutral": 0}
                            }
                        
                        article_ref = {
                            "title": title,
                            "url": article.get("url", ""),
                            "date": article.get("date", ""),
                            "source": article.get("source", ""),
                            "sentiment": sentiment,
                            "sentiment_confidence": sentiment_confidence,
                            "relevance": "high" if match_ratio >= 0.3 or matches >= 3 else "medium"
                        }
                        identified_risks[structural_risk]["articles"].append(article_ref)
                        identified_risks[structural_risk]["article_count"] += 1
                        identified_risks[structural_risk]["sentiment_breakdown"][sentiment] += 1
                        risk_category_counts[category] = risk_category_counts.get(category, 0) + 1
        
        if not article_matched:
            log(f"  - No risk matches found (article may not be risk-related)")
    
    # Convert to list and sort
    risks_list = []
    for risk_desc, risk_data in identified_risks.items():
        risks_list.append({
            "risk": risk_data["risk_description"],
            "category": risk_data["risk_category"],
            "article_count": risk_data["article_count"],
            "sentiment_breakdown": risk_data["sentiment_breakdown"],
            "dominant_sentiment": max(risk_data["sentiment_breakdown"].items(), key=lambda x: x[1])[0],
            "articles": risk_data["articles"][:5]
        })
    
    risks_list.sort(key=lambda x: x["article_count"], reverse=True)
    
    # Summarize by category
    category_summary = {}
    for risk_item in risks_list:
        category = risk_item["category"]
        if category not in category_summary:
            category_summary[category] = {
                "risk_count": 0,
                "article_count": 0,
                "sentiment_breakdown": {"positive": 0, "negative": 0, "mixed": 0, "neutral": 0}
            }
        category_summary[category]["risk_count"] += 1
        category_summary[category]["article_count"] += risk_item["article_count"]
        
        # Aggregate sentiment
        for sentiment, count in risk_item["sentiment_breakdown"].items():
            category_summary[category]["sentiment_breakdown"][sentiment] += count
    
    log(f"Identified {len(risks_list)} risks across {len(category_summary)} categories")
    
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
        
        sector = info.get('sector', '').lower() if info else ''
        industry = info.get('industry', '').lower() if info else ''
        
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
                sector = 'technology'
        
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
    """Identify structural/inherent risks for a sector based on knowledge base."""
    sector_lower = sector.lower()
    
    sector_map = {
        "consumer": "consumer-discretionary",
        "consumer discretionary": "consumer-discretionary",
        "financial": "financial-services",
        "financial services": "financial-services"
    }
    
    normalized_sector = sector_map.get(sector_lower, sector_lower)
    risks = SECTOR_RISKS.get(normalized_sector, {})
    
    if not risks:
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
            description="Fetch sector-specific news headlines with sentiment analysis (positive/negative/neutral)",
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
            description="RAG system: Fetches real news articles for a sector, extracts specific risk themes from those articles, and provides citations to the source articles.",
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
            name="identify_sector_risks",
            description="Identify structural/inherent risks for a sector or stock.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sector_or_ticker": {"type": "string"}
                },
                "required": ["sector_or_ticker"]
            }
        )
    ]

# --- call_tool Handler ---
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    log(f"call_tool: {name} with args: {arguments}")
    
    if name == "fetch_headlines":
        sector = arguments.get("sector", "")
        timeframe = arguments.get("timeframe", "")
        
        try:
            days = parse_timeframe_to_days(timeframe)
            headlines = fetch_headlines_from_rss(sector, days, max_results=20)
            
            if not headlines:
                log("WARNING: No headlines found!")
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "sector": sector,
                        "timeframe": timeframe,
                        "headlines": [],
                        "message": "No relevant headlines found. This could be due to RSS feed issues or connectivity problems."
                    })
                )]
            
            # Calculate sentiment distribution
            sentiment_counts = {"positive": 0, "negative": 0, "mixed": 0,"neutral": 0}
            for h in headlines:
                sentiment_counts[h.get("sentiment", "neutral")] += 1
            
            result = {
                "sector": sector,
                "timeframe": timeframe,
                "days_covered": days,
                "headline_count": len(headlines),
                "sentiment_distribution": sentiment_counts,
                "headlines": headlines
            }
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except Exception as e:
            log(f"ERROR in fetch_headlines: {e}")
            import traceback
            log(traceback.format_exc())
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
            days = parse_timeframe_to_days(timeframe)
            log(f"Fetching articles for {sector} over {timeframe} ({days} days)")
            
            articles = fetch_headlines_from_rss(sector, days, max_results=30)
            
            if not articles:
                log("WARNING: No articles found for risk extraction!")
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "sector": sector,
                        "timeframe": timeframe,
                        "identified_risks": [],
                        "articles_fetched": 0,
                        "message": "No relevant articles found. Unable to extract risk themes. This could be due to RSS feed issues."
                    })
                )]
            
            log(f"Fetched {len(articles)} articles, extracting risk themes...")
            result = extract_risk_themes_from_headlines(articles, sector)
            
            result["sector"] = sector
            result["timeframe"] = timeframe
            result["articles_fetched"] = len(articles)
            result["fetch_date"] = datetime.now().isoformat()
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except Exception as e:
            log(f"ERROR in extract_risk_themes: {e}")
            import traceback
            log(traceback.format_exc())
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
            is_ticker = len(sector_or_ticker) <= 5 and sector_or_ticker.isupper() and sector_or_ticker.isalpha()
            
            if is_ticker:
                result = identify_stock_risks(sector_or_ticker)
            else:
                result = identify_sector_risks(sector_or_ticker)
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except Exception as e:
            log(f"ERROR in identify_sector_risks: {e}")
            import traceback
            log(traceback.format_exc())
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