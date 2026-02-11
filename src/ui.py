"""
UI components and display helpers using Rich.

Handles all terminal output formatting, panels, boxes, themes.
"""

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.style import Style
from rich.theme import Theme

# Cyberpunk color scheme
CYBER_THEME = Theme({
    "cyan": "#00D9FF",
    "magenta": "#FF10F0",
    "neon_green": "#39FF14",
    "dim_cyan": "dim #00D9FF",
    "bright_white": "bright_white",
})

console = Console(theme=CYBER_THEME)

# Styles
STYLE_TOOL_CALL = Style(color="#00D9FF", bold=True)
STYLE_TOOL_RESULT = Style(color="#FF10F0")
STYLE_THINKING = Style(color="#00D9FF", dim=True)
STYLE_SUCCESS = Style(color="#39FF14")
STYLE_ERROR = Style(color="#FF10F0", bold=True)
STYLE_PROMPT = Style(color="#00D9FF", bold=True)


def display_tool_call(func_name: str, args: dict):
    """Display a tool call in a cyan panel."""
    if args:
        args_display = ", ".join(f'{k}="{v}"' for k, v in args.items() if v)
        if args_display:
            call_text = f"{func_name}({args_display})"
        else:
            call_text = f"{func_name}()"
    else:
        call_text = f"{func_name}()"

    panel = Panel(
        Text(call_text, style=STYLE_TOOL_CALL),
        title="[bold #00D9FF]TOOL CALL[/bold #00D9FF]",
        title_align="left",
        border_style="#00D9FF",
        padding=(0, 1),
    )
    console.print(panel)


def display_tool_result(result: str):
    """Display a tool result in a magenta panel."""
    result_preview = result[:200] + "..." if len(result) > 200 else result

    panel = Panel(
        Text(result_preview, style=STYLE_TOOL_RESULT),
        title="[bold #FF10F0]RESULT[/bold #FF10F0]",
        title_align="left",
        border_style="#FF10F0",
        padding=(0, 1),
    )
    console.print(panel)


def display_thinking():
    """Display thinking indicator."""
    text = Text("processing...", style=STYLE_THINKING)
    console.print(text)


def display_welcome():
    """Display welcome message with cyberpunk styling."""
    title = Text()
    title.append("LOCAL MEMORY ASSISTANT", style="bold #00D9FF")

    subtitle = Text()
    subtitle.append("Type ", style="dim white")
    subtitle.append("quit", style="#FF10F0")
    subtitle.append(" to exit", style="dim white")

    panel = Panel(
        Text.assemble(title, "\n", subtitle),
        border_style="#00D9FF",
        padding=(0, 2),
    )
    console.print(panel)
    console.print()


def get_user_input() -> str:
    """Get user input with styled prompt. Returns 'quit' on Ctrl+C/Ctrl+D."""
    console.print()
    prompt = Text()
    prompt.append("> ", style="bold #00D9FF")
    console.print(prompt, end="")
    try:
        return input().strip()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return "quit"


def display_response(content: str):
    """Display assistant response as rendered markdown."""
    if content:
        console.print()
        console.print(Markdown(content))
