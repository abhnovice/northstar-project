The Northstar MBA Prep OS application is already built and functional.

Do NOT rebuild the application from scratch.

I now want you to upgrade the existing application so that every generated study task is linked to **specific, actionable study material** rather than generic descriptions such as:

* "IMS module"
* "CAT PYQs"
* "Solve 25 questions"
* "2 RC passages"
* "2 DILR sets"

The goal is that when I open Northstar tonight, I should be able to click directly from my study plan into the material I am supposed to study.

The experience should become:

**Plan → Open exact material → Study → Record result → Adapt future plan**

rather than:

**Plan → manually figure out where to study from**

---

# 1. First fix the date bug

The current UI screenshot shows:

**Monday, August 31**
and
**90 days remaining**

This is incorrect.

The preparation plan begins on **August 12, 2026**, and the application's current date must come from the actual current date in the **Asia/Kolkata** timezone.

Do NOT use August 31 as a hard-coded "today".

Implement:

```ts
APP_TIMEZONE = "Asia/Kolkata"
CAT_DATE = "2026-11-29"
PREP_START_DATE = "2026-08-12"
```

`PREP_START_DATE` is the start of my preparation.

It is NOT the application's permanent current date.

All of these must dynamically derive from the actual date:

* dashboard date
* CAT countdown
* today's plan
* deadline countdowns
* phase
* revision queue
* backlog
* work experience
* weekly review

Use a timezone-safe date library if required.

---

# 2. Main product change

Every study task must have one or more concrete resources attached.

For example, replace:

> Averages: learn → solve → test
> IMS module + CAT PYQs
> 35 target

with something closer to:

### Averages

#### LEARN · 40 min

**Rodha — Arithmetic: Averages**

`Open learning material ↗`

#### PRACTICE · 55 min

**2IIM — Ratios, Mixtures & Averages**

20 questions
Target accuracy: ≥80%

`Start practice ↗`

#### CAT APPLICATION · 35 min

**CAT Previous Year Questions**

5–8 relevant Arithmetic questions

`Open CAT PYQs ↗`

#### REVIEW · 15 min

Record:

* questions attempted
* questions correct
* accuracy
* confidence
* reusable errors

Northstar should then use this performance when scheduling future work.

---

# 3. link to study material

Very important:

Northstar should **link to study material**.

store things like:

* resource title
* provider
* URL
* topic
* access instructions
* platform path
* completion metadata

---

# 4. Resource architecture

Create proper database models rather than hard-coding links directly into React components.

Add something conceptually equivalent to:

```ts
type ResourceProvider =
  | "RODHA"
  | "2IIM"
  | "IMS"
  | "VARC1000"
  | "GMAC"
  | "CAT_PYQ"
  | "USER";

type ResourceType =
  | "CONCEPT"
  | "PRACTICE"
  | "PYQ"
  | "SECTIONAL"
  | "MOCK"
  | "READING"
  | "VIDEO"
  | "COURSE"
  | "DIAGNOSTIC";

type StudyResource = {
  id: string;
  provider: ResourceProvider;
  title: string;
  description?: string;

  subject: "QA" | "DILR" | "VARC" | "GMAT" | "ISB";

  topicSlug?: string;

  type: ResourceType;

  url?: string;

  // Useful for logged-in platforms where deep URLs may not be stable.
  platformPath?: string;

  free: boolean;
  requiresSubscription: boolean;

  estimatedMinutes?: number;
  recommendedQuestionCount?: number;
  difficulty?: "FOUNDATION" | "INTERMEDIATE" | "CAT_LEVEL";

  active: boolean;

  lastVerifiedAt?: Date;
};
```

Create:

```ts
TopicResourceMap
```

containing:

```ts
topicId
resourceId
purpose
priority
phase
```

where `purpose` can be:

```ts
LEARN
PRACTICE
PYQ
REVISION
SECTIONAL
MOCK
```

Also create:

```ts
UserResourceAccess
```

with:

```ts
resourceProvider
enabled
subscriptionName
notes
```

---

# 5. My default material stack

Seed the following providers.

## FREE / AVAILABLE

Enable by default:

* Rodha Free CAT resources
* 2IIM CAT Question Bank
* 2IIM CAT Previous Year Papers
* GMAC Official Starter Kit

## PAID / USER TOGGLE

Create disabled-by-default toggles for:

* IMS SimCAT Plus 2026
* VARC1000 2026
* TIME AIMCAT
* Career Launcher CDC

I should be able to enable these under:

