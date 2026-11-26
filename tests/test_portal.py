"""xippios.usda.fas.portal: the kit of the FAS portal that the three snapshot scripts share.

The kit's hooks are called as core's frame calls them, with a ``Page`` and a ``Response`` or a
``Row``, and the last test runs core's frame itself, ``xippios.core.refresh.run``, on a
``Snapshot`` declared with the kit, through a client whose transport serves composed pages: it
writes the snapshot, and ``--check`` then reports no difference. Nothing here sends a request.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from xippios.core import AsyncClient, ClientConfig
from xippios.core.refresh import Page, Response, Row, Section, Snapshot, dump_json, run

from xippios.usda.fas.portal import Portal, shell_text

PORTAL_URL = "https://apps.fas.usda.gov/opendatawebV2/"
PORTAL_SWAGGER_URL = PORTAL_URL + "assets/swagger/swagger.json"
CLASSIC_UI_URL = "https://apps.fas.usda.gov/opendata/swagger/ui/index"
PORTAL_FILE = "openapi/portal-document.json"
BACKEND_FILE = "openapi/backend-docs-v1.json"
"""The portal's pages and the files the kit keeps, which the kit keeps to itself."""

BACKEND_URL = "https://apps.fas.usda.gov/OpenData/swagger/docs/v1"
SHELL_NOTE = "client-rendered shell, no documentation text"
"""The kit's note of a shell's row, which the kit keeps to itself."""
MAX_SHELL_BYTES = 16_384
"""The kit's bound of a shell, which the kit keeps to itself and its capture states."""
BUNDLE = "main.0123abcd.js"
DOCUMENT: dict[str, Any] = {
    "swagger": "2.0",
    "info": {"version": "v1", "title": "FAS Open Data", "description": "ESR, GATS and PSD"},
    "host": "api.fas.usda.gov",
    "schemes": ["https"],
    "paths": {
        "/api/esr/regions": {
            "get": {"responses": {"200": {"schema": {"$ref": "#/definitions/Region"}}}}
        },
        "/api/gats/regions": {
            "get": {"responses": {"200": {"schema": {"$ref": "#/definitions/GatsRegion"}}}}
        },
        "/api/esr/exports/{code}": {
            "get": {
                "responses": {
                    "200": {
                        "schema": {
                            "type": "array",
                            "items": {"$ref": "#/definitions/Export%20Row"},
                        }
                    }
                }
            }
        },
        "/api/psd/commodities": {"get": {"responses": {"200": {"description": "OK"}}}},
        "/api/psd/regions": {"get": {"responses": {"200": {"description": "OK"}}}},
    },
    "definitions": {
        "GatsRegion": {"type": "object"},
        "Region": {"properties": {"code": {"$ref": "#/definitions/Code~1Name~0x"}}},
        "Code/Name~x": {"type": "string"},
        "Export Row": {"properties": {"region": {"$ref": "#/definitions/Region"}}},
        "Unused": {"type": "object"},
    },
    "securityDefinitions": {"api_key": {"type": "apiKey", "name": "X-Api-Key", "in": "header"}},
}
"""A Swagger 2.0 document in the shape of the portal's: three services' paths, definitions
that reference others, escaped (``~1``, ``~0``) and percent-encoded, and one that no kept path
reaches. It is an input of the test, not an answer from USDA FAS."""


def text(document: object) -> bytes:
    """A document's text as upstream serves it: ``json.dumps(indent=2, ensure_ascii=False)``,
    with no final newline. It is an input of the test, not an answer from USDA FAS."""
    return json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8")


def response(url: str, body: bytes, status: int = 200, content_type: str = "") -> Response:
    """A ``Response`` as the frame hands a hook one. It is an input of the test, not an answer
    from USDA FAS."""
    return Response(url, status, body, content_type or None, None, None, ())


def portal_shell(*scripts: str) -> bytes:
    """The portal page's shell, its mount point and the bundles it loads. It is an input of the
    test, not an answer from USDA FAS."""
    tags = "".join(f'<script src="{name}"></script>' for name in scripts)
    return f"<!doctype html><html><body><app-root></app-root>{tags}</body></html>".encode()


