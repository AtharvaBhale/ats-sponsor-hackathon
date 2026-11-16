import pytest
from src.app import latex


def test_blocks_shell_escape():
    with pytest.raises(latex.LatexError):
        latex.validate(r"\immediate\write18{ls}")


def test_blocks_absolute_input():
    with pytest.raises(latex.LatexError):
        latex.validate(r"\input{/etc/passwd}")


def test_allows_normal_resume():
    latex.validate(open("templates/resume.tex").read())