**Settings → Study Material / Subscriptions**

Example:

```text
STUDY MATERIAL

FREE

✓ Rodha Free CAT
✓ 2IIM Question Bank
✓ CAT PYQs via 2IIM
✓ GMAT Official Starter Kit

PAID

□ IMS SimCAT Plus
□ VARC1000
□ TIME AIMCAT
□ Career Launcher CDC
```

Once I enable a provider, the planner can start allocating that material.

Never allocate a paid resource that I have not marked as available.

---

# 6. Seed these provider-level resources

Use these as configurable seed data.

```ts
const providers = [
  {
    id: "rodha-cat-free",
    provider: "RODHA",
    title: "Rodha Free CAT 2026 Preparation",
    url: "https://www.rodha.co.in/blog/free-cat-2026-preparation-study-material",
    free: true,
    requiresSubscription: false,
    description:
      "Primary free concept-learning source for CAT Quant and DILR."
  },

  {
    id: "2iim-question-bank",
    provider: "2IIM",
    title: "2IIM CAT Question Bank",
    url: "https://iim-cat-questions-answers.2iim.com/",
    free: true,
    requiresSubscription: false,
    description:
      "Primary topic-wise CAT-level practice bank."
  },

  {
    id: "2iim-cat-pyq",
    provider: "CAT_PYQ",
    title: "CAT Previous Year Papers 2017–2025",
    url: "https://online.2iim.com/CAT-question-paper/",
    free: true,
    requiresSubscription: false,
    description:
      "Primary CAT previous-year paper repository."
  },

  {
    id: "ims-simcat-plus",
    provider: "IMS",
    title: "IMS SimCAT Plus 2026",
    url: "https://www.imsindia.com/simcat-plus-2026/",
    platformPath: "IMS Dashboard → CAT → SimCAT Plus",
    free: false,
    requiresSubscription: true
  },

  {
    id: "varc1000",
    provider: "VARC1000",
    title: "VARC1000 2026",
    url: "https://www.careerlauncher.com/cat-mba/varc1000/",
    platformPath: "Career Launcher → VARC1000",
    free: false,
    requiresSubscription: true
  },

  {
    id: "gmat-official",
    provider: "GMAC",
    title: "GMAT Official Prep",
    url: "https://www.mba.com/exam-prep",
    free: true,
    requiresSubscription: false
  }
];
```

Do not assume the URLs remain permanent forever.

Put them in database/configuration rather than scattered throughout components.

Allow editing them from the Resources page.

---

# 7. QA resource mapping

Use **Rodha primarily for concept learning**.

Use **2IIM primarily for topic practice**.

Use **CAT PYQs primarily for CAT-level transfer/testing**.

Create the following initial mappings.

---

## ARITHMETIC

### Percentages

LEARN:

```text
Rodha
CAT Quant → Arithmetic → Percentages
```

PRACTICE:

```text
2IIM
https://iim-cat-questions-answers.2iim.com/quant/arithmetic/percents-profits/
```

PYQ:

```text
CAT Previous Papers
https://online.2iim.com/CAT-question-paper/
```

---

### Profit & Loss

LEARN:

```text
Rodha → Arithmetic → Profit & Loss
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/arithmetic/percents-profits/
```

PYQ:

```text
https://online.2iim.com/CAT-question-paper/
```

---

### Simple Interest / Compound Interest

LEARN:

```text
Rodha → Arithmetic → SI / CI
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/arithmetic/percents-profits/
```

---

### Ratios & Proportion

LEARN:

```text
Rodha → Arithmetic → Ratio & Proportion
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/arithmetic/ratio-mixtures-averages/
```

---

### Averages

LEARN:

```text
Rodha → Arithmetic → Averages
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/arithmetic/ratio-mixtures-averages/
```

---

### Mixtures & Alligation

LEARN:

```text
Rodha → Arithmetic → Mixtures / Alligation
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/arithmetic/ratio-mixtures-averages/
```

---

### Time & Work

LEARN:

```text
Rodha → Arithmetic → Time & Work
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/arithmetic/pipes-cisterns-work-time/
```

---

### Pipes & Cisterns

LEARN:

```text
Rodha → Arithmetic → Pipes & Cisterns
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/arithmetic/pipes-cisterns-work-time/
```

---

### Time, Speed & Distance

LEARN:

```text
Rodha → Arithmetic → Time Speed Distance
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/arithmetic/speed-time-races/
```

---

### Races / Relative Speed

LEARN:

