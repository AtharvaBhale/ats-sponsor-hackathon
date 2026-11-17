from src.app.gap import analyze

JD = """Requirements
3+ years of Python and SQL experience
Experience with Docker and AWS
Nice to have
Kubernetes, Terraform
"""
RESUME = "Built a REST API in Python with PostgreSQL. Containerized with Docker."


def test_required_split_and_gaps():
    g = analyze(RESUME, JD)
    assert "python" in g["matched_required"] and "docker" in g["matched_required"]
    assert "aws" in g["missing_required"]
    assert "kubernetes" in g["missing_preferred"]
    assert g["years_requested"] == 3
    assert any("aws" in q for q in g["questions"])


def test_no_false_match_on_substring():
    # 'go' must not match inside 'good'/'google'; 'r' must not match random letters
    g = analyze("I am good at working with Google Docs.", "Requirements\nGo, R")
    assert g["matched_required"] == []
