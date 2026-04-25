import base64
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import main


def make_response(status_code=200, json_data=None, content=b"", text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.text = text
    if json_data is None:
        resp.json.side_effect = main.requests.exceptions.JSONDecodeError("no json", "", 0)
    else:
        resp.json.return_value = json_data
    return resp


# ---------- find_local_image_refs ----------

def test_find_local_image_refs_obsidian():
    refs = list(main.find_local_image_refs("text ![[local.png]] more"))
    assert refs == [("![[local.png]]", "local.png")]


def test_find_local_image_refs_standard_markdown():
    refs = list(main.find_local_image_refs("text ![alt](other.jpg) more"))
    assert ("![alt](other.jpg)", "other.jpg") in refs


def test_find_local_image_refs_skips_remote_urls():
    md = "![alt](https://example.com/x.png) ![[http://example.com/y.png]]"
    assert list(main.find_local_image_refs(md)) == []


def test_find_local_image_refs_strips_obsidian_alt_text():
    md = "![[image.png|some alt]]"
    refs = list(main.find_local_image_refs(md))
    assert refs == [("![[image.png|some alt]]", "image.png")]


# ---------- read_markdown ----------

def test_read_markdown_returns_contents(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("hello", encoding="utf-8")
    assert main.read_markdown(str(f)) == "hello"


def test_read_markdown_exits_when_missing(tmp_path):
    with pytest.raises(SystemExit):
        main.read_markdown(str(tmp_path / "missing.md"))


# ---------- get_browser_session ----------

def test_get_browser_session_extracts_csrf():
    fake_cookies = [
        SimpleNamespace(name="sessionid", value="abc"),
        SimpleNamespace(name="csrftoken", value="tok-123"),
    ]
    with patch.object(main.browser_cookie3, "brave", return_value=fake_cookies) as brave:
        cookies, csrf = main.get_browser_session(domain="example.com")
    brave.assert_called_once_with(domain_name="example.com")
    assert cookies is fake_cookies
    assert csrf == "tok-123"


def test_get_browser_session_returns_empty_when_no_csrf():
    with patch.object(main.browser_cookie3, "brave", return_value=[]):
        _, csrf = main.get_browser_session()
    assert csrf == ""


def test_get_browser_session_exits_on_error():
    with patch.object(main.browser_cookie3, "brave", side_effect=RuntimeError("boom")):
        with pytest.raises(SystemExit):
            main.get_browser_session()


# ---------- upload_image ----------

def test_upload_image_returns_url_on_success(tmp_path):
    img = tmp_path / "pic.png"
    img.write_bytes(b"binary")
    response = make_response(
        status_code=201,
        json_data={"file": "/api/v1.0/documents/x/media-check/?key=docs%2Fabc.png"},
    )
    with patch.object(main.requests, "post", return_value=response) as post:
        url = main.upload_image(str(img), "parent-id", cookies="C", csrf_token="T")
    assert url == f"{main.DOCS_BASE_URL}/media/docs/abc.png"
    args, kwargs = post.call_args
    assert "parent-id/attachment-upload" in args[0]
    assert kwargs["headers"]["X-CSRFToken"] == "T"
    assert kwargs["cookies"] == "C"
    assert "file" in kwargs["files"]


def test_upload_image_returns_none_on_bad_status(tmp_path):
    img = tmp_path / "pic.png"
    img.write_bytes(b"x")
    response = make_response(status_code=500, text="server error")
    with patch.object(main.requests, "post", return_value=response):
        assert main.upload_image(str(img), "p", "c", "t") is None


def test_upload_image_returns_none_when_response_missing_key(tmp_path):
    img = tmp_path / "pic.png"
    img.write_bytes(b"x")
    response = make_response(status_code=200, json_data={"file": "/no/key/here"})
    with patch.object(main.requests, "post", return_value=response):
        assert main.upload_image(str(img), "p", "c", "t") is None


# ---------- upload_local_images ----------

def test_upload_local_images_rewrites_only_existing_files(tmp_path):
    (tmp_path / "exists.png").write_bytes(b"x")
    md = "![[exists.png]] and ![alt](missing.png) and ![](https://x/y.png)"

    def fake_upload(img_path, parent_id, cookies, csrf_token):
        return f"{main.DOCS_BASE_URL}/media/uploaded.png"

    with patch.object(main, "upload_image", side_effect=fake_upload) as up:
        result = main.upload_local_images(md, str(tmp_path), "pid", "c", "t")

    assert up.call_count == 1
    assert f"![exists.png]({main.DOCS_BASE_URL}/media/uploaded.png)" in result
    assert "missing.png" in result  # untouched
    assert "https://x/y.png" in result  # untouched


def test_upload_local_images_keeps_original_when_upload_fails(tmp_path):
    (tmp_path / "img.png").write_bytes(b"x")
    md = "![[img.png]]"
    with patch.object(main, "upload_image", return_value=None):
        result = main.upload_local_images(md, str(tmp_path), "pid", "c", "t")
    assert result == md


# ---------- convert_markdown ----------

def test_convert_markdown_returns_response_bytes():
    response = make_response(status_code=200, content=b"yjs-bytes")
    with patch.object(main.requests, "post", return_value=response) as post:
        out = main.convert_markdown("# hi")
    assert out == b"yjs-bytes"
    _, kwargs = post.call_args
    assert kwargs["headers"]["Authorization"] == f"Bearer {main.CONVERT_API_KEY}"
    assert kwargs["data"] == b"# hi"


def test_convert_markdown_exits_on_failure():
    response = make_response(status_code=500, text="err")
    with patch.object(main.requests, "post", return_value=response):
        with pytest.raises(SystemExit):
            main.convert_markdown("x")


# ---------- upload_document ----------

def test_upload_document_returns_id_and_sends_base64():
    payload = b"hello"
    response = make_response(status_code=201, json_data={"id": "new-doc-id"})
    with patch.object(main.requests, "post", return_value=response) as post:
        doc_id = main.upload_document(payload, "Title", "parent", "c", "tok")
    assert doc_id == "new-doc-id"
    _, kwargs = post.call_args
    assert kwargs["json"]["title"] == "Title"
    assert kwargs["json"]["content"] == base64.b64encode(payload).decode("utf-8")
    assert kwargs["headers"]["X-CSRFToken"] == "tok"


def test_upload_document_returns_none_on_failure():
    response = make_response(status_code=403, text="nope")
    with patch.object(main.requests, "post", return_value=response):
        assert main.upload_document(b"x", "T", "p", "c", "t") is None


def test_upload_document_returns_none_when_id_missing():
    response = make_response(status_code=200, json_data={"foo": "bar"})
    with patch.object(main.requests, "post", return_value=response):
        assert main.upload_document(b"x", "T", "p", "c", "t") is None


# ---------- move_document ----------

def test_move_document_posts_expected_payload():
    response = make_response(status_code=200, json_data={})
    with patch.object(main.requests, "post", return_value=response) as post:
        main.move_document("doc-id", "parent-id", "c", "tok")
    args, kwargs = post.call_args
    assert "doc-id/move" in args[0]
    assert kwargs["json"] == {"target_document_id": "parent-id", "position": "first-child"}
    assert kwargs["headers"]["X-CSRFToken"] == "tok"


def test_move_document_handles_failure_quietly():
    response = make_response(status_code=500, text="bad")
    with patch.object(main.requests, "post", return_value=response):
        # Should not raise.
        main.move_document("d", "p", "c", "t")


# ---------- upload_and_convert (integration) ----------

def test_upload_and_convert_pipeline(tmp_path):
    md_file = tmp_path / "input.md"
    md_file.write_text("# hi", encoding="utf-8")

    with patch.object(main, "get_browser_session", return_value=("cookies", "csrf")) as gs, \
         patch.object(main, "upload_local_images", return_value="# hi rewritten") as ui, \
         patch.object(main, "convert_markdown", return_value=b"yjs") as cm, \
         patch.object(main, "upload_document", return_value="doc-id") as ud, \
         patch.object(main, "move_document") as mv:
        main.upload_and_convert(str(md_file), "My title", parent_id="parent-x")

    gs.assert_called_once()
    ui.assert_called_once()
    assert ui.call_args.args[0] == "# hi"
    assert ui.call_args.args[2] == "parent-x"
    cm.assert_called_once_with("# hi rewritten")
    ud.assert_called_once_with(b"yjs", "My title", "parent-x", "cookies", "csrf")
    mv.assert_called_once_with("doc-id", "parent-x", "cookies", "csrf")


def test_upload_and_convert_skips_move_when_upload_fails(tmp_path):
    md_file = tmp_path / "input.md"
    md_file.write_text("# hi", encoding="utf-8")

    with patch.object(main, "get_browser_session", return_value=("c", "t")), \
         patch.object(main, "upload_local_images", return_value="x"), \
         patch.object(main, "convert_markdown", return_value=b"y"), \
         patch.object(main, "upload_document", return_value=None), \
         patch.object(main, "move_document") as mv:
        main.upload_and_convert(str(md_file), "T")

    mv.assert_not_called()