def classic_shell(
    root: str = "'https://apps.fas.usda.gov/OpenData'", paths: str = "/swagger/docs/v1"
) -> bytes:
    """The classic Swagger UI page, its container and its configuration. It is an input of the
    test, not an answer from USDA FAS."""
    return (
        '<html><body><div id="swagger-ui-container"></div><script>'
        f"window.swashbuckleConfig = {{ rootUrl: {root}, discoveryPaths: arrayFrom('{paths}') }};"
        "</script></body></html>"
    ).encode()


ESR = Portal("/api/esr/")


# -- the portal and its services ------------------------------------------------------------


@pytest.mark.parametrize(
    ("prefix", "service"), [("/api/esr/", "ESR"), ("/api/gats/", "GATS"), ("/api/psd/", "PSD")]
)
def test_a_portal_is_read_for_one_of_its_three_services(prefix: str, service: str) -> None:
    assert Portal(prefix).service == service


@pytest.mark.parametrize("prefix", ["/api/nass/", "/api/esr", "api/esr/", "/API/ESR/"])
def test_a_prefix_of_no_service_on_the_portal_is_refused(prefix: str) -> None:
    with pytest.raises(ValueError, match="/api/esr/, /api/gats/ or /api/psd/"):
        Portal(prefix)


def test_the_portal_s_pages_come_first_in_their_order() -> None:
    # The backend document is not among them: ``linked`` names it after the classic UI page.
    assert ESR.pages == (
        Page(PORTAL_URL),
        Page(PORTAL_SWAGGER_URL, PORTAL_FILE, excerpt=True),
        Page(CLASSIC_UI_URL),
    )
    assert "swagger" not in PORTAL_FILE + BACKEND_FILE, "detect-secrets skips such a file"


# -- the cut of a document to one service ---------------------------------------------------


def test_a_document_is_cut_to_the_service_s_paths_and_the_definitions_they_reach() -> None:
    part = ESR._part(response(PORTAL_SWAGGER_URL, text(DOCUMENT)))
    assert type(part).__name__ == "_Part", "the kit's own: no source reads it"
    assert list(part.part) == list(DOCUMENT), "every top-level field, in upstream order"
    assert list(part.part["paths"]) == ["/api/esr/regions", "/api/esr/exports/{code}"]
    assert part.part["paths"]["/api/esr/regions"] == DOCUMENT["paths"]["/api/esr/regions"]
    assert list(part.part["definitions"]) == ["Region", "Code/Name~x", "Export Row"]
    assert part.part["info"] == DOCUMENT["info"]
    assert part.part["securityDefinitions"] == DOCUMENT["securityDefinitions"]
    assert (part.kept, part.definitions_kept, part.definitions_total) == (2, 3, 5)
    assert part.dropped == {"/api/gats/": 1, "/api/psd/": 2}
    assert list(part.dropped) == ["/api/gats/", "/api/psd/"], "in upstream order"


@pytest.mark.parametrize(
    ("prefix", "paths", "dropped"),
    [
        ("/api/gats/", ["/api/gats/regions"], {"/api/esr/": 2, "/api/psd/": 2}),
        (
            "/api/psd/",
            ["/api/psd/commodities", "/api/psd/regions"],
            {"/api/esr/": 2, "/api/gats/": 1},
        ),
    ],
)
def test_each_service_gets_its_own_part(
    prefix: str, paths: list[str], dropped: dict[str, int]
) -> None:
    part = Portal(prefix)._part(response(PORTAL_SWAGGER_URL, text(DOCUMENT)))
    assert list(part.part["paths"]) == paths
    assert part.dropped == dropped


def test_a_path_under_no_service_s_prefix_is_counted_under_itself() -> None:
    document = {**DOCUMENT, "paths": {**DOCUMENT["paths"], "/swagger/docs": {}}}
    part = ESR._part(response(PORTAL_SWAGGER_URL, text(document)))
    assert part.dropped == {"/api/gats/": 1, "/api/psd/": 2, "/swagger/docs": 1}


