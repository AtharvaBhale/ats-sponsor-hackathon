import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

from src.app import docs_parse, latex_resume as lr, resume_build as rb, routes_docs
from src.app.main import app

TEX = open("templates/resume.tex").read()
RESUME_TXT = """Jordan Example
jordan@example.com | 555-0100
EDUCATION
B.S. Computer Science, Fictional State University, 2024
EXPERIENCE
Software Intern, Acme Test Corp
- Built a REST API for an internal inventory tool.
• Wrote unit tests & raised coverage to 80%
SKILLS
Python, SQL"""


def make_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, x)


def test_extract_pdf_docx_txt():
    t, w = docs_parse.extract_text("r.pdf", make_pdf("Python project coursework for Jordan Example resume text"))
    assert "Python project" in t and not w
    d = Document(); d.add_paragraph("Capstone: built a Docker pipeline"); b = io.BytesIO(); d.save(b)
    assert "Docker pipeline" in docs_parse.extract_text("c.docx", b.getvalue())[0]
    assert docs_parse.extract_text("n.txt", b"hello\r\n\r\n\r\n\r\nworld")[0] == "hello\n\nworld"


def test_bad_inputs():
    with pytest.raises(docs_parse.ParseError):
        docs_parse.extract_text("x.exe", b"MZ")
    with pytest.raises(docs_parse.ParseError):
        docs_parse.extract_text("x.pdf", b"not a pdf")
    with pytest.raises(docs_parse.ParseError):
        docs_parse.extract_text("big.txt", b"a" * (docs_parse.MAX_BYTES + 1))
    assert docs_parse.extract_text("e.pdf", make_pdf(" "))[1]  # scanned/empty warning


def test_screening_keeps_relevant_drops_pii_and_noise():
    jd = "Requirements\nPython and Docker. Machine learning coursework preferred."
    text = ("Capstone project: containerized a Python service with Docker\n"
            "Coursework in machine learning and statistics\n"
            "Student ID: 12345678\nSSN 123-45-6789\n"
            "Played varsity chess and volunteered at the library\n")
    r = docs_parse.screen_evidence(text, jd)
    assert len(r["kept"]) == 2 and r["dropped_personal_ids"] == 2 and r["dropped_irrelevant"] == 1
    assert not any("123-45" in k or "12345678" in k for k in r["kept"])


def test_text_to_latex_structure_and_escaping():
    tex = rb.text_to_latex(RESUME_TXT)
    assert tex.count("\\item") == 2 and "\\section*{Education}" in tex and "\\section*{Experience}" in tex
    assert r"\& raised coverage to 80\%" in tex and tex.rstrip().endswith("\\end{document}")
    assert "jordan@example.com" in tex.split("\\section")[0]


def test_tex_to_plain_and_markdown():
    plain = rb.tex_to_plain(TEX)
    assert plain.splitlines()[0] == "Jordan Example" and "EDUCATION" in plain
    assert "- Built a REST API for an internal inventory tool." in plain and "\\" not in plain
    md = rb.tex_to_plain(TEX, markdown=True)
    assert md.startswith("# Jordan Example") and "## Experience" in md


def test_insert_bullet_existing_new_and_empty_section():
    t = lr.insert_bullet(TEX, "Built a Docker pipeline in a course project.", "Experience")
    assert t.count("\\item") == 3 and t.index("Docker pipeline") < t.index("\\end{itemize}")
    t2 = lr.insert_bullet(TEX, "Capstone with R & SQL", "Projects")
    assert "\\section*{Projects}" in t2 and r"R \& SQL" in t2 and t2.rstrip().endswith("\\end{document}")
    t3 = lr.insert_bullet(t2, "Another project.", "Projects")
    assert t3.count("\\section*{Projects}") == 1 and t3.count("\\item") == 4


@pytest.fixture
def client(monkeypatch):
    async def fake(ev, skill):
        return "Containerized a Flask app with Docker." if "Flask" in ev else "Led 40 engineers on Kubernetes."
    monkeypatch.setattr(routes_docs, "draft_fn", fake)
    return TestClient(app)


def test_api_uploads(client):
    r = client.post("/api/resume/upload", files={"file": ("r.txt", RESUME_TXT.encode())}).json()
    assert r["latex"].count("\\item") == 2
    assert client.post("/api/resume/upload", files={"file": ("r.exe", b"x")}).status_code == 400
    e = client.post("/api/evidence/upload", data={"job_description": "Requirements\nDocker"},
                    files={"file": ("t.txt", b"Course project: Docker deployment lab\nStudent ID: 99999999")}).json()
    assert len(e["kept"]) == 1 and e["dropped_personal_ids"] == 1


def test_api_synthesize_guard(client):
    ok = client.post("/api/synthesize", json={"evidence": "Course project: built a Flask app and ran it in Docker."}).json()
    assert ok["accepted"]
    bad = client.post("/api/synthesize", json={"evidence": "Course project: wrote a small script for class."}).json()
    assert not bad["accepted"] and bad["violations"]
    assert client.post("/api/synthesize", json={"evidence": "x"}).status_code == 400


def test_api_add_bullet_and_export(client):
    t = client.post("/api/resume/add-bullet", json={"tex": TEX, "bullet": "Did a thing.", "section": "Projects"}).json()["tex"]
    assert "Did a thing." in t
    r = client.post("/api/export", json={"tex": TEX, "format": "md"})
    assert r.status_code == 200 and "resume.md" in r.headers["content-disposition"] and r.text.startswith("# Jordan")
    assert client.post("/api/export", json={"tex": TEX, "format": "exe"}).status_code == 400


def test_sample_resume_route_serves_valid_latex(client):
    r = client.get("/api/sample-resume")
    assert r.status_code == 200 and r.text.startswith("\\documentclass")
