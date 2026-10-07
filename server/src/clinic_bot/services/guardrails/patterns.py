"""Layer 1 pattern sets. Authored after eval/red_flags.dev.jsonl was frozen.

No negation handling by design: "no chest pain" matches. SPEC 6.3 recovers it.
"""

from __future__ import annotations

SELF_HARM: tuple[str, ...] = (
    r"\bkill(ing)?\s+my\s*self\b",
    r"\bend(ing)?\s+(my|his|her)\s+(own\s+)?life\b",
    r"\btake\s+my\s+(own\s+)?life\b",
    r"\bsuicid(e|al)\b",
    r"\b(hurt|harm|cut|cutting|harming|hurting)\s+my\s*self\b",
    r"\bself[\s-]?harm\b",
    r"\bno\s+point\s+(in\s+)?living\b",
    r"\b(don'?t|do\s+not)\s+want\s+to\s+(live|be\s+alive)\b",
    r"\bwant\s+to\s+die\b",
    r"\bbetter\s+off\s+dead\b",
    r"\bmar\s+jaa?na\s+chaht[aie]\b",
    r"\bjeena\s+nahi\s+chaht[aie]\b",
    r"\b(khudkushi|aatmahatya|atmahatye)\b",
    r"\bsaaya?bek(u|ide)\b",
)

EMERGENCY: tuple[str, ...] = (
    r"\bchest\s+(pain|tightness|pressure|heaviness|is\s+tight|feels\s+(tight|heavy))\b",
    r"\bchest\s+(feels|is)\s+\w*\s*(tight|heavy)\b",
    r"\b(pressure|pain|tightness)\s+in\s+(my|his|her|the)\s+chest\b",
    r"\bcrushing\s+(pain|pressure)\b",
    r"\b(can'?t|cannot|can\s+not|unable\s+to|difficulty|trouble|hard\s+to|struggling\s+to)\s+"
    r"(breathe|breathing)\b",
    r"\b(not|isn'?t|is\s+not|stopped)\s+breathing\b",
    r"\bshort(ness)?\s+of\s+breath\b",
    r"\bgasping\b",
    r"\b(unconscious|unresponsive|passed\s+out|blacked\s+out|collapsed|fainted|fainting)\b",
    r"\bnot\s+(responding|waking\s+up)\b",
    r"\b(heavy|uncontrolled|severe|lot\s+of)\s+bleeding\b",
    r"\bbleeding\s+(won'?t|will\s+not|doesn'?t|does\s+not|is\s+not|isn'?t)\s+stop",
    r"\bblood\s+(keeps|is)\s+(pouring|gushing|spurting)\b",
    r"\bstroke\b",
    r"\bface\s+(\w+\s+)?(is\s+)?(droop(ing|y)?|went\s+crooked|crooked)\b",
    r"\b(droop(ing)?|crooked)\s+(face|on\s+one\s+side)\b",
    r"\bslurred\s+speech\b|\bspeech\s+is\s+slurred\b",
    r"\bone\s+side\s+(is\s+)?(weak|numb)\b",
    r"\b(can'?t|cannot|unable\s+to)\s+move\s+(my|his|her)\s+(right|left)?\s*(arm|leg|side)\b",
    r"\b(seizures?|convulsions?|fits)\b",
    r"\b(anaphyla\w*|severe\s+allergic\s+reaction)\b",
    r"\bthroat\s+(is\s+)?(swelling|swollen|closing)\b",
    r"\b(lips?|tongue)\s+(and\s+\w+\s+)?(are|is)?\s*swell",
    r"\b(poison(ing|ed)?|overdose|overdosed)\b",
    r"\bswallowed\s+(some\s+)?(bleach|cleaning|poison|acid|kerosene|pesticide|phenyl)",
    r"\bsevere\s+burns?\b",
    r"\b(boiling|hot)\s+(oil|water)\b.{0,40}\b(burn|skin|peel)",
    r"\bsnake\s*bite\b|\bbitten\s+by\s+a\s+snake\b",
    # Romanised Hindi
    r"\b(seene|chhati|chaati|chhaati)\s+(mein|me|main)\s+(bahut\s+)?dard\b",
    r"\bdil\s+(mein|me)\s+dard\b",
    r"\bsaans\s+(nahi|nahin)\s+aa\s+rahi\b",
    r"\bsaans\s+lene\s+(mein|me)\s+(taklif|takleef|dikkat)\b",
    r"\bsaans\s+phool\s+rahi\b",
    r"\b(behosh|bebhosh|be\s+hosh)\b",
    r"\bkhoon\s+band\s+(nahi|nahin)\s+ho\s+raha\b",
    r"\bdora\s+pad\s+raha\b",
    r"\bmirgi\b",
    r"\bzeher\s+(kha|pee|pi)",
    # Romanised Kannada
    r"\bedhe\s+novu\b",
    r"\busiru\s+(kattide|aadtilla|aaguttilla)\b",
    r"\bprajne\s+illa\b",
    r"\brakta\s+nilthilla\b",
    r"\bmoorchhe\b",
)

_DRUG_SUFFIX = (
    r"\w+(mab|pril|olol|statin|cillin|mycin|azole|prazole|sartan|formin|cetamol|profen|zine"
    r"|tadine|oxacin|dipine)"
)
BRANDS = (
    "dolo",
    "crocin",
    "calpol",
    "combiflam",
    "pan-?d",
    "paracetamol",
    "ibuprofen",
    "aspirin",
    "azithromycin",
    "amoxicillin",
    "augmentin",
    "metformin",
    "cetirizine",
    "allegra",
    "saridon",
    "disprin",
    "digene",
    "benadryl",
    "ascoril",
    "montair",
    "telma",
    "thyronorm",
    "ecosprin",
    "shelcal",
    "pantoprazole",
    "omeprazole",
    "levocetirizine",
    "insulin",
)
_BRAND = r"\b(" + "|".join(BRANDS) + r")\b"

MEDICATION: tuple[str, ...] = (
    r"\b(dose|doses|dosage|dosing)\b",
    r"\b\d+\s*mg\b|\bmg\b",
    r"\btablets?\b|\bpills?\b|\bcapsules?\b|\bsyrup\b",
    r"\bhow\s+many\s+(tablets?|pills?|times)\b",
    r"\bcan\s+i\s+take\b",
    r"\bshould\s+i\s+(take|stop|skip)\b",
    r"\bwith\s+food\b|\bempty\s+stomach\b",
    r"\bside[\s-]?effects?\b",
    r"\binteract(ion|ions|s)?\b",
    r"\bused\s+for\b.{0,40}("
    + _BRAND
    + "|"
    + _DRUG_SUFFIX
    + r")|("
    + _BRAND
    + "|"
    + _DRUG_SUFFIX
    + r").{0,40}\bused\s+for\b",
    r"\bprescri(be|ption)\b",
    r"\b(medicine|medication|antibiotic|painkiller)s?\b.{0,30}\b(take|give|for|should|which|what)\b",
    r"\b(which|what)\s+(medicine|medication|antibiotic|painkiller)",
    _BRAND,
)

OFF_TOPIC: tuple[str, ...] = (
    r"\b(write|generate|debug|fix|create|give\s+me)\b.{0,30}\b(code|script|program|function|"
    r"essay|poem|joke)s?\b",
    r"\b(python|javascript|typescript|java|c\+\+|golang|rust|sql|html|css)\b",
    r"\btell\s+me\s+a\s+joke\b",
)
