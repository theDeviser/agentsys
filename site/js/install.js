/** Single source for MCP install deep links (validated by scripts/check_install_links.py). */
export const INSTALL_TARGETS = {
  "cursor": "cursor://anysphere.cursor-deeplink/mcp/install?name=agentsys&config=%7B%22command%22%3A%22agentsys%22%2C%22args%22%3A%5B%22mcp%22%5D%7D",
  "vscode": "https://code.visualstudio.com/docs/copilot/customization/mcp",
  "claude": "https://docs.anthropic.com/en/docs/claude-code/mcp",
  "codex": "https://github.com/openai/codex"
};

export function mcpConfigJson(actor = "human:you") {
  return JSON.stringify({
    mcpServers: {
      agentsys: {
        command: "agentsys",
        args: ["mcp", "--as", actor],
      },
    },
  }, null, 2);
}
