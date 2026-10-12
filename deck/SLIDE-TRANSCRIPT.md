# Ask the Data: slide-by-slide transcript

For reviewers (a language model or a person in the department). Read this section first.

## What this is

A 15-slide presentation by the Department of Excise, Uttar Pradesh, to the state's senior
leadership. It demonstrates a working proof of concept: officers ask questions about
excise figures and rules in plain English and get an answer, a chart, and the exact query
behind it, from the department's own data, on the department's own server.

This file holds the words of every slide, the speaker notes, a description of every picture,
and the facts behind each claim. The design is final: pale blue and pale yellow from the department flag, on white, with the State Emblem. Only the wording is open to improvement.

A shorter 8-slide version of the deck exists for a limited slot. It uses slides 1, 2, 3, 5, 6,
10, 14 and 15 of this file unchanged, so a wording change to one of those slides applies to
both decks.

## Audience

Senior officers and ministers. They are experienced in public administration, not in software.
They have limited time and will challenge any claim that looks inflated. They read English;
some will read it as a second language.

## What to improve

- Plain, direct English. Short sentences. One idea per sentence.
- The vocabulary a senior Indian government officer uses in a review meeting.
- State each fact once, with its number. Keep every figure exactly as written.
- No promotional words ("powerful", "seamless", "revolutionary") and no claims the facts
  below do not support.
- Say what the system does and what it cannot do yet, in equal plain terms.
- Money in rupees, with lakh and crore, never dollars. Write ₹2,860.80 crore, not 28.6 billion.

## How to read each slide entry

- On-slide text is listed in reading order. A short line followed by a longer one is usually a
  heading and its body text. Text in quotation marks is a question typed into the system.
- Speaker notes are guidance to the presenter, not a finished script. You may rewrite them as
  a short script in the first person plural ("we"), keeping every fact.
- 'Screenshot alt text' describes a picture so you can see it. It is not text to rewrite.
- 'Locked facts' are the source of truth for the claims on that slide.

## Hard rules (do not change)

- Every number, name, date and licence code in the 'Locked facts' lines stays as written.
- Do not add a statistic, a benefit, or a capability that is not in this file.
- Keep the department's own terms: Integrated Excise Supply Chain Management System (IESCMS), Rajkosh and Koshwani portals, CL5C, CL5CC, FL5DB, MGQ.
- Slide 15's decision request is deliberately empty. Do not invent one.

## Length limits

Slide title: at most 9 words. A card heading: at most 5 words. A card body: at most 30 words.
A bullet: at most 25 words. Speaker notes: at most 90 words per slide.

## Terms used in this deck

- IESCMS: the Integrated Excise Supply Chain Management System, the department's live system
  for excise licences and transport passes.
- Rajkosh and Koshwani portal data: the department's district-level records of revenue, sales
  volume, enforcement, shops, brands, prices and policy.
- Country liquor (CL5C), country liquor with beer (CL5CC): retail shop types.
- Composite shop (FL5DB): a foreign liquor and beer retail licence.
- MGQ: minimum guaranteed quantity.
- BL: bulk litres. Crore: 10 million. Lakh: 100 thousand.
- Ask: the one-question-one-answer page. Chat: the conversation page.
- Knowledge library: the acts, rules and policy orders the chat can read and quote.

## Known weak spots in the current wording

- Slides 2 and 3 lean on lists of three. Vary where a different number is true.
- Slide 13 is the most important slide for trust. Keep it frank, without apology or spin.

## What to send back

The same structure for each slide: Title, On-slide text, Speaker notes. Mark every change with a
one-line reason. Do not return design or layout suggestions.

## Prompt to paste with this file

> You are editing the wording of a government presentation, using the attached transcript.
> Follow the 'What to improve', 'Hard rules' and 'Length limits' sections exactly. For each
> slide, return the improved title, on-slide text and speaker notes, then one line saying what
> you changed and why. Do not alter any locked fact. If you think a claim is too strong for the
> facts given, say so instead of rewriting around it.

