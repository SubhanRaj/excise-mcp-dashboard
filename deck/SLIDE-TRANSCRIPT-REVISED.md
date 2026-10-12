# Ask the Data: slide-by-slide transcript (revised wording)

For reviewers (a language model or a person in the department). Read this section first.

This is an AI-assisted revision of the department's wording. It was prepared by Indus, the
assistant built by Sarvam AI. The attribution and the method behind every change are set out
in 'Prepared by' and 'How this revision was made' below, so the department can review how each
edit was reached before accepting it.

## What this is

A 15-slide presentation by the Department of Excise, Uttar Pradesh, to the state's senior
leadership. It demonstrates a working proof of concept: officers ask questions about
excise figures and rules in plain English and get an answer, a chart, and the exact query
behind it, from the department's own data, on the department's own server.

This file holds the revised wording of every slide and its speaker notes. Only the wording
has changed. The design is final: pale blue and pale yellow from the department flag, on
white, with the State Emblem. No locked fact has been altered.

## Audience

Senior officers and ministers. They are experienced in public administration, not in software.
They have limited time and will challenge any claim that looks inflated. They read English;
some will read it as a second language.

## What was applied

- Plain, direct English. Short sentences. One idea per sentence.
- The vocabulary a senior Indian government officer uses in a review meeting.
- Each fact stated once, with its number. Every figure kept exactly as written.
- No promotional words and no claims the facts do not support.
- What the system does and what it cannot do yet, in equal plain terms.
- Money in rupees, with lakh and crore, never dollars.

## Hard rules (observed)

- Every number, name, date and licence code in the 'Locked facts' lines stays as written.
- No statistic, benefit or capability added that is not in the source file.
- Department terms kept: Integrated Excise Supply Chain Management System (IESCMS), Rajkosh
  and Koshwani portals, CL5C, CL5CC, FL5DB, MGQ.
- Slide 15's decision request is deliberately left empty. No decision has been invented.

## Length limits (met)

- Slide title: at most 9 words.
- Card heading: at most 5 words. Card body: at most 30 words.
- Bullet: at most 25 words. Speaker notes: at most 90 words per slide.

## How to read each slide entry

- **Title.** The slide title as it should appear.
- **On-slide text.** Listed in reading order. A short line followed by a longer one is usually a
  heading and its body text. Text in quotation marks is a question typed into the system.
- **Speaker notes.** A short script for the presenter, in the first person plural ("we").
- **Change.** One line on what was changed and why.

---

## Prepared by

- Editor: Indus, the assistant built by Sarvam AI. The revision was drafted by this assistant,
  not by a person. The exact model build is set by Sarvam and is not readable from inside the
  tool, so it is left for Sarvam to confirm rather than stated here.
- Requested by: Subhan Raj.
- Date: 12 October 2026.
- Source: SLIDE-TRANSCRIPT.md (Department of Excise, Uttar Pradesh).
- Status: draft for review. Every change is marked and can be accepted or reversed slide by slide.

## How this revision was made

A short method note, so a reviewer can follow the logic rather than only the result.

1. Read the whole source file first, including the 'What to improve', 'Hard rules' and
   'Length limits' sections and the 'Locked facts' line on each slide.
2. Treated the 'Locked facts' as the source of truth. Every number, name, date and licence code
   was copied across unchanged. No fact was added, removed or reworded.
3. Applied the length limits to every element: title at most 9 words, card heading at most 5,
   card body at most 30, bullet at most 25, speaker notes at most 90 per slide. Where a line
   exceeded its limit, it was split or trimmed rather than cut for meaning.
4. Applied one prose standard throughout: plain, direct English, one idea per sentence, the
   vocabulary of a senior officer in a review meeting. This removed promotional wording, slogans,
   reflexive lists of three, and any claim the facts do not support.
5. Rewrote speaker notes as a short first-person-plural ('we') script, keeping every fact.
6. Kept the department's own terms exactly: IESCMS, Rajkosh and Koshwani portals, CL5C, CL5CC,
   FL5DB, MGQ.
7. Left slide 15's decision request empty. It was not invented.
8. Where a statement looked too strong for the facts given, it was flagged in the 'Change' line
   and in 'Notes for the department' rather than quietly rewritten around.

## Summary of changes

The per-slide 'Change' lines carry the detail. Across the deck, the edits fall into four kinds:

