# T-07: Portfolio Advisor

Owner instruction, 2026-10-10: Sentinel acts like a personal portfolio manager that advises; the owner executes every transaction. Idea PDF pp21–23, 36–37.

## Rules
- No bank or broker credentials and no order placement, ever.
- Market data read-only through the egress guard; each new data host added to the allowlist with owner approval.
- All numbers come from deterministic code; the model only explains.
- Recommendations show reasons, ranges and risks; never guaranteed returns. Label: educational analysis, not licensed advice.

## Open questions for the owner
- Which broker / app (Zerodha, Groww, Upstox, other)? Determines the import format.
- Mutual funds, shares, or both?

## Report
2026-10-10: first version done. `app/core/portfolio.py` (CSV import for Zerodha/Groww/CAMS-style exports, calculator, SIP/lumpsum ranges, rule-based suggestions with reasons and do-it-yourself steps, AMFI NAV + NSE price fetch on demand), `app/portfolio_routes.py`, Portfolio screen, chat skill `portfolio_advisor` (read-only, approval required). Tests: `tests/integration/test_portfolio.py` (12). Live check: AMFI list (32,512 entries) parses; fund names matched only when near-exact and the same Direct/Regular and Growth/IDCW; INFY price fetched.
Not yet: broker-specific tuning (owner has not named the broker), XIRR from transaction history, fund expense ratios/overlap, tax estimates, news.
