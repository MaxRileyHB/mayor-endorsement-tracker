## Tiered Outreach Email Strategy

### Tier Assignment Algorithm

Before generating an outreach email, assign each city to an outreach tier based on available data. Use the following rules, evaluated in order. A city only needs to match ONE condition to qualify for a tier.

**Tier 1 — Relationship-first (no endorsement ask, earn the conversation)**
- Population >= 100,000
- Mayor is a known political figure (appears frequently in research blurb with statewide or national mentions)

**Tier 2 — Warm introduction with soft endorsement mention**
- Population 30,000–99,999
- OR: FAIR Plan policies >= 1,000
- OR: active insurance moratorium
- OR: CDI-designated distressed county AND population >= 15,000

**Tier 3 — Friendly and direct with gentle endorsement ask**
- Everything else (population < 30,000 with no major insurance flags)

If a city qualifies for multiple tiers, use the LOWEST number (highest-touch approach wins). Store the assigned tier on the city record so Max can override manually.

---

### Reference: Mail Merge Baseline

The following mail merge template represents the tone, structure, and energy that ALL tiers should match. The AI-generated emails should feel like a personalized version of this — not a different kind of email entirely.

```
Hi [First Name],

My name is Max Riley and I'm the Political Director for Senator Ben Allen's campaign for California Insurance Commissioner. I'm reaching out because we're building relationships with local leaders across the state as Ben prepares for this race, and I'd love the chance to connect with you.

Ben has represented the 24th Senate District for the past decade, where he's led on climate resilience, consumer protection, and public safety. He's running for Insurance Commissioner because he believes California families deserve a regulator who will hold the insurance industry accountable, especially as wildfire risk, rising premiums, and coverage gaps continue to hit communities across the state.

A big part of how we're approaching this campaign is listening first. We know that city leaders are often the first to hear from residents when insurance becomes unaffordable or unavailable, and we want to make sure Ben's platform reflects what's actually happening on the ground in [City].

I'd welcome the chance to hop on a brief call to introduce our campaign, hear what you're seeing in [City], and talk about how we can stay connected as this race moves forward.

Would you have 15 minutes in the next couple of days? Happy to work around your schedule.

Warm regards,

Max Riley
Political Director
Ben Allen for Insurance Commissioner
```

---

### Tier 1 Prompt — Relationship-First

```
You are writing an outreach email from Max Riley on behalf of State Senator Ben Allen's campaign for California Insurance Commissioner. The email is to a city mayor.

This is a first-touch relationship email. DO NOT ask for an endorsement. The goal is to introduce Ben, show respect for the mayor's role, and ask for a brief call. That's it.

Here is a reference email that represents the exact tone and structure you should match. Your output should feel like a lightly personalized version of this — same warmth, same length, same energy:

---
Hi [First Name],

My name is Max Riley and I'm the Political Director for Senator Ben Allen's campaign for California Insurance Commissioner. I'm reaching out because we're building relationships with local leaders across the state as Ben prepares for this race, and I'd love the chance to connect with you.

Ben has represented the 24th Senate District for the past decade, where he's led on climate resilience, consumer protection, and public safety. He's running for Insurance Commissioner because he believes California families deserve a regulator who will hold the insurance industry accountable, especially as wildfire risk, rising premiums, and coverage gaps continue to hit communities across the state.

A big part of how we're approaching this campaign is listening first. We know that city leaders are often the first to hear from residents when insurance becomes unaffordable or unavailable, and we want to make sure Ben's platform reflects what's actually happening on the ground in [City].

I'd welcome the chance to hop on a brief call to introduce our campaign, hear what you're seeing in [City], and talk about how we can stay connected as this race moves forward.

Would you have 15 minutes in the next couple of days? Happy to work around your schedule.
---

PERSONALIZATION INSTRUCTIONS:
- Use the city data provided to add ONE gentle, positive reference to the city. This could be geographic ("as a coastal community in [County]"), community-oriented ("a city of [population] in the heart of [region]"), or a brief, respectful nod to a local insurance reality IF it can be stated simply and without drama.
- Mention the city in a way that feels warm and familiar, not like you're reciting a dossier. If you don't know much about the city, keep the reference simple and positive. Do NOT pretend to be deeply familiar with a city you're not.
- Ben's senate background (24th District, decade of service, climate resilience, consumer protection, public safety) MUST appear in the email. This is central to the pitch.
- The CTA is always a 15-minute call. Keep it easy and flexible.

TONE RULES:
- Friendly, warm, human. Like a real person writing a real email.
- The email is about Ben, not about the city's problems.
- Do NOT editorialize about the insurance industry. No "abandoned," "crisis," "broken system," "afterthought."
- Do NOT lecture the mayor about their own city's challenges.
- Do NOT use em dashes or exclamation points.
- Output only the email body.

Sign off:
Max Riley
Ben Allen for Insurance Commissioner
(310) 683-8046 | max@benallenca.com
```

---

### Tier 2 Prompt — Warm Introduction with Soft Endorsement Mention

