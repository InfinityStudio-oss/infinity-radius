import type { DocsBlock } from "@/content/docs/types";
import { DocsCallout } from "./docs-callout";
import { DocsSteps } from "./docs-steps";
import { DocsCodeBlock } from "./docs-code-block";

export function DocsBlockRenderer({ blocks }: { blocks: DocsBlock[] }) {
  return (
    <div className="space-y-4">
      {blocks.map((block, index) => {
        switch (block.type) {
          case "p":
            return (
              <p key={index} className="text-sm leading-relaxed text-slate-600">
                {block.text}
              </p>
            );
          case "list":
            return (
              <ul key={index} className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-slate-600">
                {block.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            );
          case "steps":
            return <DocsSteps key={index} items={block.items} />;
          case "callout":
            return (
              <DocsCallout key={index} tone={block.tone}>
                {block.text}
              </DocsCallout>
            );
          case "code":
            return <DocsCodeBlock key={index} code={block.code} label={block.label} />;
          default:
            return null;
        }
      })}
    </div>
  );
}