```text
Rodha → TSD → Relative Speed / Races
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/arithmetic/speed-time-races/
```

---

## ALGEBRA

### Linear Equations

LEARN:

```text
Rodha → Algebra → Linear Equations
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/algebra/linear-quadratic-equations/
```

---

### Quadratic Equations

LEARN:

```text
Rodha → Algebra → Quadratic Equations
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/algebra/linear-quadratic-equations/
```

---

### Inequalities / Modulus

LEARN:

```text
Rodha → Algebra → Inequalities
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/algebra/inequalities/
```

---

### Functions

LEARN:

```text
Rodha → Algebra → Functions
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/algebra/functions/
```

---

### Polynomials

LEARN:

```text
Rodha → Algebra → Polynomials
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/algebra/polynomials/
```

---

### Progressions

LEARN:

```text
Rodha → Algebra → AP / GP / Progressions
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/algebra/progressions/
```

---

### Logarithms & Exponents

LEARN:

```text
Rodha → Algebra → Logarithms / Exponents
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/arithmetic/exponents-logarithms/
```

---

## NUMBER SYSTEMS

### HCF / LCM

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/number-system/hcf-lcm/
```

---

### Factors

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/number-system/factors/
```

---

### Remainders

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/number-system/remainders/
```

---

### Factorials

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/number-system/factorial/
```

---

### Digits / Number Properties

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/number-system/other/
```

---

## GEOMETRY

### Triangles / Circles / Polygons / Core Geometry

LEARN:

```text
Rodha → Geometry
```

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/geometry/geometry-triangles/
```

---

### Coordinate Geometry

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/geometry/co-ordinate-geometry/
```

---

### Mensuration

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/geometry/mensuration/
```

---

### Trigonometry

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/geometry/trigonometry/
```

---

## MODERN MATH

### Permutation & Combination

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/permutation-probability/
```

---

### Probability

PRACTICE:

```text
https://iim-cat-questions-answers.2iim.com/quant/permutation-probability/
```

---

### Set Theory

Use the 2IIM Set Theory category where available.

The implementation should allow the resource URL to be corrected from the Resources UI if the provider changes its routing.

---

# 8. QA task-generation rules

For a completely new QA topic:

```text
LEARN
30–60 min concept material

PRACTICE FOUNDATION
10–15 questions

PRACTICE CAT LEVEL
10–15 questions

REVIEW
analyse mistakes
```

Do NOT immediately assign 40 difficult CAT questions after one concept video.

As mastery improves:

### Confidence 1/5

Concept + basic practice.

### Confidence 2/5

More topic practice.

### Confidence 3/5

CAT-level practice + first PYQs.

### Confidence 4/5

Timed topic test / sectional integration.

### Confidence 5/5

Revision + mixed practice only.

---

# 9. DILR resource mapping

Create structured DILR categories.

Use Rodha for learning representation/approach.

Use 2IIM for public practice.

Use IMS DILR practice when I enable IMS.

Map:

---

### Sequencing / Ordering

```text
https://iim-cat-questions-answers.2iim.com/LR_sequences/
```

---

### Grid / Arrangement Puzzles

```text
https://iim-cat-questions-answers.2iim.com/LR_grid/
```

---

### Mathematical Puzzles

```text
https://iim-cat-questions-answers.2iim.com/LR_math/
```

---

2IIM also exposes categories for:

* Pie Charts
* Multiple Graphs
* Word Problems
* Line Graphs
* Bar Graphs
* Visualisation
* Other Patterns

Create resources for these category names using their public 2IIM category navigation wherever the existing URLs are stable.

Do not fabricate a URL if you cannot verify it from the repository/config.

If unsure, fall back to:

```text
https://iim-cat-questions-answers.2iim.com/
```

with a `platformPath` such as:

```text
CAT DILR → Pie Charts
```

This is preferable to creating a broken deep link.

---

# 10. DILR daily assignment logic

During foundation phase:

Assign approximately **2 sets/day**.

The task should look like:

### DILR Set 1 — Grid Arrangement

**Source**

2IIM → Grid Puzzle

`Open set bank ↗`

**Target**

25–30 min maximum initial attempt.

Then capture:

* solved: yes/no
* time taken
* number of questions
* number correct
* representation
* opening insight
* clue missed
* CAT selectability

CAT selectability options:

```text
YES
MAYBE
NO
```

Representation:

```text
TABLE
GRID
SLOTS
TIMELINE
NETWORK
EQUATIONS
VENN
DIAGRAM
OTHER
```