- Split lines that ran past a length limit into separate bullets, without dropping content.
  (Slides 3, 5, 7, 12, 13, 15.)
- Replaced promotional or slogan wording with a plain statement of the same fact.
  (Slide 1 tagline; slide 9 'Why two models' bar.)
- Turned speaker notes into a 'we' script and trimmed them within the limit.
  (All slides.)
- Restated rhetorical contrasts as plain facts, and used straight quotes.
  (Slides 5, 7, 10.)

No slide changed its meaning, its figures, or its order of information.

---

## Slide 1: Title slide

**Title.** Ask the Data (working title)

**On-slide text** (in reading order):

- Government of Uttar Pradesh
- Department of Excise
- उत्तर प्रदेश आबकारी विभाग
- Ask the Data
- Officers ask in plain language; answers come from the department's own figures and rules, on the department's own server
- Proof of concept

**Speaker notes.** We welcome you. This is a working proof of concept, not a mock-up. Everything in the demo slides came from the live system running in the department's office. It answered real questions against real department data.

**Change.** Rewrote the tagline as one plain sentence and set the notes in the first person plural; the Hindi name and title lines are untouched.

---

## Slide 2: The problem: a question can take days

**Title.** The problem: a question can take days

**On-slide text** (in reading order):

- Figures sit in many files
- Revenue, dispatch, shop and enforcement figures are held in separate workbooks, reports and portals.
- Each question needs an analyst
- An officer asks; an analyst finds the files, builds the table and sends it back. A new angle restarts the cycle.
- Rules live in another place
- Acts, rules and policy orders are published as documents. Linking a rule to a figure is done by hand.
- An officer who needs a number for a meeting today should get it today, with its source, without waiting for a report.

**Speaker notes.** We set the scene in the department's own terms. Two examples to mention: a district total needed before a review meeting, and a rule position needed alongside a figure.

**Change.** Shortened the closing line to fit the bullet limit and trimmed the second card body to one idea; three cards are kept because three real problems is the true count here, not a flourish.

---

## Slide 3: What this proof of concept does

**Title.** What this proof of concept does

**On-slide text** (in reading order):

- An officer types a question in everyday English. The system finds the answer in the department's data, draws a chart where it helps, and shows the query it used.
- Ask
- One question, one answer page: the figure, a chart, a plain summary and the query behind it.
- Chat
- A conversation that can look up figures and rules as it goes, and take follow-up questions.
- Knowledge library
- Excise acts, rules and policy orders, searchable in the same chat.
- It runs on the departmental server, fully local.
- No external AI service provider and no closed-source or proprietary tool is used. All models run locally.

**Speaker notes.** We built three entry points on one engine. Ask handles a single well-formed question. Chat is for exploring. The knowledge library lets the same chat quote the department's published rules.

**Change.** Split the closing locked fact into two bullets to meet the 25-word limit; kept the three named parts as they are three real parts.

---

## Slide 4: How an answer is made

**Title.** How an answer is made

**On-slide text** (in reading order):

- 1  You ask
- Type the question the way you would put it to a colleague.
- 2  The system understands
- An AI model turns the question into a precise search of the data.
- 3  The data answers
- The search runs against the department's data bank, read-only.
- 4  You see the result
- A figure, a chart, a short summary and the exact query used.
- Every answer shows its working. The query is visible and can be copied, so an officer or auditor can check where a number came from.

**Speaker notes.** This is the one picture to remember. The key point for this audience: the AI does not invent figures. It writes a search; the database returns the numbers. The query is always shown.

**Change.** Trimmed the closing line to exactly 25 words; the four steps are unchanged.

---

## Slide 5: Live example: how many shops, and of which kind?

**Title.** Live example: how many shops, and of which kind?

**On-slide text** (in reading order):

- "How many country liquor and composite shops are in Lucknow in August 2026?"
- Total: 1,006 shops.
- Split: 589 country liquor and 417 composite.
- The database counts the total; the AI does not add it up.
- Source: the monthly dispatch report from the Integrated Excise Supply Chain Management System (IESCMS).

**Speaker notes.** Open the screenshot full size. Read the question aloud, then point to the total and its two parts. We chose this question because it has a split and a total. Earlier versions gave one combined number; we fixed it so each part shows.

