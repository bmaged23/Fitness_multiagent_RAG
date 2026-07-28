from pathlib import Path


def load_prompt(prompt_path: Path | str) -> str:
    return Path(prompt_path).read_text(encoding="utf-8").strip()


def load_agent_prompt(agent_dir: Path, filename: str) -> str:
    """Load a prompt file relative to an agent's prompts/ directory."""
    return load_prompt(agent_dir / "prompts" / filename)
