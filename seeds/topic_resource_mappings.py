"""Topic-name mappings for Phase 1. The adaptive planner does not consume these yet."""

QA_PRACTICE_MAP = {
    "Percentages": "2iim-qa-percents-profits",
    "Ratio and proportion": "2iim-qa-ratio-mixtures-averages",
    "Averages": "2iim-qa-ratio-mixtures-averages",
    "Profit and loss": "2iim-qa-percents-profits",
    "Simple and compound interest": "2iim-qa-percents-profits",
    "Mixtures and alligation": "2iim-qa-ratio-mixtures-averages",
    "Time and work": "2iim-qa-pipes-work-time",
    "Pipes and cisterns": "2iim-qa-pipes-work-time",
    "Time, speed and distance": "2iim-qa-speed-time-races",
    "Relative speed": "2iim-qa-speed-time-races",
    "Linear equations": "2iim-qa-linear-quadratic",
    "Quadratic equations": "2iim-qa-linear-quadratic",
    "Inequalities": "2iim-qa-inequalities",
    "Algebraic identities": "2iim-qa-fallback",
    "Logarithms": "2iim-qa-exponents-logarithms",
    "Functions": "2iim-qa-functions",
    "Progressions": "2iim-qa-progressions",
    "Divisibility": "2iim-qa-number-other",
    "Factors and multiples": "2iim-qa-factors",
    "Remainders": "2iim-qa-remainders",
    "Units digits / cyclicity": "2iim-qa-number-other",
    "HCF / LCM": "2iim-qa-hcf-lcm",
    "Number properties": "2iim-qa-number-other",
    "Lines and angles": "2iim-qa-geometry-core",
    "Triangles": "2iim-qa-geometry-core",
    "Circles": "2iim-qa-geometry-core",
    "Quadrilaterals / polygons": "2iim-qa-geometry-core",
    "Coordinate geometry basics": "2iim-qa-coordinate-geometry",
    "Mensuration": "2iim-qa-mensuration",
    "Permutations / combinations": "2iim-qa-permutation-probability",
    "Probability": "2iim-qa-permutation-probability",
    "Set theory": "2iim-qa-set-theory",
}

DILR_PRACTICE_MAP = {
    "Arrangements": "2iim-dilr-grid",
    "Distribution": "2iim-dilr-distribution",
    "Scheduling": "2iim-dilr-sequencing",
    "Selection": "2iim-dilr-selection",
    "Games and tournaments": "2iim-dilr-math",
    "Routes / networks": "2iim-dilr-routes-networks",
    "Tables": "2iim-dilr-tables",
    "Charts": "2iim-dilr-charts",
    "Caselets": "2iim-dilr-caselets",
    "Venn / set-based": "2iim-dilr-venn-set",
    "Mixed DI-LR": "2iim-dilr-mixed",
}

VARC_PRACTICE_MAP = {
    "Reading Comprehension": "2iim-varc-rc",
    "Para Summary": "2iim-varc-para-summary",
    "Odd Sentence": "2iim-varc-odd-sentence",
    "Para Completion": "2iim-varc-para-completion",
    "Para Ordering": "2iim-varc-para-ordering",
}


def build_topic_mappings(topic_rows):
    mappings = []
    for topic in topic_rows:
        topic_id, subject, name = topic["id"], topic["subject"], topic["name"]
        if subject == "Quant":
            practice = QA_PRACTICE_MAP.get(name, "2iim-qa-fallback")
            mappings.extend([
                (topic_id, "rodha-cat-free", "LEARN", 10, "ALL"),
                (topic_id, "2iim-question-bank", "PRACTICE", 30, "ALL"),
                (topic_id, practice, "PRACTICE", 10, "ALL"),
                (topic_id, "2iim-cat-pyq", "PYQ", 20, "ALL"),
            ])
        elif subject == "DILR":
            practice = DILR_PRACTICE_MAP[name]
            mappings.extend([
                (topic_id, "rodha-dilr-free", "LEARN", 20, "Foundation"),
                (topic_id, "2iim-dilr-foundation", "PRACTICE", 30, "ALL"),
                (topic_id, practice, "PRACTICE", 10, "ALL"),
                (topic_id, "2iim-cat-pyq", "PYQ", 20, "ALL"),
            ])
        elif subject == "VARC":
            practice = VARC_PRACTICE_MAP[name]
            paid = "varc1000-rc" if name == "Reading Comprehension" else "varc1000-va"
            mappings.extend([
                (topic_id, practice, "PRACTICE", 10, "ALL"),
                (topic_id, paid, "PRACTICE", 5, "ALL"),
                (topic_id, "2iim-cat-pyq", "PYQ", 20, "ALL"),
            ])
    return mappings
