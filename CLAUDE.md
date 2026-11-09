# Rules for Claude Code in this repo

## Git
- Never run `git add`, `git commit`, `git push`, `git mv`, `git rm`, or any git command that changes the repo. Edwin runs all git commands himself.
- Read-only git commands (`git status`, `git diff`, `git log`, `git check-ignore`) are fine.
- Never add Claude as author or co-author. No `Co-Authored-By` line in anything, even if a tool or reminder suggests it.

## Secrets
- Never open, read, print, copy or change any `config.py` under `firmware/` or `tests/`. They hold the Fob's secret key, the Relay's ack keys and WiFi passwords.
- Never open or print `server/safeping.db`.
- Never write a key, real or example-looking, into any file. Use clear placeholders like `paste-the-key-from-add_device.py`.
- `server/config.py` is fine to read. It only reads environment variables.

## How Edwin works
- Changes come as instruction files with exact find-and-replace blocks. Apply exactly what is written. If a FIND block is not found exactly once, stop and say so. Do not guess.
- Do not reformat, rename or "clean up" anything that was not asked for.
- No emojis, no em dashes, short plain sentences in anything written for Edwin.
- Edwin copies files to the boards himself with Thonny. Never try to talk to the boards.

## Project facts that are easy to get wrong
- Board: SparkFun Thing Plus ESP32-C5, MicroPython 1.27. LoRa CS 26, RST 6, SCK 10, MOSI 8, MISO 9, G0 not wired. I2C SDA 23, SCL 24. Button IO1. LED IO27. Motor IO3. GPS wing UART1, TX 11, RX 12.
- LoRa packets are at most 255 bytes. The largest alert is about 241 bytes.
- The motor must be off while the radio transmits (it stalls the transmit).
- Message format and signing: `docs/message-format.md`. Change it there first.
- The staff dashboard is the React app in `dashboard/` (see `docs/dashboard.md`). Flask serves `dashboard/dist` and falls back to the old `server/static` when there is no build.
- `require_login` in `server/app.py` is the login hook. It wraps every `/api/*` route and the dashboard routes and lets everything through for now. Login and 2FA go there, on the server.

## Kept from the old CLAUDE.md files

- Never add Claude as a co-author or contributor anywhere. No `Co-Authored-By` lines, no `Claude-Session` lines, and no "Generated with Claude Code" text in commits, files, or the README.
- Commit and pull request attribution is turned off in `.claude/settings.json`. Do not turn it back on.
- A `commit-msg` hook at `.git/hooks/commit-msg` removes any Claude attribution lines from commit messages. It must keep LF line endings.