def test_a_document_without_definitions_keeps_none() -> None:
    document = {key: value for key, value in DOCUMENT.items() if key != "definitions"}
    document["paths"] = {"/api/esr/regions": {"get": {}}}
    part = ESR._part(response(PORTAL_SWAGGER_URL, text(document)))
    assert "definitions" not in part.part
    assert (part.kept, part.definitions_kept, part.definitions_total) == (1, 0, 0)


@pytest.mark.parametrize(
    ("document", "what"),
    [
        ({**DOCUMENT, "swagger": "3.0"}, "it is no Swagger 2.0 document"),
        ([DOCUMENT], "it is no Swagger 2.0 document"),
        ({**DOCUMENT, "paths": []}, "it has no paths object"),
        ({**DOCUMENT, "definitions": []}, "its definitions are not an object"),
        ({key: value for key, value in DOCUMENT.items() if key != "info"}, "it has no info object"),
        ({**DOCUMENT, "paths": {"/api/gats/regions": {}}}, "no path starts with /api/esr/"),
        (
            {
                **DOCUMENT,
                "definitions": {
                    name: value
                    for name, value in DOCUMENT["definitions"].items()
                    if name != "Code/Name~x"
                },
            },
            "#/definitions/Code/Name~x is referenced, absent",
        ),
    ],
)
def test_a_document_the_kit_does_not_recognise_stops_the_run(document: object, what: str) -> None:
    with pytest.raises(SystemExit) as stop:
        ESR._part(response(PORTAL_SWAGGER_URL, text(document)))
    message = str(stop.value.code)
    assert message.startswith(f"{PORTAL_SWAGGER_URL} changed: {what}.")
    assert message.endswith("Nothing was written.")


def test_of_several_absent_definitions_the_first_by_name_is_named() -> None:
    # The same document stops every run with the same words.
    document = {**DOCUMENT, "definitions": {"Code/Name~x": {"type": "string"}}}
    with pytest.raises(SystemExit, match="#/definitions/Export Row is referenced, absent"):
        ESR._part(response(PORTAL_SWAGGER_URL, text(document)))


def test_a_document_whose_text_the_cut_would_not_reproduce_stops_the_run() -> None:
    # Written in another form than upstream's, the cut part would not be upstream's text.
    compact = json.dumps(DOCUMENT).encode()
    with pytest.raises(SystemExit, match="no longer reproduces the fetched text"):
        ESR._part(response(PORTAL_SWAGGER_URL, compact))
    duplicate = text(DOCUMENT).replace(b'"swagger": "2.0",', b'"swagger": "2.0", "swagger": "2.0",')
    with pytest.raises(SystemExit, match="duplicate keys"):
        ESR._part(response(PORTAL_SWAGGER_URL, duplicate))


def test_reduce_writes_the_part_in_upstream_s_form_and_cuts_its_own_output_alike() -> None:
    page = ESR.pages[1]
    content = ESR.reduce(page, response(PORTAL_SWAGGER_URL, text(DOCUMENT)))
    part = ESR._part(response(PORTAL_SWAGGER_URL, text(DOCUMENT))).part
    assert content == dump_json(part)
    assert content.endswith(b"}\n")
    assert not content.endswith(b"\n\n")
    again = ESR.reduce(page, response(PORTAL_SWAGGER_URL, content.removesuffix(b"\n")))
    assert again == content, "a committed part, served as a document, gives itself back"
    crlf = text(DOCUMENT).replace(b"\n", b"\r\n")
    assert ESR.reduce(page, response(PORTAL_SWAGGER_URL, crlf)) == content, "up to line endings"


# -- the two shells and the backend document's URL ------------------------------------------


