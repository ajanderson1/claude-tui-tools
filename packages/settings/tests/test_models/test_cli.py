"""Tests for CLI argument parsing."""

import pytest

from claude_tui_settings.cli import parse_args


def test_no_args():
    args = parse_args([])
    assert not args["summary"]
    assert not args["report"]
    assert not args["effective"]
    assert not args["help"]


def test_summary_flag():
    args = parse_args(["--summary"])
    assert args["summary"]


def test_report_flag():
    args = parse_args(["--report"])
    assert args["report"]


def test_effective_flag():
    args = parse_args(["--effective"])
    assert args["effective"]


def test_help_flag():
    args = parse_args(["--help"])
    assert args["help"]


def test_h_flag():
    args = parse_args(["-h"])
    assert args["help"]


def test_no_gum_prints_message(capsys):
    args = parse_args(["--no-gum"])
    captured = capsys.readouterr()
    assert "--no-gum is no longer needed" in captured.out


def test_unknown_flag_exits():
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--unknown"])
    assert exc_info.value.code == 1