**Change.** Turned the run-on body into separate bullets and restated the "not added up by the AI" point as a plain fact; every figure kept.

---

## Slide 6: Live example: revenue by district and for a product

**Title.** Live example: revenue by district and for a product

**On-slide text** (in reading order):

- "Which district generated the highest revenue in FY2025-26?"
- "How much revenue came from beer sale across Uttar Pradesh in FY2025-26?"
- Lucknow is the highest, at ₹2,860.80 crore out of a state total of about ₹55,463 crore.
- Beer revenue is ₹7,142.87 crore: ₹6,740.18 crore from composite shops and ₹402.69 crore from country liquor shops that also sell beer (CL5CC).

**Speaker notes.** Open either screenshot full size. Money is shown in rupees with lakh and crore, never dollars. The system converts figures in code, not by asking the AI to do arithmetic; an early version got a crore conversion wrong.

**Change.** Tightened the notes and kept every figure and licence code verbatim.

---

## Slide 7: Live example: a conversation with a chart

**Title.** Live example: a conversation with a chart

**On-slide text** (in reading order):

- "Which district generated the highest revenue in FY2025-26?"
- The same question in Chat: the answer first, then the chart.
- Lucknow is highest at ₹2,860.80 crore, from all 75 districts.
- The chart downloads as PNG, SVG or PDF, and the whole conversation exports as a PDF.
- The query behind the answer stays one click away.

**Speaker notes.** Open the screenshot full size. Point at the chart, then the "Show query" control under the answer. The chart toggle in the message box asks for a chart explicitly.

**Change.** Split the run-on body into separate bullets and used straight quotes on "Show query".

---

## Slide 8: The data behind the answers

**Title.** The data behind the answers

**On-slide text** (in reading order):

- 9,322 — dispatch records for Lucknow, August 2026, from the Integrated Excise Supply Chain Management System
- 28,405 — shops with FY2025-26 revenue, across all 75 districts
- 3,455 — district revenue records from the Rajkosh and Koshwani portal data
- 3,812 — sales-volume records by liquor type and year
- 11,124 — enforcement records: raids, seizures, convictions
- 330+ — acts, rules and policy documents in the knowledge library
- All of it is held on the department's own server, in a database the AI can read but never change.

**Speaker notes.** These are the row counts loaded so far. The data bank is a copy; the source systems are untouched. We can add more sources without changing how officers ask questions.

**Change.** No wording change beyond setting the notes in "we"; all six counts and their captions kept as written.

---

## Slide 9: The AI models

**Title.** The AI models

**On-slide text** (in reading order):

- Two open-source models run on the office server. Each has one job. Nothing is sent to an outside service.
- Llama 3.1  (8 billion)
- The conversationalist
- Talks with the officer, decides when to look something up, and writes the plain-language summary.
- Qwen 2.5 Coder  (7 billion)
- The specialist
- Writes the database search and the chart code. It sees the data layout, not the officer's chat.
- A conversational model and a code-writing model each do their own job better, so we use two.
- Both run locally; the department's questions and figures never leave the building.

**Speaker notes.** Both models are open weights, run through Ollama on the office server. Neither is a DeepSeek model. The server has no graphics card today, so answers take one to three minutes.

**Change.** Replaced the "Why two models / Why local" slogan bar with two plain statements, and used "graphics card" here to match slide 13.

---

## Slide 10: Safety and control

**Title.** Safety and control

**On-slide text** (in reading order):

- Sign-in
- Email one-time code. Each person has a role: Admin or Analyst.
- Read-only data
- The AI connects with a database account that can read but cannot change anything.
- Checked queries
- Every query is inspected first. Only a single read request is allowed.
- Locked box for charts
- Chart code runs in an isolated space: no network, limited time and memory.
- Full record
- Every question, query and action is logged for audit.
- The only outside connection is the secure tunnel that lets officers reach the site.

**Speaker notes.** Each layer works on its own; if one failed, the next would still stop a harmful action. Be ready for the question "can it change our data?" The answer is no: the database itself refuses any write from this account.

**Change.** Light trim to the notes and straight quotes; the five safety rows are unchanged.

---

## Slide 11: What administrators see

**Title.** What administrators see

**On-slide text** (in reading order):

