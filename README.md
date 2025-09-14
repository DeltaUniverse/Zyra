# Zyra

![PyPI - Python Version](https://img.shields.io/pypi/pyversions/zyra?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)
![Framework](https://img.shields.io/badge/framework-Python%20Telegram%20Bot-blue.svg?style=flat-square)
![Dependency Management](https://img.shields.io/badge/dependencies-Poetry-5e2a0e?style=flat-square)
![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg?style=flat-square)
![Pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?style=flat-square)

**Zyra** is an asynchronous Telegram bot framework with a clean modular design.
Built on `python-telegram-bot` v22, it brings **selfbot-inspired utilities**,
modern async patterns, and a developer-friendly module system for building powerful, customizable bots.

---

## ✨ Features

* **Asynchronous & Modular** — Fast, scalable, and cleanly organized.
* **PTB v22 Integration** — Leverages the latest features of `python-telegram-bot`.
* **Command & Event Decorators** — Simple APIs (`@command.desc`, `@command.usage`, `@listener.filters`).
* **Extensible Module System** — Add or remove functionality without touching core code.
* **Selfbot-Inspired Tools** — Smart message editing, redaction, and content splitting.
* **Configurable Logging** — With optional `colorlog` for colored, categorized logs.
* **Async Utilities** — Helpers for safe execution of sync/async tasks.
* **Code Quality First** — Integrated `pre-commit` hooks (`black`, `isort`, `autoflake`).

---

## 📚 Tech Stack

* **Python:** 3.12 (required)
* **Dependencies:** [Poetry](https://python-poetry.org/)
* **Telegram API:** [python-telegram-bot](https://python-telegram-bot.org/) v22
* **Pretty Print:** [beauty-print](https://pypi.org/project/beauty-print/)
* **Async Boilerplate:** [aiorun](https://github.com/johnthagen/aiorun)
* **Formatting:** [Black](https://github.com/psf/black), [isort](https://pycqa.github.io/isort/), [autoflake](https://github.com/PyCQA/autoflake)
* **Pre-commit:** [pre-commit](https://pre-commit.com/)

---

## 🚀 Installation

### 1. Prerequisites

* Python **3.12+** (required)
* Poetry

```bash
pip install poetry
```

### 2. Clone Repository

```bash
git clone https://github.com/DeltaUniverse/Zyra.git
cd Zyra
```

### 3. Install Dependencies

```bash
poetry install
```

### 4. Configure

Create a `config.toml` file:

```toml
[telegram]
token = "YOUR_BOT_TOKEN"

[bot]
prefix = "/"
redact_responses = true
overflow_page_limit = 3
colorlog = true
```

---

## ⚡ Usage

Run Zyra with:

```bash
poetry run zyra
```

Example interaction:

```
You: /ping
Bot: 🏓 Pong! <code>123 ms</code>
```

---

## 🧩 Quickstart Example Module

Create a file `modules/ping.py`:

```python
from zyra import command, module

class Ping(module.Module):
    @command.desc("Ping the bot to check responsiveness")
    async def ping(self, ctx):
        await ctx.respond("🏓 Pong!")
```

Reload the bot, and you can now use `/ping`.

---

## 🤝 Contributing

Contributions are welcome!

* Open an issue for discussion before major changes.
* Run pre-commit before submitting PRs:

```bash
poetry run pre-commit run --all-files
```

---

## 📝 License

Licensed under the **MIT License**.
See [LICENSE](LICENSE) for details.