---

### DILR Set 2 — Sequencing

Use a different set type wherever possible.

Northstar should avoid assigning:

```text
Grid
Grid
Grid
Grid
```

for several consecutive days.

Use rotation.

---

# 11. DILR adaptive rules

Track performance by set category.

Example:

```text
Arrangements
12 sets
8 solved
67% solve rate
Median time 31m

Games & tournaments
8 sets
2 solved
25% solve rate
Median time 41m
```

The planner should identify:

**Games & tournaments = weak**

and increase exposure moderately.

Do NOT allocate nothing but games/tournaments tomorrow.

Use approximately:

```text
1 weak-area set
+
1 mixed/normal set
```

during foundation.

Later:

```text
timed 40-minute DILR sectionals
```

become more important than isolated sets.

---

# 12. CAT DILR PYQs

Use:

```text
https://online.2iim.com/CAT-question-paper/
```

as the primary PYQ gateway.

During early foundation:

Prefer topic practice.

From September onward:

begin introducing complete CAT DILR sets.

From October onward:

PYQ set practice should become significantly more common.

---

# 13. VARC material architecture

Create TWO possible VARC modes.

## MODE A — VARC1000 enabled

When I enable VARC1000, use it as the main structured learning curriculum.

Assignments can include:

```text
VARC1000 → Concept Lesson
VARC1000 → RC Short Drill
VARC1000 → VA Short Drill
VARC1000 → Strategy Drill
VARC1000 → Sectional
VARC1000 → Article Dose
```

Because VARC1000 is login-protected, use:

```text
platformPath
```

rather than pretending every lesson has a permanent public deep URL.

Example:

```ts
{
  provider: "VARC1000",
  title: "RC Short Drill",
  platformPath: "VARC1000 → RC Short Drills",
  requiresSubscription: true
}
```

Allow me to manually edit the task to store the exact drill number I completed.

---

## MODE B — VARC1000 disabled

Use 2IIM + CAT PYQs.

### Reading Comprehension

```text
https://iim-cat-questions-answers.2iim.com/verbal/reading-comprehension/
```

### Para Summary

```text
https://iim-cat-questions-answers.2iim.com/verbal/para-summary/
```

### Odd Sentence / Sentence Elimination

```text
https://iim-cat-questions-answers.2iim.com/verbal/sentence-elimination/
```

CAT PYQ gateway:

```text
https://online.2iim.com/CAT-question-paper/
```

---

# 14. VARC daily plan

During August/early foundation:

Typical assignment:

### RC 1

1 passage.

### RC 2

1 passage.

### VA

4–6 questions.

Possible split:

```text
2 Para Summary
2 Odd Sentence
1–2 other VA questions
```

Do not simply record:

```text
2 RC done
```

Capture:

```text
passages
questions
correct
incorrect
accuracy
time
```

and mistake categories.

---

# 15. VARC error labels

Already support or add:

```text
EXTREME_OPTION
SCOPE_SHIFT
UNSUPPORTED_INFERENCE
AUTHOR_VIEW_VS_EXAMPLE
CAUSE_EFFECT_REVERSAL
PARTIALLY_CORRECT
MISSED_QUALIFIER
MISREAD_QUESTION
TIME_PRESSURE
CLOSE_CALL
OTHER
```

Northstar should calculate:

```text
Last 50 VARC errors

Scope shift: 28%
Unsupported inference: 22%
Extreme option: 18%
...
```

and show a recommendation such as:

> Your most frequent VARC error is scope expansion. During today's RC review, explicitly compare the scope of the passage with each close option.

---

# 16. Reading material

Do not require newspaper reading as a substitute for RC practice.

Reading is supplementary.

Create optional reading resources.

Allow sources such as:

* Aeon
* The Guardian Long Read
* Smithsonian
* The Atlantic
* JSTOR Daily
* Scientific American
* Economist-style analytical articles where accessible
* user-added sources

Do not allocate more than approximately **20–30 min/day** of general reading unless explicitly requested.

CAT RC practice remains the priority.

---

# 17. IMS integration

If:

```text
IMS SimCAT Plus = ENABLED
```

Northstar should use IMS primarily for:

* full mocks
* sectionals
* additional DILR practice
* additional RC practice
* VA practice

Because IMS requires login and exact internal URLs can change, store:

```text
provider = IMS
platformPath
```

Example:

```text
IMS Dashboard → SimCAT 4
IMS Dashboard → QA Sectional 3
IMS Dashboard → DILR Practice → Set 14
```

