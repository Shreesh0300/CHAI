"""
Manual Terminal Client for CHAI Backend.

Connects to the running FastAPI server at http://127.0.0.1:8000/api/solve
and provides an interactive terminal interface to test both simple and complex queries.
"""
import sys
from typing import Optional
import httpx

API_BASE_URL = "http://127.0.0.1:8000"
SOLVE_ENDPOINT = f"{API_BASE_URL}/api/solve"
TIMEOUT_SECONDS = 300.0  # Multi-agent pipelines may take time to orchestrate


def sanitize_error_summary(err_str: Optional[str]) -> Optional[str]:
    """Return a brief, safe summary of an error message without stack frames."""
    if not err_str:
        return None
    s = str(err_str).strip()
    if "Traceback" in s or "\n" in s:
        s = s.split("\n")[0]
    if len(s) > 90:
        s = s[:87] + "..."
    return s


def format_response(data: dict) -> None:
    """Format and display the CHAI FinalResponse payload cleanly."""
    final_answer = data.get("final_answer") or data.get("final_synthesized_answer") or "No answer returned."
    status = data.get("status") or data.get("request_status") or "unknown"
    route = data.get("route") or "unknown"
    selected_agents = data.get("selected_agents") or []
    agent_statuses = data.get("agent_execution_statuses") or []
    execution_trace = data.get("execution_trace") or []
    limitations = data.get("limitations") or []
    sources = data.get("retrieved_sources") or []

    # If sources not in retrieved_sources, extract from acquired_information
    if not sources:
        acquired = data.get("acquired_information") or []
        for ac in acquired:
            if isinstance(ac, dict):
                src = ac.get("url") or ac.get("title") or ac.get("source")
                if src and src not in sources:
                    sources.append(src)

    print("\n------------------------------------------------------------")
    print("FINAL ANSWER")
    print("------------------------------------------------------------")
    print(final_answer.strip())

    print("\n------------------------------------------------------------")
    print("STATUS")
    print("------------------------------------------------------------")
    print(status)

    print("\n------------------------------------------------------------")
    print("ROUTE")
    print("------------------------------------------------------------")
    print(route)

    if agent_statuses:
        print("\n------------------------------------------------------------")
        print("AGENT STATUS")
        print("------------------------------------------------------------")
        for st in agent_statuses:
            if isinstance(st, dict):
                name = st.get("agent_name", "unknown")
                status_raw = str(st.get("status", "unknown")).lower()
                err = sanitize_error_summary(st.get("error"))
                if status_raw in ("success", "completed"):
                    mark = "[OK] completed"
                else:
                    mark = "[FAIL] failed"
                    if err:
                        mark += f" ({err})"
                print(f"  {name:<22} {mark}")

    print("\n------------------------------------------------------------")
    print("SELECTED AGENTS")
    print("------------------------------------------------------------")
    if selected_agents:
        for agent in selected_agents:
            print(f"  {agent}")
    else:
        print("  []")

    print("\n------------------------------------------------------------")
    print("EXECUTION TRACE")
    print("------------------------------------------------------------")
    if execution_trace:
        for item in execution_trace:
            if isinstance(item, dict):
                agent_name = item.get("agent") or item.get("stage") or str(item)
                print(f"  -> {agent_name}")
            else:
                print(f"  -> {item}")
    else:
        print("  None")

    if limitations:
        print("\n------------------------------------------------------------")
        print("LIMITATIONS")
        print("------------------------------------------------------------")
        for lim in limitations:
            print(f"  - {lim}")

    if sources:
        print("\n------------------------------------------------------------")
        print("SOURCES / PROVENANCE")
        print("------------------------------------------------------------")
        for src in sources:
            print(f"  - {src}")

    print("============================================================\n")


def send_query(client: httpx.Client, query: str) -> bool:
    """
    Send a problem query to the CHAI backend /api/solve endpoint.
    Returns True if request completed (success or handled failure), False if fatal connection error.
    """
    payload = {"problem": query.strip()}

    try:
        response = client.post(SOLVE_ENDPOINT, json=payload, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()

        try:
            data = response.json()
        except Exception as json_err:
            print(f"\n[ERROR] Failed to parse JSON response from server: {json_err}")
            print(f"Raw response content: {response.text[:500]}")
            return False

        format_response(data)
        return True

    except httpx.ConnectError:
        print("\n[CONNECTION ERROR] Could not connect to CHAI backend at http://127.0.0.1:8000.")
        print("Please verify the backend server is running in Terminal 1:")
        print("  uvicorn backend.main:app --reload")
        return False
    except httpx.TimeoutException:
        print(f"\n[TIMEOUT ERROR] Request timed out after {TIMEOUT_SECONDS}s.")
        print("The multi-agent execution took longer than expected.")
        return False
    except httpx.HTTPStatusError as http_err:
        print(f"\n[HTTP ERROR] Server returned status {http_err.response.status_code}:")
        try:
            err_detail = http_err.response.json()
            print(f"Detail: {err_detail}")
        except Exception:
            print(f"Detail: {http_err.response.text}")
        return False
    except Exception as err:
        print(f"\n[UNEXPECTED ERROR] {err}")
        return False


def main() -> None:
    """Run the interactive manual testing loop or one-shot command line query."""
    print("=" * 60)
    print("                    CHAI TERMINAL")
    print("=" * 60)
    print(f"Connecting to: {SOLVE_ENDPOINT}")
    print("Type your query and press Enter. Type 'exit', 'quit' or Ctrl+C to exit.\n")

    # If query was provided via command line arguments, execute once and exit
    if len(sys.argv) > 1:
        cli_query = " ".join(sys.argv[1:])
        print(f"CHAI > {cli_query}")
        with httpx.Client() as client:
            send_query(client, cli_query)
        return

    # Interactive session loop
    with httpx.Client() as client:
        while True:
            try:
                query = input("CHAI > ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n\nExiting CHAI Terminal. Goodbye!")
                break

            if not query:
                continue

            if query.lower() in {"exit", "quit"}:
                print("\nExiting CHAI Terminal. Goodbye!")
                break

            send_query(client, query)


if __name__ == "__main__":
    main()