## Questions for the department to check

1. Are the shop-type definitions (country liquor, CL5CC, composite) worded the way the
   department would say them?
2. Is the Integrated Excise Supply Chain Management System named correctly as the source of the dispatch report?
3. Are the safety statements on slide 10 acceptable as written for a senior-leadership audience?
4. Is slide 13 frank enough, or too frank?
5. What should slide 15 ask for?

## Notes for the department

A wording review by Indus (Sarvam AI's assistant, 12 October 2026) fed the current wording.
Its draft is in the repository history (`SLIDE-TRANSCRIPT-REVISED.md`, commit `e07d86c`).
Two points from it still apply:

- Two statements are absolute and worth being ready to defend: slide 3, "No external AI
  service provider and no closed-source or proprietary tool is used", and slide 9, "Nothing is
  sent to an outside service". Both are locked facts. The interim server is reached through a
  secure tunnel, which the deck does not mention because it goes away with that server.
- Slide 13 states the limits plainly: a wrong answer, a wrong conversion and an overstated
  Lucknow figure. It has not been softened. Whether that is too frank is the department's
  decision (question 4).

---


## Slide 1: Title slide

**Purpose.** Open the talk and name the project in one line.

**On-slide text** (in reading order):

- Government of Uttar Pradesh
- Department of Excise
- उत्तर प्रदेश आबकारी विभाग
- Ask the Data
- Ask a question in plain language. / The answer comes from the department's own figures and rules, on the department's own server.
- Proof of concept

**Speaker notes.** Welcome. This is a working proof of concept, not a mock-up. Everything in the demo slides came from the live system running in the department's office. It answered real questions against real department data.

**Visual.** Title slide split diagonally into pastel yellow (top left) and pastel blue (bottom right), after the department flag. The State Emblem of Uttar Pradesh at top left, with 'Government of Uttar Pradesh', 'Department of Excise' and the Hindi name 'उत्तर प्रदेश आबकारी विभाग' (Unicode text, Nirmala UI font) beside it.

**Screenshot alt text.** None.

**Locked facts.** Project name 'Ask the Data' is a working title and can change.

---

## Slide 2: The problem: a simple question can take days

**Purpose.** Make the audience feel the everyday problem before any technology appears.

**On-slide text** (in reading order):

- Figures sit in many files
- Revenue, dispatch, shop and enforcement figures are held in separate workbooks, reports and portals.
- Each question needs an analyst
- An officer asks, an analyst finds the files, builds the table and sends it back. A new angle starts the cycle again.
- Rules live in another place
- Acts, rules and policy orders are published as documents. Linking a rule to a figure is done by hand.
- An officer who needs a number for a meeting today should get it today, with its source, without waiting for a report.

**Speaker notes.** Set the scene in the department's own terms. Two examples to mention: a district total needed before a review meeting, and a rule position needed alongside a figure.

**Visual.** Three pale blue cards, each with a round blue icon: a spreadsheet, a clock, a shelf of books.

**Screenshot alt text.** None.

**Locked facts.** None. This slide is argument, not data. Examples to use in the talk are in the notes.

---

## Slide 3: What this proof of concept does

**Purpose.** Say in plain words what the system does, and name its three parts.

**On-slide text** (in reading order):

- An officer types a question in everyday English. The system finds the answer in the department's data, draws a chart where it helps, and shows the exact query it used.
- Ask
- One question, one answer page: the figure, a chart, a plain summary and the query behind it.
- Chat
- A conversation that can look up figures and rules as it goes, and take follow-up questions.
- Knowledge library
- Excise acts, rules and policy orders, searchable in the same chat.
- It runs on the departmental server, completely local. / No external AI service provider and no closed-source or proprietary tool is used. All models run locally.

**Speaker notes.** We built three entry points on one engine. Ask takes a single well-formed question. Chat is for exploring. The knowledge library lets the same chat quote the department's published rules.

**Visual.** Three cards with icons: a speech bubble with a question mark (Ask), a chat bubble (Chat), a bookshelf (Knowledge library).

**Screenshot alt text.** None.

**Locked facts.** The system runs on the departmental server and is completely local. No external AI service provider and no closed-source or proprietary tool is used; all models run locally.

---

## Slide 4: How an answer is made

**Purpose.** The one picture the audience should remember: how a question becomes an answer.

**On-slide text** (in reading order):

- 1  You ask
- Type the question the way you would put it to a colleague.
- 2  The system understands
- An AI model turns the question into a precise search of the data.
- 3  The data answers
- The search runs against the department's data bank, read-only.
- 4  You see the result
- A figure, a chart, a short summary and the exact query used.
- Every answer shows its working. The query is visible and can be copied, so an officer or an auditor can check where a number came from.

**Speaker notes.** This is the one picture to remember. The key point for this audience: the AI does not invent figures. It writes a search; the database returns the numbers. The query is always displayed.

**Visual.** Four pale blue boxes joined by gold arrows, left to right: 1 You ask (question icon), 2 The system understands (brain icon), 3 The data answers (database icon), 4 You see the result (bar chart icon). A pale yellow bar underneath carries the closing sentence.

**Screenshot alt text.** None.

**Locked facts.** The AI writes a search of the data. The database returns the numbers. The AI does not invent figures. The exact query is shown with every answer and can be copied.

---

## Slide 5: Live example: how many shops, and of which kind?

**Purpose.** Show one real question answered end to end, with a figure the audience can check.

**On-slide text** (in reading order):

- "How many country liquor and composite shops are in Lucknow in August 2026?"
- Total: 1,006 shops. / Split: 589 country liquor and 417 composite. / The database counts the total; the AI does not add it up. / Source: the monthly dispatch report from the Integrated Excise Supply Chain Management System (IESCMS).

**Speaker notes.** Click the screenshot to open it full size. Read the question aloud, then point to the total and the two parts. This question was chosen because it has a split and a total. Earlier versions gave one combined number; we fixed that so each part is shown.

**Visual.** Left: the question and four short points. Right: a screenshot of the Ask page.

**Screenshot alt text.** Screenshot of the Ask page for the question 'How many country liquor and composite shops are in Lucknow in August 2026?'. A bar chart titled 'Number of Country Liquor and Composite Shops in Lucknow in August 2026' (y-axis 'Number of Shops') shows three bars: Composite 417, Country Liquor 589, Total 1,006. Below the chart is a two-sentence summary reading 'There are 589 country liquor shops and 417 composite shops in Lucknow in August 2026. The total number of such shops is 1006, with a combined shop count of 1006 across these categories.' (the second sentence repeats the total; a known wording slip), then a three-row table (Composite 417, Country Liquor 589, Total 1006), a collapsed 'Generated SQL' panel, and a thumbs up / thumbs down feedback row.

**Locked facts.** Lucknow, August 2026: 1,006 shops in total, 589 country liquor and 417 composite. Source: the monthly dispatch report from the Integrated Excise Supply Chain Management System (IESCMS), one row per transport pass, loaded for Lucknow for August 2026 only. 'Composite' means a Foreign Liquor and Beer licence (code FL5DB). Country liquor includes CL5C and CL5CC.

---

## Slide 6: Live example: revenue by district and for a product

**Purpose.** Show two money questions answered, one by district and one for a product.

**On-slide text** (in reading order):

- "Which district generated the highest revenue in FY2025-26?"
- "How much revenue came from beer sale across Uttar Pradesh in FY2025-26?"
- Lucknow is the highest, at ₹2,860.80 crore out of a state total of about ₹55,463 crore.
- Beer revenue is ₹7,142.87 crore: ₹6,740.18 crore from composite shops and ₹402.69 crore from country liquor shops that also sell beer (CL5CC).

**Speaker notes.** Click either screenshot to open it full size. Money is shown in rupees with lakh and crore, never in dollars. The system converts the figures in code, not by asking the AI to do the arithmetic, after an early version got a crore conversion wrong.

**Visual.** Two Ask-page screenshots side by side, each with its question above and a one-sentence reading below.

**Screenshot alt text.** Left screenshot: Ask page for 'Which district generated the highest revenue in FY2025-26?'. A bar chart titled 'Highest Revenue by District in FY2025-26' shows 75 districts, falling steeply from Lucknow on the left; the y-axis reaches 30B rupees. A summary names Lucknow at ₹2,860.80 crore, then Gautam Buddha Nagar at ₹2,622.48 crore and Kanpur Nagar at ₹2,068.48 crore. A 75-row table starts with Lucknow. Right screenshot: Ask page for 'How much revenue was generated from beer sale across Uttar Pradesh in FY 2025-26?'. A bar chart titled 'Revenue from Beer Sale in Uttar Pradesh FY 2025-26' shows three bars: Composite Shop, Country Liquor (CL5CC), Total. A summary and a three-row table follow.

**Locked facts.** FY2025-26: Lucknow is the highest district at ₹2,860.80 crore. The state total of about ₹55,463 crore comes from shop-level revenue for 28,405 shops across all 75 districts. Beer revenue is ₹7,142.87 crore in total: ₹6,740.18 crore from composite shops and ₹402.69 crore from country liquor shops that also sell beer (CL5CC). All amounts are in Indian rupees; crore = 10 million.

---

## Slide 7: Live example: a conversation with a chart

**Purpose.** Show that Chat answers the same kind of question as a conversation, with a chart.

**On-slide text** (in reading order):

- "Which district generated the highest revenue in FY2025-26?"
- The same question in Chat: the answer first, then the chart. / Lucknow is highest at ₹2,860.80 crore, from all 75 districts. / The chart downloads as PNG, SVG or PDF, and the whole conversation exports as a PDF. / The query behind the answer stays one click away.

**Speaker notes.** Click the screenshot to open it full size. Point at the chart, then the "Show query" control under the answer. The chart toggle in the message box asks for a chart explicitly.

**Visual.** Left: the question and four short points. Right: a screenshot of the Chat page.

**Screenshot alt text.** Screenshot of the Chat page. A violet bubble holds the user's question 'Which district generated the highest revenue in FY2025-26?'. The assistant replies 'The district that generated the highest revenue in FY2025-26 was Lucknow, with a total revenue of ₹2,860.80 crore.' A chart card below shows a bar chart titled 'Total Revenue by District in FY 2025-26' with PNG, SVG and PDF download links and a 'Show query' control. The message box at the bottom has a 'Visualize' switch.

**Locked facts.** Same figures as slide 6. Chart download formats: PNG, SVG, PDF. A whole conversation exports as a PDF.

---

## Slide 8: The data behind the answers

**Purpose.** Show how much data is already loaded, so the audience knows this is built on real department data.

**On-slide text** (in reading order):

- 9,322 records
- dispatch records for Lucknow, August 2026, from the Integrated Excise Supply Chain Management System
- 28,405 shops
- shops with FY2025-26 revenue, across all 75 districts
- 3,455 records
- district revenue records from the Rajkosh and Koshwani portal data
- 3,812 records
- sales-volume records by liquor type and year
- 11,124 records
- enforcement records: raids, seizures, convictions
- 330+ documents
- acts, rules and policy documents in the knowledge library
- All of it is held on the department's own server, in a database the AI can read but never change.

**Speaker notes.** These are the row counts loaded so far. The data bank is a copy; the source systems are untouched. We can add more sources without changing how officers ask questions.

**Visual.** Six tiles, each with an icon and a large number, in two rows of three.

**Screenshot alt text.** None.

**Locked facts.** 9,322 dispatch records (Lucknow, August 2026, from the Integrated Excise Supply Chain Management System). 28,405 shops with FY2025-26 revenue across all 75 districts. 3,455 district revenue records, 3,812 sales-volume records by liquor type and year, and 11,124 enforcement records (raids, seizures, convictions), all from the Rajkosh and Koshwani portal data. More than 330 acts, rules and policy documents in the knowledge library. The data bank is a copy; the source systems are untouched.

---

## Slide 9: The AI models

**Purpose.** Name the two models and what each one does, in terms a non-technical person can repeat.

**On-slide text** (in reading order):

- Two open-source models run on the office server. Each has one job. Nothing is sent to an outside service.
- Llama 3.1  (8 billion)
- The conversationalist
- Talks with the officer, decides when to look something up, and writes the plain-language summary.
- Qwen 2.5 Coder  (7 billion)
- The specialist
- Writes the database search and the chart code. It sees the data layout, not the officer's chat.
- A conversational model and a code-writing model each do their own job better, so we use two. / Both run locally: the department's questions and figures never leave the building.

**Speaker notes.** Both models are open weights, run through Ollama on the office server. Neither is a DeepSeek model. The server has no graphics card today, so answers take one to three minutes.

**Visual.** Two large pale blue cards: Llama 3.1 (8 billion) and Qwen 2.5 Coder (7 billion), each with an icon. A pale yellow bar underneath gives the two reasons: two models, and local.

**Screenshot alt text.** None.

**Locked facts.** Llama 3.1 8B talks with the officer and writes the plain-language summary. Qwen 2.5 Coder 7B writes the database search and the chart code. Both are open-source models run on the office server through Ollama. The server has no graphics card, so an answer takes about one to three minutes. No DeepSeek model is used.

---

## Slide 10: Safety and control

**Purpose.** Answer 'can it change our data?' and 'who can see what?' before anyone asks.

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

**Speaker notes.** Each layer works on its own: if one failed, the next would still stop a harmful action. Be ready for the question "can it change our data?" The answer is no: the database itself refuses any write from this account.

**Visual.** Five rows, each with a round icon, a short name and one sentence: Sign-in, Read-only data, Checked queries, Locked box for charts, Full record.

**Screenshot alt text.** None.

**Locked facts.** Sign-in is an emailed one-time code; roles are Admin and Analyst. The AI uses a database account that can read but not change anything; the database itself refuses a write. Every query is inspected and only a single read request passes. Chart code runs in an isolated space with no network and limits on time and memory. Every question, query and action is logged.

---

## Slide 11: What administrators see

**Purpose.** Show that administrators have real controls, not only users.

**On-slide text** (in reading order):

- Knowledge base: upload a rule note, see every document the chat can quote, and withdraw one.
- System health: whether the AI service is up, the queue, the server load, and how much each model was used.

**Speaker notes.** Click either screenshot to open it full size. Administrators also have screens for users, the activity log, data loading runs and a data dictionary where a plain-language note can be attached to any table or column to guide the AI.

**Visual.** Two screenshots side by side with a one-line caption under each.

**Screenshot alt text.** Left screenshot: the Knowledge base admin page, with an 'Upload a document' form (title, Markdown file, Upload button), a 'Pending uploads' table with one row 'UP Excise shop types and license codes', and an 'Ingested corpus' table of policy documents such as 'Excise Policy Uttar Pradesh 2020-21', each marked Active. Right screenshot: the System health page with four tiles (Orchestrator Reachable, Queue 0 pending, Load average, Memory available 12.8 of 30.1 GB), and tables of AI usage for one-shot queries and for chat.

**Locked facts.** Knowledge base: upload a rule note, browse the corpus, withdraw a document. System health: AI service status, queue, server load, per-model usage. Other admin screens, not shown: users, activity log, data-loading runs, data dictionary.

---

## Slide 12: How we built it, and how we tested it

**Purpose.** Tell the audience this was built in steps and tested on real questions, not assembled in a hurry.

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
- The automated tests cover the safety checks, the data loaders and the chat flow. / Live testing on real questions found problems the tests could not. Each one was fixed and recorded.

**Speaker notes.** We followed a written plan with milestones, and every live failure found in testing is documented. Honest testing is part of the case for trusting the results.

**Visual.** Five narrow cards with icons: Data bank, Question engine, Knowledge library, Chat and Ask screens, Real-question testing.

**Screenshot alt text.** None.

**Locked facts.** Automated tests cover the safety checks, the data loaders and the chat flow. Live testing on real questions found problems the tests could not; each was fixed and recorded in the project log.

---

## Slide 13: What we learned, and the limits today

**Purpose.** Be open about what went wrong and what is not yet possible. This slide answers the audience's hardest question first.

**On-slide text** (in reading order):

- What we learned
- A language model can give a confident wrong answer. We added checks so an empty result is reported as empty. / District revenue after 2018 in the Rajkosh and Koshwani portal data is booked at the central treasury in Lucknow. / We cross-checked against shop-level revenue and now point the system to the correct source. / Money conversions are done in code. A model got one crore figure wrong by ten times.
- Limits today
- The server has no graphics card, so an answer takes one to three minutes. / Shop-level monthly detail is loaded for Lucknow only (August 2026). / Shop-level Bhang data has no source yet. / Answers should be treated as a fast first reading, to be checked against the source for formal use.

**Speaker notes.** We are open about limits deliberately. The audience will ask what can go wrong; this slide answers first.

**Visual.** Two pale blue cards: 'What we learned' (blue heading) and 'Limits today' (gold heading).

**Screenshot alt text.** None.

**Locked facts.** A model once gave a confident wrong answer; an empty result is now reported as empty. District revenue after 2018 in the Rajkosh and Koshwani portal data is booked at the central treasury in Lucknow, so it overstates Lucknow; it was cross-checked against shop-level revenue and the system now uses that source. A money conversion done by the model was once wrong by ten times; conversions are now done in code. Limits: no graphics card so answers take one to three minutes; shop-level monthly detail is loaded for Lucknow for August 2026 only; no source yet for shop-level Bhang data; answers are a fast first reading to be checked against the source for formal use.

---

## Slide 14: What comes next

**Purpose.** Show where this goes next.

**On-slide text** (in reading order):

- High-performance compute
- A high-performance computing (HPC) node with high-end GPU servers runs larger, more capable models and shortens response times.
- More data
- Monthly feeds for every district, and the missing sources such as Bhang shops.
- Saved analyses and reports
- Re-run a favourite question each month and export a report with the data date on it.
- Wider access
- Roles for district and division officers, with their own question history.

**Speaker notes.** Roadmap items come from the project plan. Saved analyses and offline reading are planned, not built.

**Visual.** Four cards in a two-by-two grid with icons: High-performance compute, More data, Saved analyses and reports, Wider access.

**Screenshot alt text.** None.

**Locked facts.** High-performance compute means a high-performance computing (HPC) node with high-end GPU servers, which can run larger, more capable models and shorten response times. Saved analyses, reports and wider access by district and division officers are planned, not built.

---

## Slide 15: The decision we are asking for

**Purpose.** State the decision the respected authorities are being asked to make.

**On-slide text** (in reading order):

- This proof of concept shows that officers can get sourced answers from the department's own data in minutes, on the department's own server. / We ask the respected authorities for a decision on the next step.
- Proposed next steps
- 1.  A pilot with a small group of district and division officers. / 2.  A high-performance GPU compute node. / 3.  Monthly data feeds from the source systems and involved stakeholders.

**Speaker notes.** DECISION REQUEST: to be written after the review with the project lead. Replace the next steps above with the specific approval being sought.

**Visual.** A tinted box with a lightbulb icon holds the main sentence; a short numbered list sits below.

**Screenshot alt text.** None.

**Locked facts.** The decision request itself is not yet written. It will be added after the project lead's review. The three next steps on the slide are proposals.

---