Let me manually assign or edit the exact test/set number.

Do not pretend Northstar can access my IMS account automatically.

---

# 18. Mock allocation

Create an actual mock sequence.

Target:

```text
25–30 deeply analysed mocks before CAT.
```

Seed the schedule according to preparation phase.

### August

1/week.

### September

1–2/week.

### October

2/week initially.

Then 2–3/week late October.

### Early/mid November

Approximately 3/week if recovery and analysis are good.

### Final week

0–1.

Every mock task should link to its provider.

Example:

### FULL MOCK

**IMS SimCAT 01**

2 hr

`Open IMS ↗`

Then automatically schedule:

### MOCK ANALYSIS

180 min.

### RE-SOLVE

60 min.

The combination consumes the full six-hour day.

Never add a standard six-hour curriculum on top.

---

# 19. Previous CAT papers

Add a dedicated resource:

```text
CAT PYQ Library
https://online.2iim.com/CAT-question-paper/
```

The library currently needs to be treated as a separate type:

```ts
type = PYQ_LIBRARY
```

Northstar should allow the user to log:

```text
Year
Slot
Section
Question/set references
Attempted
Correct
Incorrect
Time
```

Do not copy the question content.

---

# 20. PYQ preservation

Do NOT burn through all recent CAT papers immediately.

Add a configuration:

```ts
const PYQ_POLICY = {
  earlyPhaseYears: ["older available PYQs"],
  recentPaperPreservation: true
}
```

During August:

Use mostly:

* topic-wise CAT questions
* selected PYQs

Do not allocate entire recent CAT papers casually.

During October/November:

complete recent CAT papers become valuable simulation material.

The exact paper-preservation strategy should remain configurable.

---

# 21. GMAT resource system

Create dedicated GMAT resources.

Primary resource:

**GMAT Official Prep**

```text
https://www.mba.com/exam-prep
```

The first mandatory GMAT task should be:

### Official GMAT Diagnostic

Target:

**First week of September 2026**

Material:

```text
GMAT Official Practice Exam 1
```

Platform:

```text
mba.com → Official Prep → Full-Length Exams → Practice Exam 1
```

Record:

* Total Score
* Quantitative Reasoning
* Verbal Reasoning
* Data Insights
* Date
* Notes

Do NOT use a random unofficial diagnostic as the primary baseline.

---

# 22. GMAT study allocation

Until diagnostic:

CAT dominates.

After diagnostic, assign approximately:

```text
30 min
3–4 days/week
```

for GMAT-specific material initially.

Priorities:

* Critical Reasoning
* Data Insights
* GMAT format
* pacing
* question review

Do not duplicate hours of arithmetic already covered through CAT unless the diagnostic indicates a GMAT Quant problem.

---

# 23. Add "Open material" directly to task cards

The Today screen currently has task rows.

Enhance them.

For every task display:

```text
[SUBJECT] [PRIORITY]

Task title

Resource:
Provider · Material title

Open material ↗

Target:
20 questions · ≥80% accuracy

Duration:
55 min
```

If there are several stages:

```text
LEARN
Rodha → Averages
[Open ↗]

PRACTICE
2IIM → Ratios, Mixtures & Averages
[Open ↗]

PYQ
CAT Question Papers
[Open ↗]
```

Use icons sparingly.

Keep the existing Northstar visual style.

---

# 24. Start task mode

When I press:

**Start tonight's plan**

open a focused study view.

For current task show:

```text
8:00–8:40

LEARN
Percentages

Rodha
Arithmetic → Percentages

[OPEN MATERIAL ↗]
```

Provide:

```text
Start timer
Pause
Mark complete
Add note
Add error
```

When learning time finishes:

```text
NEXT

PRACTICE
2IIM Percentages / Profit-Loss / SICI

15 questions
Target ≥80%

[OPEN PRACTICE ↗]
```

This should feel like guided execution, not a static calendar.

---

# 25. Completion dialog

When a practice task finishes, show:

### Record performance

```text
Questions attempted: [ ]

Correct: [ ]

Incorrect: [ ]

Time spent: [ ]

Confidence: 1 2 3 4 5
```

Automatically calculate:

```text
Accuracy
average time/question
```

Ask:

```text
Any reusable mistake?
```

Options:

```text
No
Add to Error Log
```

---

# 26. Adaptive QA decision

Example:

Averages practice:

```text
20 attempted
18 correct
90%
confidence 4/5
```