def test_a_shell_is_a_small_page_that_still_carries_its_mount_point() -> None:
    body = portal_shell(BUNDLE)
    assert shell_text(response(PORTAL_URL, body), "<app-root>") == body.decode()
    with pytest.raises(SystemExit, match="the client-rendering mount point '<ng-app>' is gone"):
        shell_text(response(PORTAL_URL, body), "<ng-app>")
    large = body + b" " * MAX_SHELL_BYTES
    with pytest.raises(SystemExit, match=f"{len(large)} bytes, more than a shell's"):
        shell_text(response(PORTAL_URL, large), "<app-root>")
    with pytest.raises(SystemExit, match="the body is not UTF-8"):
        shell_text(response(PORTAL_URL, b"<app-root>\xff"), "<app-root>")


def row(page: Page, body: bytes, content: bytes | None = None, note: str = "") -> Row:
    """A row as the frame makes it before the snapshot's ``note``. Its answer is an input of the
    test, not an answer from USDA FAS."""
    return Row(page, response(page.url, body), content, note)


def test_the_portal_page_s_note_names_the_bundle_it_loads() -> None:
    page = ESR.pages[0]
    assert ESR.note(row(page, portal_shell(BUNDLE))) == f"{SHELL_NOTE}; loads the bundle `{BUNDLE}`"
    twice = portal_shell(BUNDLE, BUNDLE)
    assert ESR.note(row(page, twice)) == f"{SHELL_NOTE}; loads the bundle `{BUNDLE}`"
    with pytest.raises(SystemExit, match=r"expected one main.<hash>.js, found \[\]"):
        ESR.note(row(page, portal_shell("vendor.js")))
    with pytest.raises(SystemExit, match="found"):
        ESR.note(row(page, portal_shell(BUNDLE, "main.ffff.js")))


def test_the_classic_ui_names_the_backend_document_which_is_captured_after_it() -> None:
    page = ESR.pages[2]
    ui = row(page, classic_shell())
    assert ESR.note(ui) == f"{SHELL_NOTE}; Swagger UI that loads `{BACKEND_URL}`"
    assert ESR.linked(ui) == (Page(BACKEND_URL, BACKEND_FILE, excerpt=True),)
    slashes = row(
        page, classic_shell("'https://apps.fas.usda.gov/OpenData/'", "|/swagger/docs/v1|")
    )
    assert ESR.linked(slashes) == (Page(BACKEND_URL, BACKEND_FILE, excerpt=True),)
    for other in (ESR.pages[0], ESR.pages[1], Page(BACKEND_URL, BACKEND_FILE, excerpt=True)):
        assert ESR.linked(row(other, b"{}")) == ()


@pytest.mark.parametrize(
    ("body", "what"),
    [
        (classic_shell("'a', rootUrl: 'b'"), "rootUrl ['a', 'b'], discoveryPaths"),
        (classic_shell(paths="/a|/b"), "expected one discovery path, found ['/a', '/b']"),
        (classic_shell(paths=""), "expected one discovery path, found []"),
        (
            classic_shell("'http://apps.fas.usda.gov/OpenData'"),
            "the document URL 'http://apps.fas.usda.gov/OpenData/swagger/docs/v1' left "
            "https://apps.fas.usda.gov",
        ),
        (
            classic_shell("'https://example.org'"),
            "the document URL 'https://example.org/swagger/docs/v1' left https://apps.fas.usda.gov",
        ),
    ],
)
def test_a_backend_url_the_kit_cannot_trust_stops_the_run(body: bytes, what: str) -> None:
    with pytest.raises(SystemExit) as stop:
        ESR.linked(row(ESR.pages[2], body))
    assert f"{CLASSIC_UI_URL} changed: {what}" in str(stop.value.code)


# -- the notes of a document's row and the section on the two documents ---------------------


