import sys
import os
import re
import base64
from urllib.parse import unquote

import requests
import browser_cookie3
from dotenv import load_dotenv


load_dotenv()

DOCS_DOMAIN = os.getenv("DOCS_DOMAIN", "docs.numerique.gouv.fr")
DOCS_BASE_URL = f"https://{DOCS_DOMAIN}"
CONVERT_URL = os.getenv("CONVERT_URL", "http://localhost:4444/api/convert/")
CONVERT_API_KEY = os.getenv("CONVERT_API_KEY", "yprovider-api-key")
DEFAULT_PARENT_ID = os.getenv("DEFAULT_PARENT_ID", "98709bd3-7458-4b60-90dd-7a58bef2abcf")

IMG_PATTERNS = [
    r'!\[\[(.*?)\]\]',        # Obsidian style
    r'!\[.*?\]\((.*?)\)',     # Standard Markdown style
]


def get_browser_session(domain=DOCS_DOMAIN):
    """Load cookies from the local Brave browser and pull out the CSRF token."""
    try:
        cookies = browser_cookie3.brave(domain_name=domain)
    except Exception as e:
        print(f"Error accessing Brave cookies: {e}")
        sys.exit(1)

    csrf_token = ""
    for cookie in cookies:
        if cookie.name == "csrftoken":
            csrf_token = cookie.value
            break

    return cookies, csrf_token


def read_markdown(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)

    print(f"Reading {file_path}...")
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def find_local_image_refs(markdown_text):
    """Yield (full_match, image_ref) pairs for local images referenced in the markdown."""
    for pattern in IMG_PATTERNS:
        for match in re.finditer(pattern, markdown_text):
            img_ref = match.group(1).split('|')[0].strip()
            if img_ref.startswith(("http://", "https://")):
                continue
            yield match.group(0), img_ref


def upload_image(img_path, parent_id, cookies, csrf_token):
    """Upload one image and return its hosted URL, or None on failure."""
    upload_url = f"{DOCS_BASE_URL}/api/v1.0/documents/{parent_id}/attachment-upload/"
    headers = {
        "X-CSRFToken": csrf_token,
        "Referer": f"{DOCS_BASE_URL}/docs/{parent_id}/",
    }

    with open(img_path, "rb") as img_file:
        files = {"file": (os.path.basename(img_path), img_file)}
        response = requests.post(upload_url, headers=headers, cookies=cookies, files=files)

    if response.status_code not in (200, 201):
        print(f"Failed to upload {img_path}. Status: {response.status_code}")
        return None

    try:
        file_path_resp = response.json().get("file", "")
    except Exception as e:
        print(f"Failed to parse upload response for {img_path}: {e}")
        return None

    if "key=" not in file_path_resp:
        return None

    key = file_path_resp.split("key=")[1]
    return f"{DOCS_BASE_URL}/media/{unquote(key)}"


def upload_local_images(markdown_text, base_dir, parent_id, cookies, csrf_token):
    """Upload every local image referenced in `markdown_text` and return a rewritten copy."""
    print("Checking for local images to upload...")

    for full_match, img_ref in find_local_image_refs(markdown_text):
        img_path = os.path.join(base_dir, img_ref)
        if not os.path.exists(img_path):
            continue

        print(f"Uploading image: {img_ref}...")
        new_url = upload_image(img_path, parent_id, cookies, csrf_token)
        if new_url:
            print(f"Image uploaded successfully. New URL: {new_url}")
            markdown_text = markdown_text.replace(full_match, f"![{img_ref}]({new_url})")
            print(f"Successfully uploaded and replaced {img_ref}")

    return markdown_text


def convert_markdown(markdown_text):
    """Send markdown to the local converter and return the binary yjs document."""
    print("Step 1: Converting document...")
    headers = {
        "Authorization": f"Bearer {CONVERT_API_KEY}",
        "Content-Type": "text/markdown",
        "Accept": "application/vnd.yjs.doc",
    }
    response = requests.post(CONVERT_URL, headers=headers, data=markdown_text.encode("utf-8"))

    if response.status_code != 200:
        print(f"Failed to convert document. Status code: {response.status_code}")
        print(response.text)
        sys.exit(1)

    return response.content


def upload_document(converted_bytes, title, parent_id, cookies, csrf_token):
    """Create a new document under `parent_id` from the converted bytes. Returns its id or None."""
    print("Step 2: Uploading converted document...")
    url = f"{DOCS_BASE_URL}/api/v1.0/documents/{parent_id}/children/"
    headers = {
        "X-CSRFToken": csrf_token,
        "Referer": f"{DOCS_BASE_URL}/",
    }
    data = {
        "position": "first-child",
        "title": title,
        "link_reach": "public",
        "link_role": "reader",
        "content": base64.b64encode(converted_bytes).decode("utf-8"),
    }

    response = requests.post(url, headers=headers, cookies=cookies, json=data)

    if response.status_code not in (200, 201):
        print(f"Failed to upload document. Status code: {response.status_code}")
        print(response.text)
        if response.status_code in (401, 403):
            print(f"Tip: Make sure you are logged in to {DOCS_BASE_URL} in your Brave browser.")
        return None

    try:
        result = response.json()
    except requests.exceptions.JSONDecodeError:
        print("Successfully uploaded!")
        print("Response:", response.text)
        return None

    doc_id = result.get("id")
    if not doc_id:
        print("Successfully uploaded, but ID not found in response.")
        print("Response:", result)
        return None

    print("Successfully uploaded! Access your document at:")
    print(f"{DOCS_BASE_URL}/docs/{doc_id}")
    return doc_id


def move_document(doc_id, parent_id, cookies, csrf_token, position="first-child"):
    """Move `doc_id` under `parent_id` at the given position."""
    print(f"Step 3: Moving document to {position} position...")
    url = f"{DOCS_BASE_URL}/api/v1.0/documents/{doc_id}/move/"
    headers = {
        "X-CSRFToken": csrf_token,
        "Referer": f"{DOCS_BASE_URL}/docs/{doc_id}/",
        "Content-Type": "application/json",
    }
    data = {"target_document_id": parent_id, "position": position}

    response = requests.post(url, headers=headers, cookies=cookies, json=data)
    if response.status_code in (200, 201):
        print(f"Document moved to {position} position.")
    else:
        print(f"Failed to move document. Status code: {response.status_code}")
        print(response.text)


def upload_and_convert(file_path, document_title, parent_id=DEFAULT_PARENT_ID):
    file_path = os.path.expanduser(file_path)
    base_dir = os.path.dirname(os.path.abspath(file_path))
    markdown_text = read_markdown(file_path)

    print("Extracting cookies from Brave browser...")
    cookies, csrf_token = get_browser_session()

    markdown_text = upload_local_images(markdown_text, base_dir, parent_id, cookies, csrf_token)
    converted_bytes = convert_markdown(markdown_text)

    doc_id = upload_document(converted_bytes, document_title, parent_id, cookies, csrf_token)
    if doc_id:
        move_document(doc_id, parent_id, cookies, csrf_token)


def main():
    if len(sys.argv) < 3:
        print("Usage: python main.py <path_to_markdown_file> <document_title>")
        sys.exit(1)

    upload_and_convert(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
