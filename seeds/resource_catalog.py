VERIFIED_AT = "2026-08-12"
RODHA_URL = "https://www.rodha.co.in/blog/free-cat-2026-preparation-study-material"
TWO_IIM_URL = "https://iim-cat-questions-answers.2iim.com/"
PYQ_URL = "https://online.2iim.com/CAT-question-paper/"


def resource(
    resource_id: str,
    provider: str,
    title: str,
    subject: str,
    resource_type: str,
    *,
    url: str | None = None,
    platform_path: str | None = None,
    description: str = "",
    topic_slug: str | None = None,
    free: bool = True,
    requires_subscription: bool = False,
    difficulty: str | None = None,
):
    return {
        "id": resource_id,
        "provider": provider,
        "title": title,
        "description": description,
        "subject": subject,
        "topic_slug": topic_slug,
        "type": resource_type,
        "url": url,
        "platform_path": platform_path,
        "free": int(free),
        "requires_subscription": int(requires_subscription),
        "estimated_minutes": None,
        "recommended_question_count": None,
        "difficulty": difficulty,
        "active": 1,
        "last_verified_at": VERIFIED_AT,
    }


PROVIDER_RESOURCES = [
    resource("rodha-cat-free", "RODHA", "Rodha Free CAT 2026 Preparation", "QA", "COURSE", url=RODHA_URL, platform_path="Rodha Free CAT → Quant playlist → select the mapped topic", description="Primary free concept-learning source for CAT Quant and DILR.", difficulty="FOUNDATION"),
    resource("2iim-question-bank", "2IIM", "2IIM CAT Question Bank", "QA", "PRACTICE", url=TWO_IIM_URL, platform_path="CAT Quantitative Aptitude → choose the named topic", description="Primary topic-wise foundation and intermediate practice bank.", difficulty="FOUNDATION"),
    resource("2iim-cat-pyq", "CAT_PYQ", "CAT Previous Year Papers 2017–2025", "QA", "PYQ_LIBRARY", url=PYQ_URL, description="Primary CAT previous-year paper repository."),
    resource("ims-simcat-plus", "IMS", "IMS SimCAT Plus 2026", "QA", "MOCK", url="https://www.imsindia.com/simcat-plus-2026/", platform_path="IMS Dashboard → CAT → SimCAT Plus", free=False, requires_subscription=True),
    resource("time-aimcat-portal", "TIME", "T.I.M.E. AIMCAT Portal", "QA", "FULL_MOCK", url="https://www.time4education.com/", platform_path="T.I.M.E. student portal → AIMCAT → select the scheduled test", description="Portal entry for scheduled AIMCAT availability windows. Northstar never attempts to sign in.", free=False, requires_subscription=True),
    resource("time-turbo-sectionals", "TIME", "T.I.M.E. Turbo Advanced Sectionals", "QA", "SECTIONAL", url="https://www.time4education.com/", platform_path="T.I.M.E. student portal → CAT → Turbo / advanced sectionals", description="Selective section-level testing for evidence-backed weaknesses; protected from early overuse.", free=False, requires_subscription=True, difficulty="TIMED"),
    resource("varc1000", "VARC1000", "VARC1000 2026", "VARC", "COURSE", url="https://www.careerlauncher.com/cat-mba/varc1000/", platform_path="Career Launcher → VARC1000", free=False, requires_subscription=True),
    resource("gmat-official", "GMAC", "GMAT Official Prep", "GMAT", "DIAGNOSTIC", url="https://www.mba.com/gmat-exam-prep", platform_path="mba.com → Official Prep → Full-Length Exams → Practice Exam 1", description="Official GMAT Starter Kit and Practice Exam 1."),
]


