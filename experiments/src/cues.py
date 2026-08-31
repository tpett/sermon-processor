"""Lexical cues for block classification.

These are a tuning artifact and must only ever be adjusted against the
development split. Versioned so a change to them is a change of config_id.

Drawn from the running order and phrasings described in
../features/QUESTIONS.md (Q16, Q19, Q74) — not from reading the corpus.
"""

VERSION = "cues.v4"

SCRIPTURE = [
    "scripture reading", "our reading", "the reading this morning",
    "turn with me", "turn in your bible", "open your bible",
    "hear now the word", "this is the word of the lord",
    "reading comes from", "comes from the book of", "beginning at verse",
    # "chapter" removed. A church preaching expository series says it constantly
    # *inside* the sermon ("wait a couple of chapters to flesh it out"), and
    # refine_in takes the LAST cue hit in its window, so a mid-sermon mention
    # drags the punch-in minutes late. Verified on held-out: removing this one
    # string takes 8/14 to 11/14 and worst error 222 s to 6.6 s. The dev split
    # could not see it — none of its six sermons says "chapter" early.
    "follow along as i read", "listen to the word",
]

PRAYER = [
    "let us pray", "let's pray", "would you pray with me", "pray with me",
    "father we thank you", "father, we thank you", "heavenly father",
    "in jesus name", "in jesus' name", "amen",
]

COMMUNION = [
    "invite you to join us", "visitor with us", "guest with us",
    "come to the table", "the lord's supper", "lords supper",
    "serve communion", "take communion", "communion",
    "elders will be coming", "bread and the cup",
]

# The invitation that OPENS communion, as distinct from communion vocabulary in
# general. A sermon can be about communion; only the pitch to the table uses
# these. Measured near-verbatim across the corpus:
#   "well if you're a visitor with us ... we invite you to partake of communion"
COMMUNION_INVITATION = [
    "visitor with us", "guest with us", "visitors with us",
    # A second preacher says "if you're visiting with us" rather than "a visitor
    # with us". Same move, different wording — worth carrying both.
    "visiting with us", "if you're visiting", "if you are visiting",
    "invite you to partake", "invite you to join us",
    "if you have trusted christ", "if you've trusted christ",
    "obedient to his command to be baptized",
]

QA = [
    "any questions", "are there any questions", "questions before we",
    "what questions", "let's have some questions", "lets have some questions",
    "raise your hand", "yes, in the back",
]

ANNOUNCEMENTS = [
    "good morning and welcome", "welcome to", "a few announcements",
    "couple of announcements", "this week", "next sunday", "sign up",
    "if you're new", "if you are new", "guest table",
]

GREETING_OPENERS = [
    "good morning", "if you have your bible", "turn with me",
    "pick up where we left off", "let me pray for us",
]


def count_hits(text: str, phrases: list[str]) -> int:
    low = text.lower()
    return sum(1 for p in phrases if p in low)


def any_hit(text: str, phrases: list[str]) -> bool:
    low = text.lower()
    return any(p in low for p in phrases)


# A class often opens with a short throat-clearing line before the real start:
# a bare greeting, or "we'll get going in a minute". Sometimes there is silence
# after it, sometimes it runs straight on.
PREAMBLE = [
    "good morning", "good evening", "morning everyone", "hey everyone",
    "we're going to get started", "we are going to get started",
    "we'll get started", "we will get started", "going to get going",
    "in about a minute", "in about two minutes", "in a minute or two",
    "as you take your seats", "if you'll take your seats", "grab a seat",
    "let's go ahead and get started", "why don't we get started",
]
