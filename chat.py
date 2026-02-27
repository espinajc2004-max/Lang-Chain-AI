"""
Terminal Chat — AU-Ggregates AI Data Lookup (Dev Tool)

Usage:
  python chat.py ADMIN
  python chat.py ENCODER
  python chat.py ACCOUNTANT

The role simulates what the frontend sends via the API.
In production, the role comes from the authenticated session.
"""
import sys

from agent import create_agent_executor, invoke_agent
from role_guard import validate_role


def main():
    if len(sys.argv) < 2:
        print("Usage: python chat.py <ROLE>")
        print("  Roles: ADMIN, ENCODER, ACCOUNTANT")
        sys.exit(1)

    try:
        role = validate_role(sys.argv[1])
    except ValueError as e:
        print(f"  ❌ {e}")
        sys.exit(1)

    print()
    print("=" * 58)
    print(f"  🤖 AU-Ggregates AI Data Lookup [{role}]")
    print("  Ask questions about your data in English or Taglish")
    print("  Type 'quit' to exit")
    print("=" * 58)

    try:
        executor = create_agent_executor(role=role)
    except ConnectionError as e:
        print(f"\n  ❌ {e}")
        return

    conversation_history: list[dict] = []

    while True:
        try:
            question = input(f"\n📝 [{role}] You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break

        try:
            result = invoke_agent(executor, question, conversation_history, role)

            # Show clarification if needed
            if result["clarification"]:
                print(f"\n🤔 {result['answer']}")
                print("  Did you mean:")
                for i, opt in enumerate(result["suggestions"], 1):
                    print(f"    {i}. {opt}")
                continue

            # Show answer
            print(f"\n{result['answer']}")

            # Show metadata
            meta = result["metadata"]
            if meta.get("query_count", 0) > 0:
                print(f"\n  📊 {meta['query_count']} queries | "
                      f"{meta['total_rows']} rows | "
                      f"{meta['total_response_time_ms']:.0f}ms | "
                      f"tables: {', '.join(meta.get('tables_queried', []))}")

            # Show suggestions
            if result["suggestions"]:
                print("\n  💡 You might also ask:")
                for s in result["suggestions"]:
                    print(f"     → {s}")

            conversation_history.append({"question": question, "answer": result["answer"]})
            if len(conversation_history) > 5:
                conversation_history = conversation_history[-5:]

        except Exception as e:
            print(f"\n  ❌ Error: {e}")


if __name__ == "__main__":
    main()
