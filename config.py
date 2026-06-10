# ─────────────────────────────────────────────────────────────────────────
#  EDIT THIS FILE to tune your weekly report. Nothing else needs changing.
# ─────────────────────────────────────────────────────────────────────────

# The business you're monitoring.
BRAND_NAME = "Mark Miller Subaru"

# The exact questions each AI assistant gets asked every week.
PROMPTS = [
    "What can you tell me about Mark Miller Subaru in Salt Lake City?",
    "I'm in Salt Lake City and want to buy a Subaru. Which dealership should I go to?",
    "Is Mark Miller Subaru a reputable dealership? What do people say about them?",
    "What are the best Subaru dealerships near Salt Lake City, Utah?",
    "What's the difference between Mark Miller Subaru Midtown and Mark Miller Subaru Southtowne?",
    "Where should I take my Subaru for service in the Salt Lake City area?",
]

# The TRUE, CURRENT facts about your business.
GROUND_TRUTH = """
- Two locations:
    Mark Miller Subaru Midtown: 3535 S State Street, South Salt Lake, UT 84115
    Mark Miller Subaru Southtowne: 10920 S State Street, Sandy, UT 84070
- Sells new and used Subaru vehicles; full service and parts departments at both locations.
- (ADD: phone numbers, hours, current promotions, awards, and anything else
  you want the report to fact-check.)
"""

# Competitors to watch for in the answers.
COMPETITORS = [
    "Nate Wade Subaru",
]

# Which provider writes the weekly summary.
SYNTH_PREFERENCE = ["anthropic", "openai", "gemini", "perplexity"]