QA_PRACTICE_CATEGORIES = {
    "percents-profits": ("Percents, Profit & Loss and SICI", "https://iim-cat-questions-answers.2iim.com/quant/arithmetic/percents-profits/"),
    "ratio-mixtures-averages": ("Ratios, Mixtures and Averages", "https://iim-cat-questions-answers.2iim.com/quant/arithmetic/ratio-mixtures-averages/"),
    "pipes-work-time": ("Pipes, Cisterns, Work and Time", "https://iim-cat-questions-answers.2iim.com/quant/arithmetic/pipes-cisterns-work-time/"),
    "speed-time-races": ("Speed, Time, Distance and Races", "https://iim-cat-questions-answers.2iim.com/quant/arithmetic/speed-time-races/"),
    "linear-quadratic": ("Linear and Quadratic Equations", "https://iim-cat-questions-answers.2iim.com/quant/algebra/linear-quadratic-equations/"),
    "inequalities": ("Inequalities", "https://iim-cat-questions-answers.2iim.com/quant/algebra/inequalities/"),
    "functions": ("Functions", "https://iim-cat-questions-answers.2iim.com/quant/algebra/functions/"),
    "polynomials": ("Polynomials", "https://iim-cat-questions-answers.2iim.com/quant/algebra/polynomials/"),
    "progressions": ("Progressions", "https://iim-cat-questions-answers.2iim.com/quant/algebra/progressions/"),
    "exponents-logarithms": ("Exponents and Logarithms", "https://iim-cat-questions-answers.2iim.com/quant/arithmetic/exponents-logarithms/"),
    "hcf-lcm": ("HCF and LCM", "https://iim-cat-questions-answers.2iim.com/quant/number-system/hcf-lcm/"),
    "factors": ("Factors", "https://iim-cat-questions-answers.2iim.com/quant/number-system/factors/"),
    "remainders": ("Remainders", "https://iim-cat-questions-answers.2iim.com/quant/number-system/remainders/"),
    "factorial": ("Factorials", "https://iim-cat-questions-answers.2iim.com/quant/number-system/factorial/"),
    "number-other": ("Digits and Number Properties", "https://iim-cat-questions-answers.2iim.com/quant/number-system/other/"),
    "geometry-core": ("Core Geometry and Triangles", "https://iim-cat-questions-answers.2iim.com/quant/geometry/geometry-triangles/"),
    "coordinate-geometry": ("Coordinate Geometry", "https://iim-cat-questions-answers.2iim.com/quant/geometry/co-ordinate-geometry/"),
    "mensuration": ("Mensuration", "https://iim-cat-questions-answers.2iim.com/quant/geometry/mensuration/"),
    "permutation-probability": ("Permutation, Combination and Probability", "https://iim-cat-questions-answers.2iim.com/quant/permutation-probability/"),
}

QA_RESOURCES = [
    resource(f"2iim-qa-{slug}", "2IIM", f"2IIM — {title}", "QA", "PRACTICE", url=url, topic_slug=slug, difficulty="CAT_LEVEL")
    for slug, (title, url) in QA_PRACTICE_CATEGORIES.items()
]
QA_RESOURCES += [
    resource("2iim-qa-fallback", "2IIM", "2IIM QA Question Bank", "QA", "PRACTICE", url=TWO_IIM_URL, platform_path="CAT Quantitative Aptitude → choose the named topic", difficulty="CAT_LEVEL"),
    resource("2iim-qa-set-theory", "2IIM", "2IIM — Set Theory", "QA", "PRACTICE", url=TWO_IIM_URL, platform_path="CAT Quantitative Aptitude → Set Theory", topic_slug="set-theory", difficulty="CAT_LEVEL"),
]

DILR_RESOURCES = [
    resource("rodha-dilr-free", "RODHA", "Rodha Free CAT LRDI", "DILR", "CONCEPT", url=RODHA_URL, platform_path="Rodha Free CAT → LRDI playlist", difficulty="FOUNDATION"),
    resource("2iim-dilr-foundation", "2IIM", "2IIM — DILR Foundation Bank", "DILR", "PRACTICE", url=TWO_IIM_URL, platform_path="CAT DILR → choose the named set category", difficulty="FOUNDATION"),
    resource("2iim-dilr-sequencing", "2IIM", "2IIM — Sequencing / Ordering", "DILR", "PRACTICE", url="https://iim-cat-questions-answers.2iim.com/LR_sequences/", topic_slug="sequencing-ordering", difficulty="CAT_LEVEL"),
    resource("2iim-dilr-grid", "2IIM", "2IIM — Grid / Arrangement Puzzles", "DILR", "PRACTICE", url="https://iim-cat-questions-answers.2iim.com/LR_grid/", topic_slug="grid-arrangements", difficulty="CAT_LEVEL"),
    resource("2iim-dilr-math", "2IIM", "2IIM — Mathematical Puzzles", "DILR", "PRACTICE", url="https://iim-cat-questions-answers.2iim.com/LR_math/", topic_slug="mathematical-puzzles", difficulty="CAT_LEVEL"),
]

