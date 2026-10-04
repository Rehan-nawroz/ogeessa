"""StockTraderAgent — the LangChain tool-calling agent at the heart of ogeessa."""
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    GEMINI_API_KEY,
    GROQ_API_KEY,
    GROQ_MODEL,
    LLM_PROVIDER,
    OLLAMA_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)
from prompts.persona import PERSONA
from tools import ALL_TOOLS


def _build_llm():
    """Build the chat LLM for the configured provider (lazy imports)."""
    if LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=OPENAI_MODEL, api_key=OPENAI_API_KEY, temperature=0.2)
    if LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=ANTHROPIC_MODEL, api_key=ANTHROPIC_API_KEY, temperature=0.2)
    if LLM_PROVIDER == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=0.2)
    elif LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model="gemini-3.1-flash-lite",
            google_api_key=GEMINI_API_KEY,
        )
    if LLM_PROVIDER == "ollama":
        from langchain_community.chat_models import ChatOllama

        return ChatOllama(model=OLLAMA_MODEL, temperature=0.2)
    raise ValueError(
        f"Unknown LLM_PROVIDER '{LLM_PROVIDER}' (use openai | anthropic | groq | ollama)"
    )


class StockTraderAgent:
    """Tool-calling agent with manually managed session memory.

    Memory note (LangChain 0.2.x): ConversationBufferMemory passed to
    AgentExecutor is deprecated — do NOT pass memory=. The correct pattern
    is a chat_history MessagesPlaceholder plus manual message management
    in ask(), exactly as done below.
    """

    def __init__(self):
        # NOTE: create_tool_calling_agent requires a ChatPromptTemplate with
        # MessagesPlaceholder slots — never a plain string prompt.
        prompt = ChatPromptTemplate.from_messages([
            ("system", PERSONA),
            MessagesPlaceholder("chat_history"),      # session memory goes here
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),  # required by tool-calling agents
        ])

        self.chat_history = []
        self.llm = _build_llm()
        self.executor = AgentExecutor(
            agent=create_tool_calling_agent(self.llm, ALL_TOOLS, prompt),
            tools=ALL_TOOLS,
            verbose=False,
            handle_parsing_errors=True,
            max_iterations=10,
        )

    def ask(self, question: str) -> str:
        result = self.executor.invoke({
            "input": question,
            "chat_history": self.chat_history,  # pass history directly
        })
        output = result["output"]
        if isinstance(output, list):
            output = " ".join(
                item.get("text", str(item)) if isinstance(item, dict) else str(item)
                for item in output
            )
        output = str(output).strip()
        self.chat_history.append(HumanMessage(content=question))
        self.chat_history.append(AIMessage(content=output))
        return output

    def ask_stream(self, question: str):
        """Generator that yields text chunks as the LLM generates.

        Usage: for chunk in agent.ask_stream(question): ...

        Streams token-level chunks from astream_events(v2), filtering to
        final text content only — tool-call argument chunks have empty
        string content (OpenAI-style) or non-text parts (Gemini-style)
        and are skipped by the content checks below. Chat history is
        updated once the stream completes, mirroring ask().
        """
        import asyncio
        import queue
        import threading

        async def _stream():
            chunks = []
            try:
                async for event in self.executor.astream_events(
                    {
                        "input": question,
                        "chat_history": self.chat_history,
                    },
                    version="v2",
                ):
                    if event.get("event", "") != "on_chat_model_stream":
                        continue
                    chunk = event.get("data", {}).get("chunk", "")
                    content = getattr(chunk, "content", "")
                    if isinstance(content, str) and content:
                        chunks.append(content)
                        yield content
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                t = item.get("text", "")
                                if t:
                                    chunks.append(t)
                                    yield t
            finally:
                full = "".join(chunks)
                if full:
                    from langchain_core.messages import AIMessage, HumanMessage

                    self.chat_history.append(HumanMessage(content=question))
                    self.chat_history.append(AIMessage(content=full))

        q: queue.Queue = queue.Queue()

        async def producer():
            try:
                async for chunk in _stream():
                    q.put(chunk)
            except Exception as exc:  # bridge worker errors to the consumer
                q.put(exc)
            finally:
                q.put(None)  # sentinel

        thread = threading.Thread(target=lambda: asyncio.run(producer()), daemon=True)
        thread.start()

        try:
            while True:
                item = q.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        except Exception as exc:  # noqa: BLE001 — report, don't crash the UI
            yield f"Streaming error: {exc}"
        finally:
            thread.join(timeout=10)

    def reset(self):
        """Clear session memory."""
        self.chat_history = []