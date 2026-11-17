import pytest
from src.app.skills import extract_skills

NOT_SKILLS = [
    "Develop a go-to-market strategy for enterprise accounts.",
    "We go above and beyond for customers. Go get them!",
    "You will go to market with our partners.",
    "Own R&D budget conversations with the team.",
    "Help the rest of the team close deals.",
    "Candidates who excel at communication thrive here.",
    "Strive to excel in a fast-paced environment.",
    "Our culture will spark joy and spring into action.",
    "Be ready to react to changing priorities.",
    "I am good at working with Google Docs.",
]


@pytest.mark.parametrize("text", NOT_SKILLS)
def test_prose_is_not_a_skill(text):
    assert extract_skills(text) == set(), text


POSITIVES = [
    ("Languages: Python, Go, Rust", {"python", "go", "rust"}),
    ("Experience with Python and Go.", {"python", "go"}),
    ("Built services in golang", {"go"}),
    ("Skills: Python, R, SQL", {"python", "r", "sql"}),
    ("Used R programming for analysis", {"r"}),
    ("Designed a REST API", {"rest"}),
    ("Built RESTful services", {"rest"}),
    ("Advanced Microsoft Excel and Tableau", {"excel", "tableau"}),
    ("Pipelines on Apache Spark and Kafka", {"spark", "kafka"}),
    ("Java, Spring Boot, PostgreSQL", {"java", "spring", "postgresql"}),
    ("Frontend in React and TypeScript", {"react", "typescript"}),
    ("Backend: Node, Python", {"node.js", "python"}),
    ("Applied ML and deep learning", {"machine learning", "deep learning"}),
]


@pytest.mark.parametrize("text,expected", POSITIVES)
def test_real_skills_detected(text, expected):
    assert extract_skills(text) == expected, text
