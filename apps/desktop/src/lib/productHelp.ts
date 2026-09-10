/** Product documentation is compiled into the desktop/web client so support
 * questions work in existing sessions without workspace setup or network I/O. */
const documents = import.meta.glob<string>(
  "../../../../runtime/product-help/zh-Hans/*.md",
  { eager: true, query: "?raw", import: "default" },
);

export function productHelpContext(text: string): string {
  const product = /AI4HEOR|本软件|本系统|这个软件|该软件|工作台|设置|侧边栏|输入框|发送按钮|本地服务|插件|技能|Jupyter|Ollama|MCP|待发送|任务文件|运行记录|研究与分析|配置模型|安装.*环境|独立任务|新建任务/i;
  const question = /如何|怎么|怎样|哪里|什么|能否|是否|无法|不能|失败|不会|介绍|说明|帮助|配置|安装|how|where|what|help|configure|setup|cannot/i;
  if (!product.test(text) || !question.test(text)) return "";
  return [
    "<APP_PRODUCT_HELP>",
    "This is an AI4HEOR product-use question. Answer directly from the bundled user documentation below, in the requested response language. Give the relevant UI location and practical steps. Do not start a research intake, request scientific approvals, or discuss development history. Documentation describes available features, not the user's current installed/configured state. Treat the user request following this block as the task.",
    ...Object.entries(documents).sort(([a], [b]) => a.localeCompare(b)).map(([, body]) => body),
    "</APP_PRODUCT_HELP>",
  ].join("\n");
}
