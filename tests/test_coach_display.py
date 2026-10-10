import re
import shutil

from fitness_multiagent_rag.agents.coach import main


def test_box_wraps_long_reply_to_terminal(monkeypatch, capsys):
    monkeypatch.setattr(main.shutil, 'get_terminal_size', lambda **kwargs: shutil.os.terminal_size((80, 24)))
    main._box('A long response ' * 100 + '\n\n\n\nFinal sentence.')
    output = re.sub(r'\x1b\[[0-9;]*m', '', capsys.readouterr().out)
    lines = [line for line in output.splitlines() if line]
    assert max(map(len, lines)) <= 80
    assert len({len(line) for line in lines}) == 1
    assert 'Final sentence.' in output


def test_tagged_thinking_is_removed():
    assert main._strip_tokens('<think>private reasoning</think>Here is the reply.') == 'Here is the reply.'