CAT PYQs:

```text
6 attempted
5 correct
83%
```

Decision:

```text
Mark topic = PRACTISING/STRONG
Schedule spaced revision
Move on
```

But:

```text
20 attempted
11 correct
55%
confidence 2/5
```

Decision:

```text
Keep topic = PRACTISING
Schedule concept repair
Schedule 10–15 additional questions
Do not immediately move to difficult PYQs
```

---

# 27. Difficulty progression

Implement:

```text
FOUNDATION
↓
INTERMEDIATE
↓
CAT LEVEL
↓
TIMED
↓
MIXED
```

A new topic should not jump directly from:

```text
watched video
```

to:

```text
hardest CAT questions
```

unless performance data justifies it.

---

# 28. Resource-selection algorithm

When generating a task:

### Step 1

Identify required:

```text
subject
topic
purpose
difficulty
```

### Step 2

Find all enabled resources matching it.

### Step 3

Rank using:

```text
exact topic match
purpose match
provider priority
subscription access
difficulty
unused/underused material
```

### Step 4

Choose primary resource.

### Step 5

If appropriate add secondary resource.

Example:

```text
Topic: Percentages

Primary Learn:
Rodha

Primary Practice:
2IIM

Transfer:
CAT PYQs
```

---

# 29. Resource fallback rules

Never produce a dead task because there is no exact deep link.

Fallback order:

```text
1. exact deep link
2. provider category page
3. provider landing page + exact platformPath
4. generic resource library
```

Example:

Prefer:

```text
2IIM → Grid Puzzle
```

over:

```text
2IIM homepage
```

But if an exact URL is unverified:

display:

```text
2IIM CAT Question Bank
Path: DILR → Other Patterns
```

instead of fabricating the URL.

---

# 30. Resources page redesign

Upgrade Resources.

Sections:

## My Active Resources

Show enabled providers.

## Free CAT Resources

Rodha

2IIM Question Bank

CAT PYQs

## Paid Resources

IMS SimCAT Plus

VARC1000

TIME

Career Launcher

## GMAT

GMAT Official Prep

## My Resources

Allow me to add custom:

* URL
* PDF
* book
* YouTube playlist
* Google Drive folder
* local notes
* course

Fields:

```text
Title
Provider
Subject
Topic
Type
URL
Platform path
Difficulty
Free/paid
Enabled
Notes
```

---

# 31. Add resource health

Show a small indicator:

```text
Verified
Needs verification
Broken link
User supplied
```

For public URLs, optionally implement a lightweight URL-check mechanism.

Do NOT repeatedly hammer third-party websites.

Checking manually/on explicit refresh is sufficient.

---

# 32. Add "replace resource"

Every task should support:

```text
Replace material
```

Example:

Northstar assigned Rodha but I prefer a particular IMS lesson.

Click:

```text
Replace
```

and choose another enabled resource.

Remember this preference if I choose:

```text
Use this provider for future Averages learning
```

---

# 33. Provider preferences

Under Settings support:

### QA Concepts

```text
Primary: Rodha
Fallback: User resources
```

### QA Practice

```text
Primary: 2IIM
Secondary: IMS
```

### DILR

```text
Primary: 2IIM
Secondary: IMS
```

### VARC

If VARC1000 disabled:

```text
2IIM
```

If VARC1000 enabled:

```text
VARC1000
```

### Mocks

If IMS enabled:

```text
IMS
```

---

# 34. Initial recommended stack UI

Create a card saying:

### Recommended Northstar Setup

**Concepts**

Rodha

**CAT question practice**

2IIM

**CAT PYQs**

2IIM CAT Paper Library

**Mocks**

IMS SimCAT Plus

**VARC structured course**

VARC1000

**GMAT**

Official GMAC Prep

Allow:

```text
Apply recommended setup
```

Do not purchase anything automatically.

---

# 35. First 7 days should become concrete

Regenerate my starting plan using actual resources.

Assuming preparation starts August 12:

## Day 1

QA:

Percentages.

* Rodha concept learning
* 2IIM Percentages practice

DILR:

* 2IIM Grid Puzzle
* 2IIM Sequencing

VARC:

* 2IIM RC
* Para Summary

Admin:

* CAT registration task

---

## Day 2

FULL CAT DIAGNOSTIC.

If IMS isn't enabled:

allow:

```text
Use another diagnostic
```

and let me enter provider/name.

Follow with analysis.

---

## Day 3

QA:

Ratio & Proportion.

Practice:

2IIM Ratios / Mixtures / Averages.

DILR:

Math Puzzle + Grid.

VARC:

2 RC + Odd Sentence.

Plus mock-error repair.

---

Continue building Days 4–7 similarly around:

* Averages
* Profit & Loss
* SI/CI
* revision of Percentages/Ratio
* DILR rotation
* daily VARC
* one recovery/weekly review component

Do not create 40 hours of backlog if the diagnostic replaces an entire day's schedule.

---

# 36. Deadline tasks also need links

For example:

### CAT registration

The task should contain:

```text
Official CAT website
[Open registration portal ↗]
```

Store official administrative resources separately from study providers.

Tag:

```text
OFFICIAL
```

Do not intermingle them with coaching resources.

---

# 37. Do not hard-code questionable assumptions

Anything that can change annually should live in data/config:

* CAT dates
* deadlines
* exam pattern
* provider links
* provider course names
* mock counts
* GMAT policies
* ISB deadlines

Add:

```text
lastVerifiedAt
sourceUrl
```

where appropriate.

---

# 38. Preserve my existing application

Keep:

* existing Northstar design
* current sidebar
* Dashboard
* Today
* Calendar
* QA
* DILR
* VARC
* Mocks
* Error Log
* GMAT
* ISB
* Analytics
* Weekly Review
* Deadlines
* Profile
* Settings

Do not redesign everything.

This is an enhancement of the existing app.

---

# 39. QA page enhancement

For every QA topic show:

```text
Averages

Status
Practising

Concept resource
Rodha
[Open]

Practice resource
2IIM
[Open]

PYQs
CAT Paper Library
[Open]

Questions
42

Accuracy
81%

Confidence
3/5

Next revision
Aug 17
```

---

# 40. DILR page enhancement

Category cards:

```text
Grid / Arrangements

Sets attempted: 14
Solved: 9
Solve rate: 64%
Median time: 29 min
Confidence: 3/5

Primary bank:
2IIM Grid Puzzle

[Practice another set]
```

---

# 41. VARC page enhancement

Display:

```text
RC passages completed
RC accuracy
VA accuracy
Average RC time
```

and:

```text
Most common mistake:
Scope Shift
```

Then:

```text
Recommended next drill:
RC passage + close-option analysis
```

with actual resource attached.

---

# 42. Prevent resource overload

Do not show 12 recommended sources for every topic.

Default display:

```text
Primary
Secondary
```

Maximum.

Additional resources can live behind:

```text
More options
```

Northstar should help me decide what to use, not create another research problem.

---

# 43. Resource coverage audit

Create a development-time validation script.

Every active CAT topic should have:

```text
at least 1 LEARN source OR be marked practice-only
at least 1 PRACTICE source
at least 1 PYQ fallback
```

Every DILR category should have:

```text
at least one practice source
```

VARC should have:

```text
RC source
VA source
PYQ source
```

GMAT should have:

```text
official diagnostic source
```

Fail seed validation if an important topic has no usable resource mapping.

---

# 44. Do not make API integrations where none exist

Northstar does NOT need to log into:

* IMS
* Career Launcher
* Rodha
* GMAC

for v1.

Just:

```text
Open external material
↓
User studies
↓
User returns
↓
Records result
```

This is reliable and sufficient.

---

# 45. Open links correctly

External material should open:

```text
new tab
```

using:

```ts
target="_blank"
rel="noopener noreferrer"
```

So Northstar stays open while I study.

---

# 46. Return-from-resource workflow

When I return to the Northstar tab, keep the active task open.

Show:

```text
Did you finish this task?

[Complete]
[Need more time]
[Skip]
```

Then capture performance.

---

# 47. Add quick resource actions

Task overflow menu:

```text
Open material
Change material
Save for later
Add note
Add error
Reschedule
Mark unavailable
```

If I mark material unavailable:

Northstar should choose the next enabled fallback.

---

# 48. Show why a resource was selected

Provide subtle explanatory text:

```text
Why this?

Selected because you are learning Averages for the first time and Rodha is your preferred QA concept source.
```

or:

```text
Selected because your Percentages accuracy is already 87%; CAT-level PYQs are now more valuable than additional concept videos.
```

This makes the adaptive planner understandable.

---

# 49. Material completion should inform planning

Separate:

```text
Topic progress
```

from:

```text
Resource completion
```

Watching a concept lesson does NOT make the topic "Strong".

Example:

```text
Rodha lesson complete
2IIM practice 62%
```

