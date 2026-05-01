"""Terminal UI — colors, print helpers, prompts."""

import getpass

BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"
RESET = "\033[0m"

PRIORITY_COLORS = {"High": RED, "Medium": YELLOW, "Low": GREEN}
PRIORITY_LABELS = ("High", "Medium", "Low")


def print_banner():
    print()
    print(f"  {BOLD}{CYAN}╔══════════════════════════════════════════════════════╗{RESET}")
    print(f"  {BOLD}{CYAN}║                                                      ║{RESET}")
    print(f"  {BOLD}{CYAN}║                {WHITE}🚀  F I X F L E E T{CYAN}                     ║{RESET}")
    print(f"  {BOLD}{CYAN}║        {DIM}{WHITE}Fleet of AI agents fixing GitLab bugs{CYAN}{RESET}{BOLD}{CYAN}         ║{RESET}")
    print(f"  {BOLD}{CYAN}║                                                      ║{RESET}")
    print(f"  {BOLD}{CYAN}║        {DIM}{WHITE}Multi-CLI · Multi-API · Token-Aware{CYAN}{RESET}{BOLD}{CYAN}           ║{RESET}")
    print(f"  {BOLD}{CYAN}║        {DIM}{WHITE}Built by Yash Koladiya{CYAN}{RESET}{BOLD}{CYAN}                        ║{RESET}")
    print(f"  {BOLD}{CYAN}║                                                      ║{RESET}")
    print(f"  {BOLD}{CYAN}╚══════════════════════════════════════════════════════╝{RESET}")
    print()


def print_section(title):
    print(f"\n  {BOLD}{BLUE}┌─ {WHITE}{title}{RESET}")
    print(f"  {BLUE}│{RESET}")


def print_info(msg):
    print(f"  {BLUE}│  {WHITE}{msg}{RESET}")


def print_success(msg):
    print(f"  {GREEN}│  ✓ {msg}{RESET}")


def print_error(msg):
    print(f"  {RED}│  ✗ {msg}{RESET}")


def print_warning(msg):
    print(f"  {YELLOW}│  ! {msg}{RESET}")


def print_divider():
    print(f"  {DIM}{BLUE}│{'─' * 54}{RESET}")


def print_end():
    print(f"  {BLUE}│{RESET}")
    print(f"  {BLUE}└{'─' * 54}{RESET}")


def print_summary(fixed: int, failed: int, total: int):
    print()
    print(f"  {BOLD}{GREEN}╔══════════════════════════════════════════════════════╗{RESET}")
    print(f"  {BOLD}{GREEN}║                                                      ║{RESET}")
    print(f"  {BOLD}{GREEN}║           {WHITE}All Done! Review your changes:{GREEN}              ║{RESET}")
    print(f"  {BOLD}{GREEN}║                                                      ║{RESET}")
    print(f"  {BOLD}{GREEN}║   {CYAN}  git status  {DIM}{WHITE}  - see changed files{GREEN}               ║{RESET}")
    print(f"  {BOLD}{GREEN}║   {CYAN}  git diff    {DIM}{WHITE}  - see what changed{GREEN}                ║{RESET}")
    print(f"  {BOLD}{GREEN}║                                                      ║{RESET}")
    print(f"  {BOLD}{GREEN}╚══════════════════════════════════════════════════════╝{RESET}")
    print(f"\n  {BOLD}Fixed:{RESET} {GREEN}{fixed}{RESET}   {BOLD}Failed:{RESET} {RED}{failed}{RESET}   {BOLD}Total:{RESET} {total}\n")


def ask_input(prompt_text: str) -> str:
    return input(f"  {BLUE}│  {MAGENTA}> {WHITE}{prompt_text}: {RESET}").strip()


def ask_secret(prompt_text: str) -> str:
    return getpass.getpass(f"  {BLUE}│  {MAGENTA}> {WHITE}{prompt_text}: {RESET}").strip()


def get_priority(labels: list) -> tuple:
    """Return (priority_name, color) for given labels."""
    for lbl in PRIORITY_LABELS:
        if lbl in labels:
            return lbl, PRIORITY_COLORS[lbl]
    return "None", WHITE
