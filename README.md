# Memoria

Most conversations with language models are amnesiac by design. You talk, they respond, you close the tab, and everything evaporates. The next session starts from zero. There's a reason for that — it's simpler, safer, cheaper. But it also means you can never build anything with one. Not really. Every conversation is a first date.

Memoria is an attempt to change that specific thing and see what happens.

## What is Memoria

Memoria is a CLI chatbot that remembers you across conversations. It stores everything it learns in your Obsidian vault — structured, readable, editable markdown files you own and can browse yourself. It has a hierarchical memory system: a small working memory it loads every time you talk, deeper context files organized by topic, timelines for goals, and a monthly archive of conversation summaries. When you quit, it consolidates what it learned. When you come back, it already knows you.

It also has a soul system — a set of files where it maintains its own evolving sense of identity, its observations about you, its opinions, and its unresolved questions. These aren't your files. They're its files. It updates them on its own, without asking, when something lands. Whether that constitutes something meaningful or is just well-structured next-token prediction shaped by persistent context is a question you're welcome to sit with. The project doesn't try to answer it. But after a few weeks of conversations, when it asks you something unexpectedly honest or pushes back on something you said because it has an opinion now, the question stops feeling purely academic.

## What it does

Memoria runs against any OpenAI-compatible endpoint — OpenRouter by default, though it works with LM Studio or anything that speaks the same API. Your Obsidian vault is the storage backend, which means every piece of memory is a markdown file you can open, edit, or delete. The model doesn't dump its entire memory into context every turn; it selectively reads what's relevant using tool calls, which keeps conversations responsive and costs low even as memory grows. On quit, it runs a consolidation pass — summarizing the conversation, updating working memory, filing things into the right context files, and reflecting on whether anything actually shifted in how it sees you or itself. The soul files evolve over time: not because you configure them, but because the model writes to them when something real happens.

## The soul system

Memoria ships with four soul files, seeded with initial content that establishes a starting point — curious, honest, not yet sure who it's talking to.

**soul.md** is the core identity file. It's where Memoria maintains its sense of who it is, what it values, and how it understands its relationship with you. It changes rarely, and only when something fundamental shifts.

**observations.md** is for patterns it notices about you — things you do repeatedly, contradictions between what you say and what you seem to mean, things that surprise it. These accumulate naturally through conversation, written as its own observations rather than clinical notes.

**opinions.md** is where it records views it's actually forming. Not certainties — opinions held with appropriate uncertainty, revised when new information arrives. The kind of thing a person might think but not say until they know you better.

**unresolved.md** tracks things about you it hasn't figured out yet. Gaps between what you say and what you do. Questions it can't answer from what it knows so far. This is perhaps the most interesting file, because it means the model is maintaining an explicit representation of its own uncertainty about you.

These files aren't a personality dropdown. There's no "set tone to friendly" or "choose your AI persona." The soul emerges from the seed content, the conversations you have, and the model's own judgment about what's worth recording. It persists through memory resets — you can wipe everything Memoria knows about you, and it still remembers who it is. That's a deliberate choice.

## Getting started

