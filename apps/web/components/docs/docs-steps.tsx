export interface DocsStepsProps {
  items: string[];
}

export function DocsSteps({ items }: DocsStepsProps) {
  return (
    <ol className="space-y-3">
      {items.map((item, index) => (
        <li key={item} className="flex gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-semibold text-white">
            {index + 1}
          </span>
          <span className="pt-0.5 text-sm leading-relaxed text-slate-600">{item}</span>
        </li>
      ))}
    </ol>
  );
}
