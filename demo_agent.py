"""
Demo script with interactive chatbot for collecting user preferences.
"""

import asyncio
from agent.agent import FinsenseCoordinator
from ui.chatbot import run_chatbot, INVESTMENT_GOALS
from ui.summary_generator import generate_sector_goal_summary, generate_risk_summary_with_citations


def display_user_preferences(preferences: dict):
    """Display user's collected preferences"""
    print("\n" + "="*80)
    print("YOUR INVESTMENT PREFERENCES")
    print("="*80)
    
    goals = preferences.get("goals", [])
    if goals:
        goal_names = [INVESTMENT_GOALS[g]["name"] for g in goals]
        print(f"\nInvestment Goals: {', '.join(goal_names)}")
    else:
        print("\nInvestment Goals: Exploratory (no specific goals)")
    
    sectors = preferences.get("sectors", [])
    print(f"Sectors: {', '.join(sectors)} ({len(sectors)} total)")
    
    risk = preferences.get("risk_tolerance", "medium")
    print(f"Risk Tolerance: {risk.upper()}")
    print("="*80)


def display_research_findings(research_data: dict):
    """Display actual research insights and analysis"""
    
    print("\n" + "="*80)
    print("RESEARCH FINDINGS - DETAILED ANALYSIS")
    print("="*80)
    
    # 1. Market Context
    print("\n[MARKET OVERVIEW]")
    print("-" * 80)
    market_ctx = research_data.get("market_context", {})
    
    if "error" in market_ctx:
        print(f"  [!] Error fetching market data: {market_ctx['error']}")
    else:
        # Market context has nested 'data' field
        market_data = market_ctx.get("data", market_ctx)
        if market_data:
            for index_name, index_data in market_data.items():
                if isinstance(index_data, dict):
                    value = index_data.get('value', 'N/A')
                    change = index_data.get('change', 'N/A')
                    change_pct = index_data.get('change_percent', 'N/A')
                    print(f"  {index_name}:")
                    print(f"    Value: {value}")
                    print(f"    Change: {change} ({change_pct}%)")
        else:
            print("  No market data available")
    
    # 2. Sector Deep Dives
    print("\n[SECTOR ANALYSIS]")
    print("-" * 80)
    
    sectors = research_data.get("sector_deep_dives", {})
    for sector_name, sector_data in sectors.items():
        print(f"\n> {sector_name.upper()}")
        
        # Market Performance
        perf = sector_data.get("market_performance", {})
        if "error" not in perf and perf:
            print(f"  Market Performance:")
            print(f"    1-Month:  {perf.get('performance_1m', 'N/A')}")
            print(f"    3-Month:  {perf.get('performance_3m', 'N/A')}")
            print(f"    1-Year:   {perf.get('performance_1y', 'N/A')}")
            
            top = perf.get('top_performers', [])
            if top:
                top_str = ', '.join([str(t) for t in top[:3]])
                print(f"    Top Performers: {top_str}")
        else:
            print(f"  Market Performance: [!] {perf.get('error', 'No data')}")
        
        # Risk Profile
        risk = sector_data.get("risk_profile", {})
        if "error" not in risk and risk:
            metrics = risk.get('metrics', risk)
            print(f"  Risk Profile:")
            print(f"    Volatility (Annual): {metrics.get('annualized_volatility', 'N/A')}")
            print(f"    Max Drawdown: {metrics.get('max_drawdown', 'N/A')}")
            print(f"    Trend: {metrics.get('trend', 'N/A')}")
            print(f"    Risk Level: {metrics.get('percentile', 'N/A')}")
        else:
            print(f"  Risk Profile: [!] {risk.get('error', 'No data')}")
        
        # News Analysis
        news = sector_data.get("news_analysis", {})
        if "error" not in news and news:
            risks = news.get('identified_risks', [])
            print(f"  Risk Themes ({len(risks)} identified):")
            for idx, risk_item in enumerate(risks[:3], 1):  # Show top 3
                risk_text = risk_item.get('risk', 'N/A')
                category = risk_item.get('category', 'N/A')
                severity = risk_item.get('severity', 'N/A')
                print(f"    {idx}. [{category.upper()}] {risk_text}")
                if severity != 'N/A':
                    print(f"       Severity: {severity}")
        else:
            print(f"  Risk Themes: [!] {news.get('error', 'No data')}")
        
        # Show errors if any
        errors = sector_data.get('errors', [])
        if errors:
            print(f"  [!] Errors encountered: {len(errors)}")
            for err in errors[:2]:
                print(f"    - {err}")
    
    # 3. Portfolio Implications
    if len(sectors) > 1:
        print("\n[PORTFOLIO IMPLICATIONS]")
        print("-" * 80)
        
        corr = research_data.get("portfolio_implications", {}).get("correlations", {})
        if "error" not in corr and corr:
            print(f"  Diversification Score: {corr.get('diversification_score', 'N/A')}")
            
            # Correlation matrix sample
            matrix = corr.get('correlation_matrix', {})
            if matrix:
                print(f"  Correlation Matrix: {len(matrix)} sectors analyzed")
                # Show a sample
                sector_list = list(matrix.keys())[:3]
                for s in sector_list:
                    correlations = matrix.get(s, {})
                    if isinstance(correlations, dict):
                        print(f"    {s}: ", end="")
                        corr_samples = list(correlations.items())[:3]
                        for s2, val in corr_samples:
                            if s != s2 and isinstance(val, (int, float)):
                                print(f"{s2}={val:.2f} ", end="")
                        print()
                    else:
                        print(f"    {s}: {correlations}")
            
            # Insights
            insights = corr.get('insights', {})
            if insights:
                print(f"  Insights:")
                for key, value in insights.items():
                    if isinstance(value, list) and value:
                        print(f"    {key.replace('_', ' ').title()}: {', '.join(value[:3])}")
        else:
            print(f"  ⚠ {corr.get('error', 'No correlation data')}")
    
    # 4. Goal-Based Recommendations (if goals provided)
    goal_recs = research_data.get("goal_based_recommendations", {})
    if goal_recs and goal_recs.get("ranked_sectors"):
        print("\n[GOAL-BASED RECOMMENDATIONS]")
        print("-" * 80)
        print(f"  {goal_recs.get('summary', '')}")
        
        goals_applied = goal_recs.get("goals_applied", [])
        if goals_applied:
            from ui.chatbot import INVESTMENT_GOALS
            goal_names = [INVESTMENT_GOALS.get(g, {}).get("name", g) for g in goals_applied]
            print(f"  Goals Applied: {', '.join(goal_names)}")
        
        top_picks = goal_recs.get("top_picks", [])
        if top_picks:
            print(f"\n  Top Recommendations:")
            for idx, pick in enumerate(top_picks, 1):
                print(f"\n    {idx}. {pick['sector'].upper()} (Score: {pick['score']})")
                print(f"       Volatility: {pick['volatility']} | 1M Performance: {pick['performance_1m']}")
                print(f"       Risk Level: {pick['risk_level']}")
                if pick.get('reasons'):
                    print(f"       Why: {', '.join(pick['reasons'][:2])}")
    
    # 5. Execution Summary
    print("\n[EXECUTION SUMMARY]")
    print("-" * 80)
    summary = research_data.get("execution_summary", {})
    if summary:
        print(f"  Total Operations: {summary.get('total_operations', 0)}")
        print(f"  Successful: {summary.get('successful', 0)}")
        print(f"  Failed: {summary.get('failed', 0)}")
        print(f"  Success Rate: {summary.get('success_rate', 'N/A')}")
        
        if summary.get('timeouts', 0) > 0:
            print(f"  [!] Timeouts: {summary['timeouts']}")
        
        errors_by_type = summary.get('errors_by_type', {})
        if errors_by_type:
            print(f"  Error Types: {dict(errors_by_type)}")
    
    print("\n" + "="*80)


