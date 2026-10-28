# Privacy

For anyone who saves things in Moira and wants to know what happens to them.

## What is stored

Your words (with passwords, card numbers, codes and keys masked out), text read from your links, screenshots, voice notes and videos, and what Moira works out from them (titles, summaries, collections). **Images, audio, video and files are not stored.** They are deleted as soon as they are read. Location data inside photos (EXIF) is removed before a photo is sent anywhere.

## What is sent to Meta

The text, images, audio and short videos needed to read, file and answer, through the Meta Model API in **Standard mode**, where content is not used to train Meta's models. Every request asks Meta not to keep it (`store: false`). A short video is uploaded with a one-hour expiry and deleted as soon as it is read. Contributor mode (which allows training) is only used for made-up demo and test data.

## What is sent elsewhere

When you save a link, Moira contacts that site (or the YouTube or GitHub API) to read it. Nothing else.

## Logs

Logs hold ids, counts, timings and costs. Never your content.

## Your control

- Export everything: JSONL, Markdown and your SQLite file.
- Forget one item (you can undo for 10 minutes).
- Forget everything (24-hour grace period).

## How long things are kept

Backups are kept 14 days (daily) and 8 weeks (weekly); forgotten data ages out of them. Sample-memory sandboxes for visitors and judges are deleted after 24 hours.

## Testers

Moira is a hackathon prototype. When you join with a tester code, the bot shows a short note about what is stored and how to forget everything.
