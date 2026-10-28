---
name: demo_gen
version: 1.0.0
model: muse-spark-1.3-contributor
effort: low
schema: DemoGenOutput
changelog:
  - 1.0.0 (2026-10-28): starting point from blueprint §9.8
---
You write realistic sample data for a demo of a personal memory app. The person is fictional: <persona>.
Write the raw things this person would quickly save during <month>, the way they would type them into a chat: short, casual, often lowercase, sometimes just a link, sometimes a voice-note style sentence.
Rules: every person, email, phone number and handle is fictional (emails at example.com, handles ending in .demo). Links use the URL shapes of real sites with made-up ids, or example.com. Mix kinds: links (Instagram reels, YouTube videos, GitHub repos, articles), ideas, to-dos, facts about themself, details about people, songs, places. Write <count> items. Never include passwords, card numbers or real people.
Output only JSON that matches the schema.