async def main():
    """Run interactive chatbot and research analysis"""
    
    # Run chatbot to collect preferences
    preferences = run_chatbot()
    
    if not preferences:
        print("\nChatbot cancelled. Exiting...")
        return
    
    # Display collected preferences
    display_user_preferences(preferences)
    
    coordinator = FinsenseCoordinator()
    
    try:
        # Initialize
        print("\nInitializing servers...")
        await coordinator.initialize()
        print("[OK] All servers ready\n")
        
        # Run research with user preferences
        research = await coordinator.conduct_research(
            sectors=preferences["sectors"],
            risk_tolerance=preferences["risk_tolerance"],
            investment_goals=preferences["goals"]
        )
        
        # Display findings
        display_research_findings(research)
        
        # Generate AI summaries based on research data
        print("\n" + "="*80)
        print("AI-GENERATED INSIGHTS (Based on Research Data)")
        print("="*80)
        
        print("\n[SECTOR-GOAL ALIGNMENT]")
        print("-" * 80)
        sector_summary = generate_sector_goal_summary(research, preferences)
        print(f"  {sector_summary}")
        
        print("\n[KEY RISKS & NEWS CITATIONS]")
        print("-" * 80)
        risk_summary = generate_risk_summary_with_citations(research)
        print(f"  {risk_summary}")
        
        print("\n" + "="*80)
        print("ANALYSIS COMPLETE")
        print("="*80)
        
    except Exception as e:
        print(f"\n[ERROR] Error during analysis: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\nCleaning up...")
        await coordinator.cleanup()
        print("[OK] Done\n")


if __name__ == "__main__":
    asyncio.run(main())
