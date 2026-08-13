"""Verified T.I.M.E. Foundation references supplied by the user.

Provider titles are deliberately stored verbatim. In particular, unknown provider
acronyms are not expanded into canonical topics.
"""

TIME_FOUNDATION_TESTS = [
    # Data Interpretation
    ("OBD1002101", "Tables 2", "DI", "TABLES", None, None, "HIGH"),
    ("OBD1002102", "Line graphs 2", "DI", "LINE_GRAPHS", None, None, "HIGH"),
    ("OBD1002103", "Bar/Stack graph 2", "DI", "BAR_STACK_GRAPHS", None, None, "HIGH"),
    ("OBD1002104", "Pie charts 2", "DI", "PIE_CHARTS", None, None, "HIGH"),
    ("OBD1002105", "Games/Tournaments 2", "DI", "GAMES_TOURNAMENTS", None, None, "HIGH"),
    ("OBD1002106", "3D and Networks 2", "DI", "NETWORKS", None, None, "HIGH"),
    ("OBD1002107", "Caselet; Maxima&Minima 2", "DI", "CASELETS", None, None, "HIGH"),
    ("OBD1002108", "Foundation-Reasoning based DI 2", "DI", "REASONING_BASED_DI", None, None, "HIGH"),
    ("OBL1001801", "Foundation - Tables - 1", "DI", "TABLES", None, None, "HIGH"),
    ("OBL1001816", "Foundation - Line graphs - 3", "DI", "LINE_GRAPHS", None, None, "HIGH"),
    ("OBL1001830", "Foundation - Line graphs - 4", "DI", "LINE_GRAPHS", None, None, "HIGH"),
    ("OBL1001839", "Foundation - 3 - D and Networks - 4", "DI", "NETWORKS", None, None, "HIGH"),
    # Logical Reasoning
    ("OBL1001812", "Foundation - Cubes and Binary Logic - 1", "LR", "CUBES_BINARY_LOGIC", None, None, "MEDIUM"),
    ("OBL1001814", "Foundation - Deductions and connectives - 1", "LR", "DEDUCTIONS_CONNECTIVES", None, None, "MEDIUM"),
    ("OBL1001826", "Foundation - Cubes and Binary Logic - 3", "LR", "CUBES_BINARY_LOGIC", None, None, "MEDIUM"),
    ("OBL1001828", "Foundation - Deductions and connectives - 3", "LR", "DEDUCTIONS_CONNECTIVES", None, None, "MEDIUM"),
    ("OBL1001840", "Foundation - Cubes and Binary Logic - 4", "LR", "CUBES_BINARY_LOGIC", None, None, "MEDIUM"),
    ("OBL1001842", "Foundation - Deductions and connectives - 4", "LR", "DEDUCTIONS_CONNECTIVES", None, None, "MEDIUM"),
    ("OBL1001845", "Foundation - OMET Qn types - 1", "LR", "OMET", None, None, "LOW"),
    ("OBL1001846", "Foundation - OMET Qn types - Verbal Reasoning - 1", "LR", "OMET_VERBAL_REASONING", None, None, "LOW"),
    ("OBL1001849", "Foundation - OMET Qn types - 2", "LR", "OMET", None, None, "LOW"),
    ("OBL1001851", "Foundation - Puzzles - Distribution, Selections, Comparisions - 3", "LR", "DISTRIBUTION_SELECTION_COMPARISON", None, None, "HIGH"),
    ("OBL1001852", "Foundation - OMET Qn types - 3", "LR", "OMET", None, None, "LOW"),
    # Quantitative Ability
    ("OBQ1001801", "Foundation - ERPV - 1", "QA", None, "ARITHMETIC", None, "HIGH"),
    ("OBQ1001802", "Foundation - PPL - 1", "QA", None, "ARITHMETIC", None, "HIGH"),
    ("OBQ1001803", "Foundation - Numbers - 1", "QA", None, "NUMBER_SYSTEMS", None, "HIGH"),
    ("OBQ1001804", "Foundation - ERPV, PPL, Numbers - 1", "QA", None, "MIXED", None, "HIGH"),
    ("OBQ1001805", "Foundation - Geo and Men - 1", "QA", None, "GEOMETRY_MENSURATION", None, "HIGH"),
    ("OBQ1001806", "Foundation - T and D - 1", "QA", None, "ARITHMETIC", "TIME_SPEED_DISTANCE", "HIGH"),
    ("OBQ1001807", "Foundation - T and W - 1", "QA", None, "ARITHMETIC", "TIME_WORK", "HIGH"),
    ("OBQ1001808", "Foundation - Geo and Men, T and D, T and W - 1", "QA", None, "MIXED", None, "HIGH"),
    ("OBQ1001809", "Foundation - Quant Based Data Sufficiency - 1", "QA", None, "DATA_SUFFICIENCY", None, "LOW"),
    ("OBQ1001810", "Foundation - AMA and SICI - 1", "QA", None, "ARITHMETIC", None, "HIGH"),
    ("OBQ1001811", "Foundation - ILS - 1", "QA", None, "ALGEBRA", None, "HIGH"),
    ("OBQ1001812", "Foundation - Quadratic Equations - 1", "QA", None, "ALGEBRA", "QUADRATIC_EQUATIONS", "HIGH"),
    ("OBQ1001813", "Foundation - AMA and SICI, QE, ILS - 1", "QA", None, "MIXED", None, "HIGH"),
    ("OBQ1001814", "Foundation - Inequalities and SP.Equations - 1", "QA", None, "ALGEBRA", "INEQUALITIES", "HIGH"),
    ("OBQ1001815", "Foundation - Progressions - 1", "QA", None, "ALGEBRA", "PROGRESSIONS", "HIGH"),
    ("OBQ1001816", "Foundation - P and C - 1", "QA", None, "MODERN_MATH", "PERMUTATION_COMBINATION", "HIGH"),
    ("OBQ1001817", "Foundation - Prob and Stat - 1", "QA", None, "MODERN_MATH", "PROBABILITY_STATISTICS", "HIGH"),
    ("OBQ1001818", "Foundation - Co - geo+Trigo+Nos system - 1", "QA", None, "MIXED", None, "HIGH"),
    ("OBQ1001819", "Foundation - FG and OB - 1", "QA", None, "ALGEBRA", None, "HIGH"),
    ("OBQ1001820", "Foundation - ERPV - 3", "QA", None, "ARITHMETIC", None, "HIGH"),
]


def seed_time_foundation_tests(connection):
    for reference, title, subject, category, group, topic, priority in TIME_FOUNDATION_TESTS:
        connection.execute(
            """
            INSERT OR IGNORE INTO time_foundation_tests(
                test_reference,provider_title,subject,level,category,
                canonical_topic_group,canonical_topic,cat_priority,cat_core
            ) VALUES(?,?,?,'FOUNDATION',?,?,?,?,?)
            """,
            (reference, title, subject, category, group, topic, priority, int(priority != "LOW")),
        )
