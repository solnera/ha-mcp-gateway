class McpGatewayPanel extends HTMLElement {
  connectedCallback() {
    const iframe = document.createElement("iframe");
    iframe.src = "/mcp_gateway_static/panel.html";
    iframe.style.cssText = "border:0;width:100%;height:100%";
    this.style.display = "block";
    this.style.height = "calc(100vh - 56px)";
    this.appendChild(iframe);
  }
}
customElements.define("mcp-gateway-panel", McpGatewayPanel);
