# Docs Share — share you local markdown notes to La Suite Numérique Docs

I write all my notes locally in [Obsidian](https://obsidian.md/). Most of them
stay private, but every now and then I want to share one with colleagues and
work on it collaboratively. The collaborative editor I use is
[Docs](https://docs.numerique.gouv.fr/) on the French government's
[La Suite Numérique](https://lasuite.numerique.gouv.fr/) platform.

This script bridges the two: it takes a local Markdown file, uploads any
referenced images, converts the Markdown to the y-doc format Docs expects, and
creates the document under a chosen parent.

## How it works

1. Reads the local Markdown file.
2. Pulls cookies from your browser session — this is how it
   authenticates with Docs (no API token needed; you just need to be logged
   in). (by default is brave, you can change it to chrome, firefox .... (https://github.com/borisbabic/browser_cookie3))
3. Finds local image references (Obsidian `![[image.png]]` and standard
   `![alt](image.png)` syntax), uploads each one as an attachment, and
   rewrites the Markdown to point at the hosted URL.
4. Posts the rewritten Markdown to a local converter (impress y-provider) that
   returns binary yjs document bytes.
5. Base64-encodes those bytes and creates a new child document under the
   configured parent.
6. Moves the new document to the `first-child` position so it's easy to find.

Optionally, if `OPENAI_API_KEY` is set, the script asks an LLM to generate a
short excerpt of the document and attaches it to the upload. The OpenAI SDK is
used as the client, so any OpenAI-compatible endpoint works — including
[Albert](https://albert.api.etalab.gouv.fr/) (the French government's
LLM gateway), or your own provider. Point `OPENAI_BASE_URL` at the endpoint
of your choice and pick a model with `OPENAI_MODEL`.

## Prerequisites

- To be logged into <https://docs.numerique.gouv.fr> or any other instance of Docs (You can specify the url in the .env). The script reads cookies from your browser's local profile.
- **Docker** to run the converter:
  ```
  docker run -p 4444:4444 --name impress-convert \
    -e Y_PROVIDER_API_KEY=yprovider-api-key \
    impress:y-provider-development
  ```
- **Python 3.14** with [uv](https://github.com/astral-sh/uv) (the repo ships a
  `uv.lock`).

## Setup

```sh
uv sync                      # install deps into .venv
cp .env.example .env         # adjust DEFAULT_PARENT_ID, etc.
```

The `.env` file holds the parent document id and the converter URL/key. See
`.env.example` for the available variables.

## Usage

```sh
make publish path=~/Documents/obsidian_vault/Work/notes.md title="Meeting notes"
```

The script prints the URL of the new document on success. If you get a
`401`/`403`, log into Docs and try again.

## Tests

```sh
make test               # unit tests, no network required
make test-integration   # hits the local converter; auto-skipped if not running
```