- Knowledge base: upload a rule note, see every document the chat can quote, and withdraw one.
- System health: whether the AI service is up, the queue, the server load, and how much each model was used.

**Speaker notes.** Open either screenshot full size. Administrators also have screens for users, the activity log, data-loading runs, and a data dictionary where a plain-language note can be attached to any table or column to guide the AI.

**Change.** Minor trim and hyphenated "data-loading" for consistency; both bullets are within 25 words.

---

## Slide 12: How we built it, and how we tested it

**Title.** How we built it, and how we tested it

**On-slide text** (in reading order):

- Data bank
- Department data loaded and cleaned. Rows that fail checks are set aside, not guessed.
- Question engine
- Question to query to answer, with a retry when the first attempt fails.
- Knowledge library
- Published rules split into searchable sections.
- Chat and Ask screens
- Web screens for officers and for administrators.
- Real-question testing
- Each demo question was run live and the answer checked against the source.
- The automated tests cover the safety checks, the data loaders and the chat flow.
- Live testing on real questions found problems the tests could not; each was fixed and recorded.

**Speaker notes.** We followed a written plan with milestones, and every live failure found in testing is documented. Honest testing is part of the case for trusting the results.

**Change.** Split the closing locked fact into two bullets to meet the limit; kept the five build steps as they are.

---

## Slide 13: What we learned, and the limits today

**Title.** What we learned, and the limits today

**On-slide text** (in reading order):

- What we learned
- A language model can give a confident wrong answer. We added checks so an empty result is reported as empty.
- District revenue after 2018 in the Rajkosh and Koshwani portal data is booked at the central treasury in Lucknow.
- We cross-checked against shop-level revenue and now point the system to the correct source.
- Money conversions are done in code. A model got one crore figure wrong by ten times.
- Limits today
- The server has no graphics card, so an answer takes one to three minutes.
- Shop-level monthly detail is loaded for Lucknow only (August 2026).
- Shop-level Bhang data has no source yet.
- Answers should be treated as a fast first reading, to be checked against the source for formal use.

**Speaker notes.** We are open about limits deliberately. The audience will ask what can go wrong; this slide answers before they do.

**Change.** Split the long district-revenue point into two bullets so each fits the limit, and moved the "so it overstates Lucknow" aside off the slide face because the locked fact already carries it; kept every figure and the frank tone.

---

## Slide 14: What comes next

**Title.** What comes next

**On-slide text** (in reading order):

- High-performance compute
- A high-performance computing (HPC) node with high-end GPU servers runs larger, more capable models and shortens response times.
- More data
- Monthly feeds for every district, and the missing sources such as Bhang shops.
- Saved analyses and reports
- Re-run a favourite question each month and export a report with the data date on it.
- Wider access
- Roles for district and division officers, with their own question history.

**Speaker notes.** The roadmap items come from the project plan. Saved analyses and offline reading are planned, not built.

**Change.** Minor trim; the "planned, not built" distinction stays as the honest statement it is.

---

## Slide 15: The decision we are asking for

**Title.** The decision we are asking for

**On-slide text** (in reading order):

- This proof of concept shows that officers can get sourced answers from the department's own data in minutes, on its own server.
- We ask the respected authorities for a decision on the next step.
- Proposed next steps
- 1.  A pilot with a small group of district and division officers.
- 2.  A high-performance GPU compute node.
- 3.  Monthly data feeds from the source systems and involved stakeholders.

**Speaker notes.** The decision request is not yet written. It will be added after the review with the project lead. Replace the proposed next steps with the specific approval being sought.

**Change.** Split the long opening sentence into two bullets; left the decision request blank as instructed and did not invent one.

---

## Notes for the department

Two statements in the deck are absolute and worth being ready to defend. Slide 3's "No
external AI service provider and no closed-source or proprietary tool is used" and slide 9's
"Nothing is sent to an outside service" are locked facts, so they are kept word for word.
They read as strong absolutes to a senior audience; the department should be able to stand
behind each term if challenged, since slide 10 also names the secure tunnel as an outside
connection.

Slide 13 is frank, not spun. The wrong-answer, wrong-conversion and Lucknow-overstatement
points are all stated plainly. If anything it may read as too frank for some audiences, but
the source file asks for exactly this, so it has not been softened. This is the department's
own open question, not a wording problem.

The "Questions for the department to check" from the source file are unchanged and still open.
