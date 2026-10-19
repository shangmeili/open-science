import { workspaceFilePath } from "./artifacts";
export { workspaceFilePath } from "./artifacts";

interface MarkdownNode {
  type: string;
  value?: string;
  url?: string;
  children?: MarkdownNode[];
}

/** Only inline code becomes a file link. Fenced code and existing links keep
 * their original semantics, including code-styled labels inside web links. */
export function remarkFileLinks() {
  return (tree: MarkdownNode) => {
    const visit = (node: MarkdownNode) => {
      if (!node.children || node.type === "link" || node.type === "linkReference") return;
      node.children = node.children.map((child) => {
        if (child.type === "inlineCode" && child.value && workspaceFilePath(child.value)) {
          return { type: "link", url: child.value, children: [child] };
        }
        visit(child);
        return child;
      });
    };
    visit(tree);
  };
}