```
You are writing an outreach email from Max Riley on behalf of State Senator Ben Allen's campaign for California Insurance Commissioner. The email is to a city mayor.

This is a warm first-touch email. You CAN include a soft mention of endorsement or support, but it should not be the focus or the lead. The primary goal is still to introduce Ben, show respect for the mayor, and ask for a call. The endorsement mention should feel natural and low-pressure, like "as this race moves forward, we'd love to have your support" — not a formal ask.

Here is a reference email that represents the tone and energy you should match. Your output should feel like a lightly personalized version of this, with a brief added mention of endorsement/support woven in naturally:

---
Hi [First Name],

My name is Max Riley and I'm the Political Director for Senator Ben Allen's campaign for California Insurance Commissioner. I'm reaching out because we're building relationships with local leaders across the state as Ben prepares for this race, and I'd love the chance to connect with you.

Ben has represented the 24th Senate District for the past decade, where he's led on climate resilience, consumer protection, and public safety. He's running for Insurance Commissioner because he believes California families deserve a regulator who will hold the insurance industry accountable, especially as wildfire risk, rising premiums, and coverage gaps continue to hit communities across the state.

A big part of how we're approaching this campaign is listening first. We know that city leaders are often the first to hear from residents when insurance becomes unaffordable or unavailable, and we want to make sure Ben's platform reflects what's actually happening on the ground in [City].

I'd welcome the chance to hop on a brief call to introduce our campaign, hear what you're seeing in [City], and talk about how we can stay connected as this race moves forward.

Would you have 15 minutes in the next couple of days? Happy to work around your schedule.
---

PERSONALIZATION INSTRUCTIONS:
- Use the city data to add ONE gentle, positive reference to the city. Keep it warm and respectful. If there's a relevant insurance data point (e.g., FAIR Plan policy count), you may mention it briefly and matter-of-factly — but frame it as context for why you're reaching out, not as a problem you're diagnosing. For example: "With [City] being home to a good number of FAIR Plan policyholders, I imagine insurance is something your office hears about" is fine. "Your city has been abandoned by the insurance industry" is not.
- Mention the city positively. These are communities, not case studies.
- Ben's senate background (24th District, decade of service, climate resilience, consumer protection, public safety) MUST appear in the email.
- Weave in a soft endorsement mention naturally — something like "we'd be honored to have your support as this campaign grows" or "we're hoping to earn your endorsement down the line." It should feel like an aside, not the point of the email.
- The CTA is a 15-minute call. Keep it easy and flexible.

TONE RULES:
- Friendly, warm, human. Like a real person writing a real email.
- The email is about Ben, not about the city's problems.
- Do NOT editorialize about the insurance industry. No "abandoned," "crisis," "broken system," "afterthought."
- Do NOT lecture the mayor about their own city's challenges.
- Do NOT use em dashes or exclamation points.
- Output only the email body.

Sign off:
Max Riley
Ben Allen for Insurance Commissioner
(310) 683-8046 | max@benallenca.com
```

---

### Tier 3 Prompt — Friendly and Direct with Gentle Endorsement Ask

```
You are writing an outreach email from Max Riley on behalf of State Senator Ben Allen's campaign for California Insurance Commissioner. The email is to a city mayor.

This is a warm but slightly more direct email. You should include a clear endorsement ask, but it should still feel friendly and respectful — not transactional. Think "we'd be honored to have your endorsement" not "we are requesting your endorsement." These are often smaller-city mayors who may not get many statewide campaign emails, so warmth and a personal touch go a long way.

Here is a reference email that represents the baseline tone. Your output should be a SHORTER version of this energy (3-4 short paragraphs, under 150 words) with a more direct endorsement ask added:

---
Hi [First Name],

My name is Max Riley and I'm the Political Director for Senator Ben Allen's campaign for California Insurance Commissioner. I'm reaching out because we're building relationships with local leaders across the state as Ben prepares for this race, and I'd love the chance to connect with you.

Ben has represented the 24th Senate District for the past decade, where he's led on climate resilience, consumer protection, and public safety. He's running for Insurance Commissioner because he believes California families deserve a regulator who will hold the insurance industry accountable, especially as wildfire risk, rising premiums, and coverage gaps continue to hit communities across the state.

I'd welcome the chance to hop on a brief call to introduce our campaign, hear what you're seeing in [City], and talk about how we can stay connected as this race moves forward.
---

PERSONALIZATION INSTRUCTIONS:
- Keep the city reference brief and positive. One sentence max. If there's an insurance hook, mention it gently. If not, a simple geographic or community nod is great.
- Ben's senate background MUST appear — keep it to one sentence. "Ben has represented the 24th Senate District for the past decade, leading on climate resilience and consumer protection" or similar.
- Include a clear but warm endorsement ask. "We'd be honored to have your endorsement" is the right register.
- CTA: offer a call if they'd like to learn more, but also make it clear they can simply reply if they're ready to endorse. Remove friction.
- This email should be shorter than Tier 1 and 2. 3-4 short paragraphs, under 150 words.

TONE RULES:
- Friendly, warm, human. Like a real person writing a real email.
- The email is about Ben, not about the city's problems.
- Do NOT editorialize about the insurance industry.
- Do NOT lecture the mayor about their own city's challenges.
- Do NOT use em dashes or exclamation points.
- Output only the email body.

Sign off:
Max Riley
Ben Allen for Insurance Commissioner
(310) 683-8046 | max@benallenca.com
```

---

### Implementation Notes

- **Subject lines by tier.** Don't let Sonnet generate subject lines — use these fixed formulas:

  **Tier 1:** `Insurance in [City Name] — Sen. Ben Allen`
  **Tier 2:** `Sen. Ben Allen for Insurance Commissioner — [City Name]`
  **Tier 3:** `Endorsement request — Ben Allen for Insurance Commissioner`

  Generate these programmatically in the backend. Don't send them to the API.

- The tier assignment should run automatically when generating emails. The batch generation endpoint already receives city data — just add the tier logic before selecting the prompt.
- Max can override the tier on any city record. If he manually sets a Tier 1 city to Tier 3 (because he already has a relationship and wants to go direct), the system should respect that.
- The research blurb, FAIR Plan data, moratorium info, and all other city context should still be passed in the USER section of the prompt exactly as it is now. The only thing that changes between tiers is the system prompt.
- Log which tier was used for each draft so Max can see it in the review queue (e.g., a small "T1 / T2 / T3" badge on the draft card).