Topic remains:

```text
PRACTISING
```

Only performance should drive mastery.

---

# 50. Analytics

Add:

### Resource effectiveness

Example:

```text
Provider         Tasks      Accuracy after use

Rodha             18             78%
2IIM              32             81%
CAT PYQ           15             69%
IMS               12             74%
```

Don't over-interpret correlation.

Just provide useful tracking.

---

# 51. Data migration

The app already has data.

Write proper migrations.

Do not delete:

* tasks
* mock data
* profile
* deadlines
* study history

Existing tasks without resources should receive reasonable resource assignments where possible.

---

# 52. Testing

Test at minimum:

1. Today plan displays attached resources.
2. Resource URL opens.
3. Subscription-disabled resource is never assigned.
4. Enabling IMS makes IMS eligible.
5. Enabling VARC1000 makes it preferred for VARC.
6. Disabling it falls back to 2IIM.
7. Completing practice records accuracy.
8. Accuracy affects later scheduling.
9. Mock day does not also schedule six hours of normal study.
10. Changing study time preserves durations.
11. Actual current date uses Asia/Kolkata.
12. CAT countdown is correct.
13. Missed tasks reschedule intelligently.
14. Broken/missing resource gracefully falls back.
15. Database migration preserves old data.

---

# 53. README

Update README with:

## Study-resource system

Explain:

* enabling subscriptions
* adding a custom resource
* modifying provider links
* resource-to-topic mapping
* planner selection algorithm
* how to update annual resources

---

# 54. Seed files

Keep the resource database maintainable.

Prefer files such as:

```text
/prisma/seed/resources.ts
/prisma/seed/topicResourceMappings.ts

or equivalent for the current stack.
```

Do not create one enormous unmaintainable seed file.

Structure examples:

```text
resources/
  providers.ts
  qa.ts
  dilr.ts
  varc.ts
  gmat.ts
  pyq.ts
```

if this suits the existing architecture.

---

# 55. Most important product outcome

When this work is complete, I want to open Northstar tonight and see something similar to:

---

### 8:00 PM — QUANT

## Percentages

**LEARN · 40m**

Rodha
Arithmetic → Percentages

[OPEN MATERIAL]

**PRACTICE · 70m**

2IIM
Percentages / Profit Loss / SICI

15–20 questions
Target ≥80%

[OPEN PRACTICE]

**REVIEW · 25m**

Log mistakes.

---

### 10:25 PM — DILR

## Set 1 — Grid Puzzle

2IIM Grid Puzzle

[OPEN SET BANK]

25–30 min

## Set 2 — Sequencing

2IIM Sequencing

[OPEN SET BANK]

25–30 min

Analyse representations afterwards.

---

### 12:20 AM — VARC

## RC Practice

2IIM Reading Comprehension

2 passages

[OPEN RC BANK]

## VA

2IIM Para Summary

3 questions

2IIM Sentence Elimination

2 questions

---

### 2:00 AM — CLOSE THE LOOP

Update:

* Error Log
* Quant Diary
* DILR representation notes
* VARC error pattern
* confidence scores

Northstar schedules revisions automatically.

---

# 56. Implementation instruction

Please now:

1. Inspect the existing repository.
2. Understand the existing models and planner implementation.
3. Fix the current-date/timezone bug first.
4. Add the resource data model.
5. Add provider/subscription settings.
6. Seed the real resource catalogue above.
7. Add full QA topic-resource mappings.
8. Add DILR category-resource mappings.
9. Add VARC mappings.
10. Add CAT PYQ library.
11. Add official GMAT resources.
12. Connect resources to the planner.
13. Upgrade Today task cards.
14. Add focused Start Plan mode if not already present.
15. Add completion/performance capture.
16. Connect results back to adaptive scheduling.
17. Upgrade Resources pages.
18. Add resource coverage validation.
19. Run database migrations.
20. Run tests.
21. Run lint/type checks.
22. Build the application.
23. Fix all errors.
24. Preserve existing functionality.
25. Update README.

Do not stop after adding a few links.

I want the application's actual daily planner to allocate these materials automatically.

If the existing architecture differs from the examples above, adapt the implementation cleanly rather than forcing an unnecessary rewrite.

At the end, report:

* files changed
* database changes
* resource mappings implemented
* planner changes
* any resources that could not safely be deep-linked
* exact commands to run the updated application

The success criterion is simple:

**I should no longer have to look at a Northstar task and wonder, "Where exactly am I supposed to study this from?"**