for slug, title in {
    "distribution": "Distribution / Word Problems", "selection": "Selection / Other Patterns", "routes-networks": "Routes and Networks",
    "tables": "Tables and Multiple Graphs", "charts": "Charts", "caselets": "Caselets / Word Problems", "venn-set": "Venn and Set-based Problems", "mixed": "Mixed DI-LR",
}.items():
    DILR_RESOURCES.append(resource(f"2iim-dilr-{slug}", "2IIM", f"2IIM — {title}", "DILR", "PRACTICE", url=TWO_IIM_URL, platform_path=f"CAT DILR → {title}", topic_slug=slug, difficulty="CAT_LEVEL"))

VARC_RESOURCES = [
    resource("2iim-varc-rc", "2IIM", "2IIM — Reading Comprehension", "VARC", "PRACTICE", url="https://iim-cat-questions-answers.2iim.com/verbal/reading-comprehension/", topic_slug="reading-comprehension", difficulty="CAT_LEVEL"),
    resource("2iim-varc-para-summary", "2IIM", "2IIM — Para Summary", "VARC", "PRACTICE", url="https://iim-cat-questions-answers.2iim.com/verbal/para-summary/", topic_slug="para-summary", difficulty="CAT_LEVEL"),
    resource("2iim-varc-odd-sentence", "2IIM", "2IIM — Sentence Elimination", "VARC", "PRACTICE", url="https://iim-cat-questions-answers.2iim.com/verbal/sentence-elimination/", topic_slug="odd-sentence", difficulty="CAT_LEVEL"),
    resource("2iim-varc-para-completion", "2IIM", "2IIM — Paragraph Completion", "VARC", "PRACTICE", url=TWO_IIM_URL, platform_path="CAT Verbal Ability → Paragraph Completion", topic_slug="para-completion", difficulty="CAT_LEVEL"),
    resource("2iim-varc-para-ordering", "2IIM", "2IIM — Para Jumble / Ordering", "VARC", "PRACTICE", url=TWO_IIM_URL, platform_path="CAT Verbal Ability → Para Jumble", topic_slug="para-ordering", difficulty="CAT_LEVEL"),
    resource("varc1000-rc", "VARC1000", "VARC1000 — RC Short Drills", "VARC", "PRACTICE", url="https://www.careerlauncher.com/cat-mba/varc1000/", platform_path="VARC1000 → RC Short Drills", free=False, requires_subscription=True, difficulty="CAT_LEVEL"),
    resource("varc1000-va", "VARC1000", "VARC1000 — VA Short Drills", "VARC", "PRACTICE", url="https://www.careerlauncher.com/cat-mba/varc1000/", platform_path="VARC1000 → VA Short Drills", free=False, requires_subscription=True, difficulty="CAT_LEVEL"),
]

STUDY_RESOURCES = PROVIDER_RESOURCES + QA_RESOURCES + DILR_RESOURCES + VARC_RESOURCES

USER_RESOURCE_ACCESS = [
    ("RODHA", 1, "Rodha Free CAT", "Free concept-learning source"),
    ("2IIM", 1, "2IIM Question Bank", "Free public CAT question bank"),
    ("CAT_PYQ", 1, "CAT PYQs via 2IIM", "Free previous-year paper library"),
    ("GMAC", 1, "GMAT Official Starter Kit", "Free official starter resources"),
    ("IMS", 0, "IMS SimCAT Plus 2026", "Enable only after purchasing access"),
    ("VARC1000", 0, "VARC1000 2026", "Enable only after purchasing access"),
    ("TIME", 1, "T.I.M.E. AIMCAT", "Purchased access · primary scheduled full-mock series"),
    ("CAREER_LAUNCHER", 0, "Career Launcher CDC", "Optional paid test series"),
]
