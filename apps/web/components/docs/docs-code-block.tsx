export interface DocsCodeBlockProps {
  code: string;
  label?: string;
}

export function DocsCodeBlock({ code, label }: DocsCodeBlockProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      {label && (
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-1.5 text-xs font-medium text-slate-500">
          {label}
        </div>
      )}
      <pre className="overflow-x-auto bg-slate-900 px-4 py-3 text-xs leading-relaxed text-slate-100">
        <code>{code}</code>
      </pre>
    </div>
  );
}