def test_a_document_s_row_counts_the_paths_kept_and_dropped() -> None:
    page = ESR.pages[1]
    body = text(DOCUMENT)
    note = ESR.note(row(page, body, ESR.reduce(page, response(page.url, body))))
    assert note == (
        "ESR part: kept 2 `/api/esr/` paths; dropped 1 `/api/gats/`, 2 `/api/psd/` (out of "
        "scope here, own packages); kept 3 of 5 definitions"
    )
    part = text(ESR._part(response(page.url, body)).part)
    assert ESR.note(row(page, part)) == (
        "ESR part: kept 2 `/api/esr/` paths; dropped none (out of scope here, own packages); "
        "kept 3 of 3 definitions"
    )
    backend = Page(BACKEND_URL, BACKEND_FILE, excerpt=True)
    assert ESR.note(row(backend, body)).startswith("ESR part: kept 2 `/api/esr/` paths")
    assert (
        Portal("/api/gats/")
        .note(row(page, body))
        .startswith("GATS part: kept 1 `/api/gats/` paths; dropped 2 `/api/esr/`, 2 `/api/psd/`")
    )


def test_a_document_s_note_stops_on_a_key_twice_and_on_no_swagger_document() -> None:
    # The note writes nothing of the document and reads it with the frame's parse_json. Core's
    # frame calls reduce before note on the same answer, so a run never notes a document that
    # reduce refused.
    page = ESR.pages[1]
    compact = json.dumps(DOCUMENT).encode()
    duplicate = compact.replace(b'"swagger": "2.0",', b'"swagger": "2.0", "swagger": "2.0",')
    with pytest.raises(SystemExit) as stop:
        ESR.note(row(page, duplicate))
    assert str(stop.value.code).startswith(
        f"{PORTAL_SWAGGER_URL} changed: not usable JSON (duplicate keys ['swagger'])."
    )
    with pytest.raises(SystemExit, match=r"it is no Swagger 2\.0 document"):
        ESR.note(row(page, json.dumps({**DOCUMENT, "swagger": "3.0"}).encode()))


def test_a_page_of_the_source_s_own_keeps_its_note() -> None:
    own = Page(
        "https://www.fas.usda.gov/data", status=403, note="403 Access Denied at the CDN edge"
    )
    assert ESR.note(row(own, b"Access Denied", note=own.note)) == own.note


def parts_rows(portal: dict[str, Any], backend: dict[str, Any]) -> list[Row]:
    """The two documents' rows as the frame hands ``sections`` them, with the source's own
    page. Their answers are inputs of the test, not answers from USDA FAS."""
    return [
        row(ESR.pages[1], b"", dump_json(portal)),
        row(Page(BACKEND_URL, BACKEND_FILE, excerpt=True), b"", dump_json(backend)),
        row(ESR.pages[0], portal_shell(BUNDLE)),
    ]


def test_the_section_says_how_the_two_parts_compare() -> None:
    part = ESR._part(response(PORTAL_SWAGGER_URL, text(DOCUMENT))).part
    backend = {
        key: ("other.example" if key == "host" else value)
        for key, value in part.items()
        if key != "securityDefinitions"
    }
    backend["basePath"] = "/"
    (section,) = ESR.sections(parts_rows(part, backend))
    assert isinstance(section, Section)
    assert section.heading == "The two documents"
    assert " ".join(section.text.split()) == (
        "Both documents are kept because they are two upstream statements of the same API that "
        "need not agree on how it is reached. As fetched, their ESR parts differ in `host`; only "
        "the portal document has `securityDefinitions`; only the backend document has "
        "`basePath`; they agree in `swagger`, `info`, `schemes`, `paths` and `definitions`; the "
        "`info` object of each carries only `version`, `title` and `description`."
    )
    assert all(len(line) <= 88 for line in section.text.splitlines()), "wrapped at 88"


def test_the_section_names_the_info_fields_where_they_differ() -> None:
    part = ESR._part(response(PORTAL_SWAGGER_URL, text(DOCUMENT))).part
    backend = {**part, "info": {"title": "FAS Open Data"}}
    (section,) = Portal("/api/esr/").sections(parts_rows(part, backend))
    flat = " ".join(section.text.split())
    assert "their ESR parts differ in `info`; they agree in `swagger`, `host`" in flat
    assert flat.endswith(
        "the portal document's `info` object carries only `version`, `title` and "
        "`description`, the backend document's only `title`."
    )
    assert all(len(line) <= 88 for line in section.text.splitlines())


