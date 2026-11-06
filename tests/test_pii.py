from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agents.middleware import build_middleware


def test_pii_redaction() -> None:
    model = GenericFakeChatModel(messages=iter([AIMessage(content="ok")]))
    agent = create_agent(model=model, tools=[], middleware=build_middleware())

    result = agent.invoke({"messages": [{"role": "user", "content": "Contact john.smith@example.com member M12345678 ssn 123-45-6789"}]})
    state = result["messages"]
    joined = "\n".join(str(message.content) for message in state if hasattr(message, "content"))

    assert "john.smith@example.com" not in joined
    assert "M12345678" not in joined
    assert "123-45-6789" not in joined
    assert "REDACTED_EMAIL" in joined or "REDACTED_MEMBER_ID" in joined or "REDACTED_SSN" in joined