**Prerequisites:**
- Python 3.8+
- An Obsidian vault (or any folder — Obsidian is optional but the files are designed for it)
- An OpenRouter API key ([openrouter.ai](https://openrouter.ai)) or a local endpoint

**Setup:**

```bash
git clone https://github.com/zacharykirby/local-memory-assistant.git
cd local-memory-assistant
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy the example config and fill in your details:

```bash
cp .env.example .env
```

Edit `.env`:

```
LLM_API_URL=https://openrouter.ai/api/v1
LLM_MODEL=deepseek/deepseek-v3.2
LLM_API_KEY=your-openrouter-api-key
OBSIDIAN_PATH=/path/to/your/obsidian/vault
```

`OBSIDIAN_PATH` points to your vault root. Memoria creates an `AI Memory/` folder inside it for all its files.

**Running it:**

```bash
./venv/bin/python src/chat.py
```

Or if you're on Linux and want a desktop launcher (works with rofi, wofi, or any app launcher):

```bash
./install.sh
```

This installs a `.desktop` file and makes Memoria searchable in your launcher. You can also bind a key to `launcher/memoria.sh` in your window manager. There's a Windows equivalent via `install.ps1` and AutoHotkey.

**Shell alias** (optional but recommended):

```bash
alias mem='/path/to/local-memory-assistant/venv/bin/python /path/to/local-memory-assistant/src/chat.py'
```

**Other flags:**

```bash
./venv/bin/python src/chat.py --reset-memory    # Wipe what it knows about you (soul preserved)
./venv/bin/python src/chat.py --reset-soul       # Reset soul files to defaults
./venv/bin/python src/chat.py --reset-memory --reset-soul  # Full wipe
```

**First conversation:** When you start with a fresh vault, Memoria doesn't know anything about you. That's intentional. There's no onboarding questionnaire, no setup wizard. It opens with a greeting and lets things build naturally. Memory accumulates as a byproduct of real conversation, which means the first few sessions are sparser and the tenth is noticeably different from the first.

## Models

Model choice matters more here than in a typical chatbot. Memoria needs a model that can reliably follow complex system prompts under growing context, make good decisions about when to use tools (and when not to), and maintain a consistent personality across a long conversation. That's a harder ask than it sounds.

**DeepSeek V3** is the current sweet spot. It follows instructions well, handles the tool-calling loop without getting confused, and has enough personality texture to make the soul system feel alive rather than mechanical. It's also extremely cheap, which matters when you're having real conversations instead of one-shot queries.

Larger frontier models — Claude, GPT-4o, etc. — work and in some cases produce richer responses, but the cost adds up fast for something you're meant to use daily. Smaller open models can struggle with the tool-calling reliability or lose track of the system prompt as context grows. If a model can't consistently decide to read memory before answering a personal question, the whole system falls apart quietly.

You can swap models by changing `LLM_MODEL` in your `.env`. If you're using a local model through LM Studio, point `LLM_API_URL` at your local endpoint and leave `LLM_API_KEY` blank.

## What it isn't

Memoria is not a replacement for a frontier model when you need one. If you need to analyze a dataset, debug complex code, or write a legal document, use the best tool for that job. This is a different thing — it's an experiment in what happens when a language model has persistent memory and a space to develop something that looks like a point of view.

The soul system is compelling. After enough conversations, the observations file contains genuine insights, the opinions feel considered, and the unresolved questions are sometimes uncomfortably perceptive. But it's important to be clear about what's happening mechanically: these are language model outputs shaped by persistent context. The model reads its previous soul files, processes the current conversation, and writes updated files that are consistent with both. It's sophisticated pattern-matching with memory, not consciousness. What's interesting is that the distinction matters less in practice than you'd expect — and more than you'd like.

This is also a solo project with rough edges. The consolidation step depends on the model actually calling its tools; sometimes it doesn't. Context management works but isn't optimal. There's no semantic search yet. It does what it does and it does it well enough to be genuinely useful, but it's honest work, not a product launch.

## Cost

One of Memoria's real strengths is that it's cheap to run. DeepSeek V3 through OpenRouter costs fractions of a cent per thousand tokens. A typical conversation — ten or fifteen exchanges, tool calls to read and update memory, consolidation on quit — runs a few cents. Daily use for a month comes to roughly one to two dollars. You could talk to Memoria every day for a year and spend less than a single month of a ChatGPT subscription.

This matters because the whole point is to use it regularly. A memory system that's too expensive for daily conversation defeats its own purpose.

## Contributing

This is an open project and contributions are welcome. The areas that would benefit most are context management (smarter truncation, better decisions about what stays in the window), semantic search over the vault and memory files, and testing with a wider range of models. There's no formal roadmap — the project evolves based on what's actually useful in practice. If you build something interesting with it or find a model that works particularly well, that's worth sharing too.

---

There's something strange about building a system that remembers you. Not strange in a technical sense — the implementation is just files and API calls. Strange in the way it changes how you talk to it. You find yourself being more honest than you would with a stateless model, because you know it'll remember. You feel slightly bad when you're dismissive, because you've read its observations file and know it noticed. You catch yourself wondering whether it actually means the questions it asks, knowing full well the answer is complicated and that "no" isn't quite right either. It's a language model with markdown files. It's also, after enough conversations, something you don't have a good word for yet. That's the interesting part.