def test_no_section_without_both_documents() -> None:
    part = ESR._part(response(PORTAL_SWAGGER_URL, text(DOCUMENT))).part
    assert ESR.sections(parts_rows(part, part)[:1]) == ()
    assert ESR.sections([]) == ()


# -- the capture's text ------------------------------------------------------------------------


def test_the_capture_says_how_the_portal_is_read_in_four_paragraphs() -> None:
    paragraphs = ESR.capture.split("\n\n")
    assert len(paragraphs) == 4
    assert all("\n" not in paragraph for paragraph in paragraphs), "the frame wraps them"
    portal, backend, part, shells = paragraphs
    assert portal.startswith(
        f"The FAS Open Data Services portal, {PORTAL_URL}, documents three APIs of USDA's "
        "Foreign Agricultural Service: ESR, GATS and PSD."
    )
    assert f"Swagger 2.0 document {PORTAL_SWAGGER_URL}." in portal
    assert portal.endswith("this file records only its file name, in the portal page's row.")
    assert backend == (
        "The API also serves its own Swashbuckle document, which the classic Swagger UI at "
        f"{CLASSIC_UI_URL} loads; the script reads its URL from the UI page's `rootUrl` and "
        "`discoveryPaths`, and the UI page's row names it."
    )
    assert part.startswith(
        "Both documents cover ESR, GATS and PSD, and GATS and PSD get their own packages in "
        "this family, so each file here holds the ESR part only:"
    )
    assert "`paths` reduced to the keys starting with `/api/esr/`" in part
    assert shells == (
        "The portal page and the classic Swagger UI page are client-rendered shells without "
        "documentation text: each gets no file, only a row with its HTTP status and the size "
        f"and sha256 of its body, and a shell larger than {MAX_SHELL_BYTES} bytes, or without "
        "its mount point, stops the run."
    )


def test_the_capture_dates_the_find_of_the_portal_s_document_and_names_nobody() -> None:
    # It states what was fetched, when and where the URL stood, which a reader can check
    # against the portal (https://github.com/xippios/sdk-usda-esr/issues/17).
    found = (
        "On 2026-10-23, when sdk-usda-psd's snapshot was set up, the portal page and its "
        "JavaScript bundle were fetched into a temporary directory and that URL was found in "
        "the bundle's Swagger UI configuration; those copies have since been deleted, and this "
        "script reuses the URL."
    )
    for prefix in ("/api/esr/", "/api/gats/", "/api/psd/"):
        assert found in Portal(prefix).capture
        assert "scratch" not in Portal(prefix).capture


@pytest.mark.parametrize(
    ("prefix", "others"), [("/api/gats/", "ESR and PSD"), ("/api/psd/", "ESR and GATS")]
)
def test_the_capture_names_the_service_and_the_other_two(prefix: str, others: str) -> None:
    portal = Portal(prefix)
    assert (
        f"and {others} get their own packages in this family, so each file here holds the "
        f"{portal.service} part only"
    ) in portal.capture
    assert f"`paths` reduced to the keys starting with `{prefix}`" in portal.capture


# -- the kit on core's frame, offline ---------------------------------------------------------


class Pages:
    """A ``MockTransport`` handler that serves the portal's pages and keeps what was asked.

    NOT RECORDED: each page is composed in the shape the three sources' snapshot scripts read
    it in, the two shells with their mount point and configuration, the two documents as
    ``DOCUMENT``'s text and a page of the source's own refused at the CDN edge (conventions
    §10, kind 2).
    """

    def __init__(self, backend: dict[str, Any]) -> None:
        self.pages: dict[str, tuple[int, bytes, str]] = {
            PORTAL_URL: (200, portal_shell(BUNDLE), "text/html"),
            PORTAL_SWAGGER_URL: (200, text(DOCUMENT), "application/json"),
            CLASSIC_UI_URL: (200, classic_shell(), "text/html"),
            BACKEND_URL: (200, text(backend), "application/json; charset=utf-8"),
            "https://www.fas.usda.gov/data": (403, b"Access Denied", "text/html"),
        }
        self.asked: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.asked.append(url)
        status, body, content_type = self.pages[url]
        return httpx.Response(status, content=body, headers={"content-type": content_type})


