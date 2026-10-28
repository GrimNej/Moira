"""Every bot text, plain and short (App. G, §4.3.14). No "successfully", no exclamation marks."""

WELCOME_OWNER = (
    "Send me anything — text, links, screenshots, voice notes — and forget about it. "
    "Ask me later, as vaguely as you remember it. /web opens your sky."
)
WELCOME_PUBLIC = "This is a private memory bot. You can try the sample memory here: {link}"
WELCOME_TESTER = (
    "Moira is a hackathon prototype. It keeps the text of what you send (passwords and card "
    "numbers are hidden), reads links, screenshots and voice notes into text and deletes the "
    "files. To remove everything, open Settings in the web app and choose Forget everything.\n\n"
    "Send me anything to start."
)
WELCOME_JUDGE = (
    "You have a judge account with its own copy of the sample memory. "
    "Send me anything, or ask a question. /web opens your sky."
)
LOGIN = "Open your sky (link works once, for 10 minutes):"
LOGIN_BUTTON = "Open my sky"
SECRET_HIDDEN = "I hid a password in that note, so it isn't stored."
SECRET_DELETE_BUTTON = "Delete my message"
CANT_READ_VIDEO = "That video is too long to read. Send a screenshot instead."
TEXT_ONLY = "I keep text only. Paste the text or send a screenshot."
NOT_KEPT = "I keep text, links, photos and voice notes."
HEIC = "Send it as a photo instead."
SILENT_VOICE = "I couldn't hear anything in that voice note."
NOT_FOUND = "I couldn't find that."
NOT_FOUND_CLOSEST = "I couldn't find that. Closest:"
DEGRADED = "I can't think it through right now. These look closest:"
FORGOTTEN = "Forgotten."
UNDO = "Undo"
UNDONE = "Undone."
NOTHING_TO_UNDO = "There is nothing to undo."
PRIVATE_ONLY = "I work in private chats only."
START_FIRST = "Send /start to the bot first."
INVALID_INVITE = "That invite code doesn't work. You can try the sample memory here: {link}"
TIMEZONE_SET = "Time zone set to {tz}."
TIMEZONE_BAD = "I don't know that time zone. Try something like /timezone Asia/Kathmandu."
TIMEZONE_HELP = "Your time zone is {tz}. Change it with /timezone Asia/Kathmandu."
SHOW_IN_SKY = "Show in sky"
SAVE_INSTEAD = "Save instead"
SAVED_INSTEAD = "Saved."
EXPORT_LINK = "Your export is too big for Telegram. Download it from the web app: {link}"
EXPORT_SENT = "Everything new since your last export, as JSONL and Markdown."
EXPORT_NOTHING_NEW = "Nothing new since your last export."
SKY_BUTTON = "Sky"
HELP = (
    "Send me anything: text, links, screenshots, voice notes, forwards. I save it and react "
    "with 👌.\n"
    "Ask a question by ending with ? or starting with /ask.\n\n"
    "/web opens your sky in the browser\n"
    "/forget forgets the last thing you saved (or reply to a message with /forget)\n"
    "/undo reverts the last change I made to your facts\n"
    "/timezone Asia/Kathmandu sets your time zone\n"
    "/export sends you everything you saved"
)
COMMANDS = (
    ("web", "Open your sky"),
    ("ask", "Ask a question"),
    ("forget", "Forget the last thing, or the replied one"),
    ("undo", "Revert the last change to your facts"),
    ("timezone", "Set your time zone"),
    ("export", "Export everything"),
    ("help", "How Moira works"),
)