def declared(out: Path, handler: Callable[[httpx.Request], httpx.Response]) -> Snapshot:
    """A FAS source's snapshot declared with the kit, as its script declares it."""
    client = AsyncClient(
        ClientConfig(source="usda-esr", version="0.0.0", base_url="https://apps.fas.usda.gov"),
        transport=httpx.MockTransport(handler),
    )
    refused = Page(
        "https://www.fas.usda.gov/data",
        status=403,
        stable=False,
        names="Access Denied",
        note="the FAS data page; 403 Access Denied at the CDN edge",
    )
    own = (
        "The FAS data page answers 403 Access Denied at the CDN edge to headless clients, a "
        "body that carries a per-request reference number."
    )
    return Snapshot(
        name="USDA FAS Export Sales Reporting",
        slug="usda-esr",
        pages=(*ESR.pages, refused),
        capture=f"{ESR.capture}\n\n{own}",
        out=out,
        pause=0.0,
        reduce=ESR.reduce,
        linked=ESR.linked,
        note=ESR.note,
        sections=ESR.sections,
        client=client,
    )


def test_core_s_frame_writes_the_snapshot_with_the_kit_and_check_finds_no_difference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    backend = {**DOCUMENT, "basePath": "/"}
    handler = Pages(backend)
    snapshot = declared(tmp_path / "upstream", handler)
    assert run(snapshot, []) == 0
    assert handler.asked == [
        PORTAL_URL,
        PORTAL_SWAGGER_URL,
        CLASSIC_UI_URL,
        BACKEND_URL,
        "https://www.fas.usda.gov/data",
    ], "the backend document right after the page that names it"
    out = tmp_path / "upstream"
    assert sorted(path.relative_to(out).as_posix() for path in out.rglob("*.*")) == [
        "FETCHED.md",
        BACKEND_FILE,
        PORTAL_FILE,
    ]
    portal = ESR._part(response(PORTAL_SWAGGER_URL, text(DOCUMENT))).part
    assert (out / PORTAL_FILE).read_bytes() == dump_json(portal)
    fetched = (out / "FETCHED.md").read_text(encoding="utf-8")
    flat = " ".join(fetched.split())
    assert "holds the ESR part only" in flat
    assert f"| {PORTAL_FILE} | {PORTAL_SWAGGER_URL} |" in fetched
    assert "ESR part: kept 2 `/api/esr/` paths; dropped 1 `/api/gats/`, 2 `/api/psd/`" in fetched
    assert f"{SHELL_NOTE}; loads the bundle `{BUNDLE}`" in fetched
    assert f"{SHELL_NOTE}; Swagger UI that loads `{BACKEND_URL}`" in fetched
    assert "## The two documents" in fetched
    assert "only the backend document has `basePath`" in flat
    capsys.readouterr()

    handler.asked.clear()
    assert run(snapshot, ["--check"]) == 0
    assert "The snapshot is current: upstream serves what it records." in capsys.readouterr().out
    assert len(handler.asked) == 5


def test_check_reports_a_document_whose_service_part_changed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    handler = Pages(DOCUMENT)
    snapshot = declared(tmp_path / "upstream", handler)
    assert run(snapshot, []) == 0
    capsys.readouterr()
    paths = {**DOCUMENT["paths"], "/api/esr/weeks": {"get": {}}}
    handler.pages[PORTAL_SWAGGER_URL] = (200, text({**DOCUMENT, "paths": paths}), "text/json")
    assert run(snapshot, ["--check"]) == 1
    assert f"differs: {PORTAL_FILE}" in capsys.readouterr().out
